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
    def __init__(self):
        self.adapter = adapter.get_adapter()
        self.cache = MetadataCache()
        self.cache_dir = os.path.expanduser("~/.cache/yandex_cloud_fuse")
        self.max_cache_size = 1 * 1024 * 1024 * 1024
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)

        self.dirty_files = set()
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
                child_path = os.path.join(path, f['name']).replace('\\', '/')
                self.cache.set_node(child_path, size=f['size'], is_dir=f.get('is_dir', False))
            self.cache.set_directory_list(path, file_names)
            cached_list = file_names

        dirents.extend(cached_list)
        for r in dirents:
            yield r

    def read(self, path, size, offset, fh):
        local_path = self._get_cache_path(path)
        if not os.path.exists(local_path):
            logger.info(f"CACHE MISS: Downloading {path} to disk cache...")
            try:
                data = self.adapter.read_file(path)
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                with open(local_path, 'wb') as f:
                    f.write(data)
                self._evict_cache_if_needed()
            except Exception as e:
                logger.error(f"Failed to download {path}: {e}")
                raise fuse.FuseOSError(errno.EIO)

        with open(local_path, 'rb') as f:
            f.seek(offset)
            return f.read(size)

    def write(self, path, data, offset, fh):
        local_path = self._get_cache_path(path)
        self.dirty_files.add(path)
        if not os.path.exists(local_path):
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            try:
                base_content = self.adapter.read_file(path)
            except:
                base_content = b""
            with open(local_path, 'wb') as f:
                f.write(base_content)
        with open(local_path, 'r+b') as f:
            f.seek(offset)
            f.write(data)

        new_size = os.path.getsize(local_path)
        self.cache.set_node(path, size=new_size, is_dir=False)
        return len(data)

    def release(self, path, fh):
        if path in self.dirty_files:
            local_path = self._get_cache_path(path)
            logger.info(f"RELEASE: Uploading changed file {path} to cloud...")
            try:
                with open(local_path, 'rb') as f:
                    self.adapter.write_file(path, f.read())
                self.dirty_files.remove(path)
                self._evict_cache_if_needed()
            except Exception as e:
                logger.error(f"Failed to upload {path}: {e}")
        return 0

    def create(self, path, mode, fi=None):
        logger.info(f"CREATE: {path}")
        local_path = self._get_cache_path(path)
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, 'wb') as f:
            pass

        self.dirty_files.add(path)
        self.cache.set_node(path, size=0, is_dir=False)
        self._add_to_parent_list(path)
        return 0

    def truncate(self, path, length, fh=None):
        local_path = self._get_cache_path(path)
        if os.path.exists(local_path):
            with open(local_path, 'r+b') as f:
                f.truncate(length)
        self.cache.set_node(path, size=length, is_dir=False)
        self.dirty_files.add(path)
        return 0

    def unlink(self, path):
        self.adapter.delete(path)
        local_path = self._get_cache_path(path)
        if os.path.exists(local_path):
            os.remove(local_path)
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
            is_dir = stat.S_ISDIR(attrs['st_mode'])
            self.cache.set_node(new, size=attrs['st_size'], is_dir=is_dir)

        self._remove_from_parent_list(old)
        self._add_to_parent_list(new)
        return 0

    def _add_to_parent_list(self, path):
        parent = os.path.dirname(path)
        name = os.path.basename(path)
        children = self.cache.get_directory_list(parent) or []
        if name not in children:
            children.append(name)
            self.cache.set_directory_list(parent, children)

    def _remove_from_parent_list(self, path):
        parent = os.path.dirname(path)
        name = os.path.basename(path)
        children = self.cache.get_directory_list(parent) or []
        if name in children:
            children.remove(name)
            self.cache.set_directory_list(parent, children)

    def _evict_cache_if_needed(self):
        files = []
        total_size = 0

        for root, _, filenames in os.walk(self.cache_dir):
            for f in filenames:
                full_path = os.path.join(root, f)
                stat_info = os.stat(full_path)
                rel_path = "/" + os.path.relpath(full_path, self.cache_dir)
                if rel_path in self.dirty_files:
                    continue

                files.append({
                    'path': full_path,
                    'size': stat_info.st_size,
                    'atime': stat_info.st_atime
                })
                total_size += stat_info.st_size
        if total_size > self.max_cache_size:
            logger.info(f"Cache limit exceeded ({total_size} bytes). Cleaning up...")
            files.sort(key=lambda x: x['atime'])

            for f in files:
                if total_size <= self.max_cache_size:
                    break

                try:
                    os.remove(f['path'])
                    total_size -= f['size']
                    logger.info(f"Evicted from cache: {f['path']}")
                except Exception as e:
                    logger.error(f"Failed to evict {f['path']}: {e}")