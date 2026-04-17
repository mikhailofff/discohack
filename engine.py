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
        # Если файла нет в памяти, инициализируем буфер
        if path not in self.data_buffer:
            try:
                # Пытаемся подтянуть существующий контент, если это дозапись
                self.data_buffer[path] = bytearray(self.adapter.read_file(path))
            except Exception:
                self.data_buffer[path] = bytearray()

        buf = self.data_buffer[path]
        # Расширяем буфер, если пишем за пределы
        if offset + len(data) > len(buf):
            buf.extend(b'\x00' * (offset + len(data) - len(buf)))

        # Пишем в память, а НЕ в облако
        buf[offset:offset + len(data)] = data
        self.cache.set_node(path, size=len(buf), is_dir=False)
        return len(data)

    def release(self, path, fh):
        # Вот теперь release важен! Когда файл закрывается,
        # мы один раз отправляем накопленный буфер в облако.
        if path in self.data_buffer:
            logger.info(f"RELEASE: Syncing {path} to Yandex Disk...")
            try:
                self.adapter.write_file(path, bytes(self.data_buffer[path]))
                # Очищаем память после успешной загрузки
                del self.data_buffer[path]
            except Exception as e:
                logger.error(f"Failed to sync {path}: {e}")
        return 0

    def read(self, path, size, offset, fh):
        # Если файла нет в памяти, качаем его целиком ОДИН раз
        if path not in self.data_buffer:
            logger.info(f"READ (Buffer miss): Downloading {path}...")
            self.data_buffer[path] = bytearray(self.adapter.read_file(path))

        # Отдаем кусок из оперативной памяти — это мгновенно
        return bytes(self.data_buffer[path][offset:offset + size])

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
