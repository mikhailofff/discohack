import time
import stat
import logging
import os


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Cache")

class MetadataCache:
    def __init__(self, dir_ttl=10, file_ttl=300):
        self.dir_ttl = dir_ttl
        self.file_ttl = file_ttl
        self._nodes = {}
        self._directory_contents = {}
        self.current_uid = os.getuid()
        self.current_gid = os.getgid()

    def set_node(self, path, size, is_dir=False):
        mode = (stat.S_IFDIR | 0o755) if is_dir else (stat.S_IFREG | 0o644)
        now = time.time()
        attrs = {
            'st_mode': mode,
            'st_nlink': 2 if is_dir else 1,
            'st_size': size,
            'st_mtime': now,
            'st_atime': now,
            'st_ctime': now,
            'st_uid': self.current_uid,
            'st_gid': self.current_gid,
        }

        self._nodes[path] = {
            'attrs': attrs,
            'expires': time.time() + self.file_ttl
        }
        logger.info(f"SET node cache: {path}")

    def get_attrs(self, path):
        node = self._nodes.get(path)
        if node and time.time() < node['expires']:
            logger.info(f"GET node cache (HIT): {path}")
            return node['attrs']

        if node:
            logger.info(f"GET node cache (EXPIRED): {path}")
            del self._nodes[path]
        return None

    def set_directory_list(self, path, file_names):
        self._directory_contents[path] = {
            'names': file_names,
            'expires': time.time() + self.dir_ttl
        }
        logger.info(f"SET dir list cache: {path}")

    def get_directory_list(self, path):
        content = self._directory_contents.get(path)
        if content and time.time() < content['expires']:
            logger.info(f"GET dir list cache (HIT): {path}")
            return content['names']

        if content:
            logger.info(f"GET dir list cache (EXPIRED): {path}")
            del self._directory_contents[path]
        return None

    def invalidate(self, path):
        self._nodes.pop(path, None)
        parent = os.path.dirname(path)
        self._directory_contents.pop(parent, None)
        logger.info(f"INVALIDATE: {path}")