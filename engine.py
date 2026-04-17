import fuse
import os
import errno
import logging
import adapter
import stat
from cache import MetadataCache

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Engine")


class CloudFUSE(fuse.Operations):
    def __init__(self):
        self.adapter = adapter.get_adapter()
        self.cache = MetadataCache()
        self.cache.set_node('/', 4096, is_dir=True)

        files = self.adapter.listdir('/')
        file_names = []
        for f in files:
            name = f['name']
            path = f'/{name}'
            self.cache.set_node(path, size=f['size'], is_dir=f.get('is_dir', False))
            file_names.append(name)

        self.cache.set_directory_list('/', file_names)

    def getattr(self, path, fh=None):
        attrs = self.cache.get_attrs(path)
        if attrs:
            return attrs

        if path == '/':
            self.cache.set_node('/', 4096, is_dir=True)
            return self.cache.get_attrs('/')

        try:
            metadata = self.adapter.get_metadata(path)
        except Exception as exc:
            logger.error("GETATTR failed for %s: %s", path, exc)
            raise fuse.FuseOSError(errno.ENOENT)

        self.cache.set_node(
            path,
            size=metadata['size'],
            is_dir=metadata.get('is_dir', False),
        )
        return self.cache.get_attrs(path)

        raise fuse.FuseOSError(errno.ENOENT)

    def readdir(self, path, fh):
        dirents = ['.', '..']

        cached_list = self.cache.get_directory_list(path)

        if cached_list is None:
            logger.info(f"Cache expired for {path}, refreshing from adapter...")
            remote_files = self.adapter.listdir(path)
            file_names = [f['name'] for f in remote_files]
            for f in remote_files:
                child_path = path.rstrip('/')
                child_path = f"{child_path}/{f['name']}" if child_path else f"/{f['name']}"
                self.cache.set_node(
                    child_path,
                    size=f['size'],
                    is_dir=f.get('is_dir', False),
                )
            self.cache.set_directory_list(path, file_names)
            cached_list = file_names

        dirents.extend(cached_list)
        for r in dirents:
            yield r

    def create(self, path, mode, fi=None):
        logger.info(f"CREATE: {path}")
        self.adapter.create_file(path)
        self.cache.set_node(path, size=0, is_dir=False)
        parent = os.path.dirname(path) or "/"
        current_files = self.cache.get_directory_list(parent) or []
        new_name = os.path.basename(path)
        if new_name not in current_files:
            current_files.append(new_name)
            self.cache.set_directory_list(parent, current_files)
        return 0

    def truncate(self, path, length, fh=None):
        logger.info(f"TRUNCATE: {path} to {length}")
        self.cache.set_node(path, size=length, is_dir=False)
        return 0

    def write(self, path, data, offset, fh):
        logger.info(f"WRITE: {path} | Offset: {offset} | Length: {len(data)}")
        current_content = b""
        try:
            current_content = self.adapter.read_file(path)
        except Exception:
            logger.info("WRITE: starting new content buffer for %s", path)

        if offset > len(current_content):
            current_content += b"\x00" * (offset - len(current_content))
        new_content = current_content[:offset] + data
        if offset + len(data) < len(current_content):
            new_content += current_content[offset + len(data):]

        self.adapter.write_file(path, new_content)
        new_size = len(new_content)
        self.cache.set_node(path, size=new_size, is_dir=False)
        return len(data)

    def release(self, path, fh):
        logger.info(f"RELEASE (Close): {path}")
        return 0

    def read(self, path, size, offset, fh):
        logger.info(f"READ: {path} | Offset: {offset} | Size: {size}")
        attrs = self.cache.get_attrs(path)
        if not attrs:
            raise fuse.FuseOSError(errno.ENOENT)
        try:
            content = self.adapter.read_file(path)
            return content[offset:offset + size]
        except Exception as exc:
            logger.error("READ failed for %s: %s", path, exc)
            raise fuse.FuseOSError(errno.EIO)

    def mkdir(self, path, mode):
        logger.info(f"MKDIR: {path}")
        self.adapter.mkdir(path)
        self.cache.set_node(path, size=4096, is_dir=True)
        parent_path = os.path.dirname(path)
        dir_name = os.path.basename(path)

        children = self.cache.get_directory_list(parent_path) or []
        if dir_name not in children:
            children.append(dir_name)
            self.cache.set_directory_list(parent_path, children)
        return 0

    def rmdir(self, path):
        """Удаление пустой папки"""
        logger.info(f"RMDIR: {path}")
        self.adapter.delete(path)
        # Тут должна быть проверка, пуста ли папка в кэше
        # Удаляем из кэша ноду и запись в родительском списке
        self._remove_from_parent_list(path)
        return 0

    def unlink(self, path):
        """Удаление файла"""
        logger.info(f"UNLINK: {path}")
        self.adapter.delete(path)
        self._remove_from_parent_list(path)
        return 0

    def rename(self, old, new):
        logger.info(f"RENAME: from {old} to {new}")
        self.adapter.move(old, new)
        attrs = self.cache.get_attrs(old)
        if attrs:
            is_dir = stat.S_ISDIR(attrs['st_mode'])
            self.cache.set_node(new, size=attrs['st_size'], is_dir=is_dir)

        self._remove_from_parent_list(old)
        parent_new = os.path.dirname(new)
        name_new = os.path.basename(new)
        children = self.cache.get_directory_list(parent_new) or []
        if name_new not in children:
            children.append(name_new)
            self.cache.set_directory_list(parent_new, children)

        return 0

    def _remove_from_parent_list(self, path):
        parent_path = os.path.dirname(path)
        name = os.path.basename(path)
        children = self.cache.get_directory_list(parent_path) or []
        if name in children:
            children.remove(name)
            self.cache.set_directory_list(parent_path, children)
