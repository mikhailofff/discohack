import fuse
import os
import errno
import logging
import adapter
from cache import MetadataCache

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Engine")


class CloudFUSE(fuse.Operations):
    def __init__(self):
        self.cache = MetadataCache()
        self.cache.set_node('/', 4096, is_dir=True)

        files = adapter.get_remote_files()
        file_names = []
        for f in files:
            name = f['name']
            path = f'/{name}'
            self.cache.set_node(path, size=f['size'], is_dir=False)
            file_names.append(name)

        self.cache.set_directory_list('/', file_names)

    def getattr(self, path, fh=None):
        attrs = self.cache.get_attrs(path)
        if attrs:
            return attrs

        if path == '/':
            self.cache.set_node('/', 4096, is_dir=True)
            return self.cache.get_attrs('/')
        raise fuse.FuseOSError(errno.ENOENT)

    def readdir(self, path, fh):
        dirents = ['.', '..']

        cached_list = self.cache.get_directory_list(path)

        if cached_list is None:
            logger.info(f"Cache expired for {path}, refreshing from adapter...")
            if path == '/':
                remote_files = adapter.get_remote_files()
                file_names = [f['name'] for f in remote_files]
                for f in remote_files:
                    self.cache.set_node(f"/{f['name']}", size=f['size'], is_dir=False)
                self.cache.set_directory_list('/', file_names)
                cached_list = file_names
            else:
                cached_list = []

        dirents.extend(cached_list)
        for r in dirents:
            yield r

    def read(self, path, size, offset, fh):
        logger.info(f"READ: {path} | Offset: {offset} | Size: {size}")

        if path == '/test.txt':
            full_content = b"This is content from your CloudBridge Core simulation!\n"
            return full_content[offset:offset + size]
        return b""

    def create(self, path, mode, fi=None):
        logger.info(f"CREATE: {path}")
        self.cache.set_node(path, size=0, is_dir=False)
        parent = "/"
        current_files = self.cache.get_directory_list(parent) or []
        new_name = path.lstrip('/')
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
        current_attrs = self.cache.get_attrs(path)
        new_size = max(current_attrs['st_size'], offset + len(data))
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
            content = adapter.get_file_content(path)
            return content[offset:offset + size]
        except AttributeError:
            # Если в адаптере еще нет метода, отдаем заглушку,
            # но уже для любого файла, чтобы система не падала
            dummy_data = f"Content of {path}\n".encode() * 100
            return dummy_data[offset:offset + size]

    def mkdir(self, path, mode):
        logger.info(f"MKDIR: {path}")
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
        # Тут должна быть проверка, пуста ли папка в кэше
        # Удаляем из кэша ноду и запись в родительском списке
        self._remove_from_parent_list(path)
        return 0

    def unlink(self, path):
        """Удаление файла"""
        logger.info(f"UNLINK: {path}")
        self._remove_from_parent_list(path)
        # В реальности здесь: adapter.delete_file(path)
        return 0

    def rename(self, old, new):
        logger.info(f"RENAME: from {old} to {new}")
        attrs = self.cache.get_attrs(old)
        if attrs:
            is_dir = (attrs['st_mode'] & 0o40000) != 0
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
