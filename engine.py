import fuse
import os
import errno
import logging
import adapter
import stat
import shutil
from cache import MetadataCache

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Engine")


class CloudFUSE(fuse.Operations):
    def __init__(self, token, cache_dir, max_cache_size):
        self.adapter = adapter.get_adapter(token)
        self.cache = MetadataCache()
        self.cache_dir = cache_dir
        self.max_cache_size = max_cache_size
        self.active_files = set()
        self.dirty_files = set()

        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)

        self.current_cache_size = self._calculate_initial_cache_size()
        self.cache.set_node('/', 4096, is_dir=True)

        try:
            files = self.adapter.listdir('/')
            file_names = []
            for f in files:
                name = f['name']
                path = f'/{name}'
                self.cache.set_node(path, size=f['size'], is_dir=f.get('is_dir', False))
                file_names.append(name)
            self.cache.set_directory_list('/', file_names)
        except Exception as e:
            logger.error(f"Initial listdir failed: {e}")

    def _get_cache_path(self, path):
        return os.path.join(self.cache_dir, path.lstrip('/'))

    def statfs(self, path):
        return {
            'f_bsize': 4096,
            'f_blocks': 100000000,
            'f_bfree': 50000000,
            'f_bavail': 50000000,
            'f_files': 1000000,
            'f_ffree': 1000000,
            'f_namemax': 255
        }

    def getattr(self, path, fh=None):
        basename = os.path.basename(path)
        if basename in ['.directory', '.hidden', '.Trash', '.Trash-1000', 'autorun.inf']:
            raise fuse.FuseOSError(errno.ENOENT)
        attrs = self.cache.get_attrs(path)
        if attrs:
            return attrs

        try:
            metadata = self.adapter.get_metadata(path)
            self.cache.set_node(path, size=metadata['size'], is_dir=metadata.get('is_dir', False))
            return self.cache.get_attrs(path)
        except:
            raise fuse.FuseOSError(errno.ENOENT)

    def readdir(self, path, fh):
        dirents = ['.', '..']
        cached_list = self.cache.get_directory_list(path)

        if cached_list is None:
            remote_files = self.adapter.listdir(path)
            file_names = [f['name'] for f in remote_files]
            for f in remote_files:
                child_path = os.path.join(path, f['name']).replace('\\', '/').replace('//', '/')
                self.cache.set_node(child_path, size=f['size'], is_dir=f.get('is_dir', False))
            self.cache.set_directory_list(path, file_names)
            cached_list = file_names

        dirents.extend(cached_list)
        for r in dirents:
            yield r

    def read(self, path, size, offset, fh):
        local_path = self._get_cache_path(path)
        attrs = self.getattr(path)
        remote_size = attrs['st_size']

        needs_download = not os.path.exists(local_path)
        if not needs_download:
            local_size = os.path.getsize(local_path)
            if local_size != remote_size and path not in self.dirty_files:
                logger.info(f"CACHE INVALID: {path} changed in cloud")
                needs_download = True

        if needs_download:
            # 1. Защита: файл больше всего кэша
            if remote_size > self.max_cache_size:
                logger.error(f"File {path} exceeds max cache size")
                raise fuse.FuseOSError(errno.EFBIG)

            # 2. Освобождаем место ДО загрузки
            self._make_room(remote_size)

            logger.info(f"DOWNLOADING (STREAM): {path}...")
            self.active_files.add(path)
            try:
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                self.adapter.download_file(path, local_path)

                # Фиксируем итоговый размер
                actual_size = os.path.getsize(local_path)
                self.current_cache_size += actual_size
            except Exception as e:
                logger.error(f"Download failed: {e}")
                if os.path.exists(local_path): os.remove(local_path)
                raise fuse.FuseOSError(errno.EIO)
            finally:
                self.active_files.discard(path)

        with open(local_path, 'rb') as f:
            f.seek(offset)
            return f.read(size)

    def write(self, path, data, offset, fh):
        local_path = self._get_cache_path(path)
        self.dirty_files.add(path)

        old_local_size = os.path.getsize(local_path) if os.path.exists(local_path) else 0

        if not os.path.exists(local_path):
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            attrs = self.cache.get_attrs(path)
            if attrs and attrs['st_size'] > 0:
                try:
                    self.adapter.download_file(path, local_path)
                    old_local_size = os.path.getsize(local_path)
                except:
                    with open(local_path, 'wb') as f:
                        pass
            else:
                with open(local_path, 'wb') as f:
                    pass

        with open(local_path, 'r+b') as f:
            f.seek(offset)
            f.write(data)

        new_local_size = os.path.getsize(local_path)
        size_diff = new_local_size - old_local_size

        if size_diff > 0:
            self._make_room(size_diff)
            self.current_cache_size += size_diff

        self.cache.set_node(path, size=new_local_size, is_dir=False)
        return len(data)

    def release(self, path, fh):
        if path in self.dirty_files:
            local_path = self._get_cache_path(path)
            logger.info(f"RELEASE: Syncing {path} to cloud...")
            self.active_files.add(path)
            try:
                with open(local_path, 'rb') as f:
                    self.adapter.write_file(path, f)
                self.dirty_files.remove(path)
            except Exception as e:
                logger.error(f"Failed to sync {path}: {e}")
            finally:
                self.active_files.discard(path)
        return 0

    def create(self, path, mode, fi=None):
        logger.info(f"CREATE: {path}")
        local_path = self._get_cache_path(path)
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, 'wb') as f: pass

        self.dirty_files.add(path)
        self.cache.set_node(path, size=0, is_dir=False)
        self._add_to_parent_list(path)
        return 0

    def truncate(self, path, length, fh=None):
        local_path = self._get_cache_path(path)
        old_size = os.path.getsize(local_path) if os.path.exists(local_path) else 0

        if not os.path.exists(local_path):
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            with open(local_path, 'wb') as f: pass

        with open(local_path, 'r+b') as f:
            f.truncate(length)

        size_diff = length - old_size
        if size_diff > 0:
            self._make_room(size_diff)

        self.current_cache_size += size_diff
        self.cache.set_node(path, size=length, is_dir=False)
        self.dirty_files.add(path)
        return 0

    def unlink(self, path):
        logger.info(f"UNLINK: {path}")
        self.adapter.delete(path)
        local_path = self._get_cache_path(path)
        if os.path.exists(local_path):
            file_size = os.path.getsize(local_path)
            os.remove(local_path)
            self.current_cache_size -= file_size

        if hasattr(self.cache, 'remove_node'):
            self.cache.remove_node(path)
        self._remove_from_parent_list(path)
        return 0

    def mkdir(self, path, mode):
        self.adapter.mkdir(path)
        self.cache.set_node(path, size=4096, is_dir=True)
        self._add_to_parent_list(path)
        return 0

    def rmdir(self, path):
        self.adapter.delete(path)
        if hasattr(self.cache, 'remove_node'):
            self.cache.remove_node(path)
        self._remove_from_parent_list(path)
        return 0

    def rename(self, old, new):
        self.adapter.move(old, new)
        old_local = self._get_cache_path(old)
        new_local = self._get_cache_path(new)

        if os.path.exists(old_local):
            os.makedirs(os.path.dirname(new_local), exist_ok=True)
            os.rename(old_local, new_local)

        attrs = self.cache.get_attrs(old)
        if attrs:
            self.cache.set_node(new, size=attrs['st_size'], is_dir=stat.S_ISDIR(attrs['st_mode']))

        if hasattr(self.cache, 'remove_node'):
            self.cache.remove_node(old)
        self._remove_from_parent_list(old)
        self._add_to_parent_list(new)
        return 0

    def utimens(self, path, times=None):
        return 0

    def _add_to_parent_list(self, path):
        parent = os.path.dirname(path)
        self.cache.set_directory_list(parent, None)

    def _remove_from_parent_list(self, path):
        parent = os.path.dirname(path)
        self.cache.set_directory_list(parent, None)

    def _calculate_initial_cache_size(self):
        total = 0
        for root, _, filenames in os.walk(self.cache_dir):
            for f in filenames:
                total += os.path.getsize(os.path.join(root, f))
        return total

    def _make_room(self, required_size):
        while (self.current_cache_size + required_size) > self.max_cache_size:
            evicted_size = self._evict_one_oldest()
            if evicted_size == 0:
                logger.warning("Cache is full of active/dirty files. Cannot free more space.")
                break

    def _evict_one_oldest(self):
        files = []
        for root, _, filenames in os.walk(self.cache_dir):
            for f in filenames:
                full_path = os.path.join(root, f)
                rel_path = "/" + os.path.relpath(full_path, self.cache_dir).replace('\\', '/')

                if rel_path in self.dirty_files or rel_path in self.active_files:
                    continue
                try:
                    stat_info = os.stat(full_path)
                    files.append((full_path, stat_info.st_size, stat_info.st_atime))
                except:
                    continue

        if not files:
            return 0

        path_to_remove, size_to_remove, _ = min(files, key=lambda x: x[2])
        try:
            os.remove(path_to_remove)
            self.current_cache_size -= size_to_remove
            logger.info(f"Evicted: {path_to_remove} ({size_to_remove} bytes)")
            return size_to_remove
        except Exception as e:
            logger.error(f"Failed to evict {path_to_remove}: {e}")
            return 0

    def _evict_cache_if_needed(self):
        while self.current_cache_size > self.max_cache_size:
            if self._evict_one_oldest() == 0:
                break
