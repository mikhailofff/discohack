import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger("Adapter")


class YandexAdapter:
    def __init__(
            self,
            token: str,
            base_url: str = "https://cloud-api.yandex.net/v1/disk",
    ):
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.headers = {"Authorization": f"OAuth {self.token}"}
        self.resource_url = f"{self.base_url}/resources"
        self.download_url = f"{self.resource_url}/download"
        self.upload_url = f"{self.resource_url}/upload"
        self.move_url = f"{self.resource_url}/move"
        self.default_timeout = (3, 15)
        # Увеличили таймаут на передачу данных до 5 минут для больших DjVu/PDF
        self.transfer_timeout = (3, 300)
        self.session = self._build_session()

    def _build_session(self) -> requests.Session:
        retry = Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET", "PUT", "POST", "DELETE"}),
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
        session = requests.Session()
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def _disk_path(self, path: str) -> str:
        if path == "/":
            return "disk:/"
        return f"disk:{path}"

    def _normalize_resource(self, item: dict) -> dict:
        return {
            "name": item["name"],
            "size": item.get("size", 0),
            "is_dir": item.get("type") == "dir",
            "path": item.get("path"),
        }

    def listdir(self, path: str) -> list[dict]:
        logger.info("Fetching directory listing: %s", path)
        response = requests.get(
            self.resource_url,
            headers=self.headers,
            params={"path": self._disk_path(path), "limit": 1000},
            timeout=self.default_timeout,
        )
        response.raise_for_status()
        items = response.json().get("_embedded", {}).get("items", [])
        return [self._normalize_resource(item) for item in items]

    def get_metadata(self, path: str) -> dict:
        response = requests.get(
            self.resource_url,
            headers=self.headers,
            params={"path": self._disk_path(path)},
            timeout=self.default_timeout,
        )
        response.raise_for_status()
        return self._normalize_resource(response.json())

    def download_file(self, path: str, local_path: str) -> None:
        """Потоковое скачивание файла напрямую на диск."""
        logger.info("Streaming download: %s -> %s", path, local_path)

        response = requests.get(
            self.download_url,
            headers=self.headers,
            params={"path": self._disk_path(path)},
            timeout=self.default_timeout,
        )
        response.raise_for_status()
        href = response.json()["href"]

        with self.session.get(href, stream=True, timeout=self.transfer_timeout) as r:
            r.raise_for_status()
            with open(local_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):  # Чанки по 1 МБ
                    if chunk:
                        f.write(chunk)

    def write_file(self, path: str, data_stream) -> None:
        """Загрузка файла в облако. data_stream может быть bytes или открытый файл."""
        logger.info("Uploading: %s", path)

        response = requests.get(
            self.upload_url,
            headers=self.headers,
            params={"path": self._disk_path(path), "overwrite": "true"},
            timeout=self.default_timeout,
        )
        response.raise_for_status()
        href = response.json()["href"]

        upload_response = self.session.put(
            href,
            data=data_stream,
            headers={"Content-Type": "application/octet-stream"},
            timeout=self.transfer_timeout,
        )
        upload_response.raise_for_status()

    def mkdir(self, path: str) -> None:
        response = requests.put(
            self.resource_url,
            headers=self.headers,
            params={"path": self._disk_path(path)},
            timeout=self.default_timeout,
        )
        response.raise_for_status()

    def delete(self, path: str) -> None:
        response = requests.delete(
            self.resource_url,
            headers=self.headers,
            params={"path": self._disk_path(path), "permanently": "true"},
            timeout=self.default_timeout,
        )
        response.raise_for_status()

    def move(self, old_path: str, new_path: str) -> None:
        response = requests.post(
            f"{self.resource_url}/move",
            headers=self.headers,
            params={
                "from": self._disk_path(old_path),
                "path": self._disk_path(new_path),
                "overwrite": "true",
            },
            timeout=self.default_timeout,
        )
        response.raise_for_status()


def get_adapter(token):
    return YandexAdapter(token)