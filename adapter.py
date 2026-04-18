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
        self.publish_url = f"{self.resource_url}/publish"
        self.unpublish_url = f"{self.resource_url}/unpublish"
        self.default_timeout = (3, 10)
        self.transfer_timeout = (3, 30)
        self.session = self._build_session()

    def listdir(self, path: str) -> list[dict]:
        logger.info("Fetching directory listing for %s", path)

        response = requests.get(
            self.resource_url,
            headers=self.headers,
            params={
                "path": self._disk_path(path),
                "limit": 1000,
            },
            timeout=self.default_timeout,
        )
        response.raise_for_status()

        data = response.json()
        embedded = data.get("_embedded", {})
        items = embedded.get("items", [])
        return [self._normalize_resource(item) for item in items]

    def get_metadata(self, path: str) -> dict:
        logger.info("Fetching metadata for %s", path)

        response = requests.get(
            self.resource_url,
            headers=self.headers,
            params={"path": self._disk_path(path)},
            timeout=self.default_timeout,
        )
        response.raise_for_status()

        return self._normalize_resource(response.json())

    def read_file(self, path: str) -> bytes:
        logger.info("Reading file %s", path)

        response = requests.get(
            self.download_url,
            headers=self.headers,
            params={"path": self._disk_path(path)},
            timeout=self.default_timeout,
        )
        response.raise_for_status()

        href = response.json()["href"]
        download_response = self.session.get(href, timeout=self.transfer_timeout)
        download_response.raise_for_status()
        return download_response.content

    def create_file(self, path: str) -> None:
        logger.info("Creating empty file %s", path)
        self.write_file(path, b"")


    def write_file(self, path: str, data) -> None:
        logger.info("Uploading file %s", path)

        response = requests.get(
            self.upload_url,
            headers=self.headers,
            params={
                "path": self._disk_path(path),
                "overwrite": "true",
            },
            timeout=self.default_timeout,
        )
        response.raise_for_status()
        href = response.json()["href"]
        upload_response = self.session.put(
            href,
            data=data,
            headers={"Content-Type": "application/octet-stream"},
            timeout=self.transfer_timeout,
        )
        upload_response.raise_for_status()

    def mkdir(self, path: str) -> None:
        logger.info("Creating directory %s", path)

        response = requests.put(
            self.resource_url,
            headers=self.headers,
            params={"path": self._disk_path(path)},
            timeout=self.default_timeout,
        )
        response.raise_for_status()

    def delete(self, path: str) -> None:
        logger.info("Deleting resource %s", path)

        response = requests.delete(
            self.resource_url,
            headers=self.headers,
            params={
                "path": self._disk_path(path),
                "permanently": "true",
            },
            timeout=self.default_timeout,
        )
        response.raise_for_status()

    def move(self, old_path: str, new_path: str) -> None:
        logger.info("Moving resource from %s to %s", old_path, new_path)

        response = requests.post(
            self.move_url,
            headers=self.headers,
            params={
                "from": self._disk_path(old_path),
                "path": self._disk_path(new_path),
                "overwrite": "true",
            },
            timeout=self.default_timeout,
        )
        response.raise_for_status()

    def get_disk_info(self) -> dict:
        logger.info("Fetching disk info")

        response = requests.get(
            self.base_url,
            headers=self.headers,
            timeout=self.default_timeout,
        )
        response.raise_for_status()
        return response.json()

    def publish(self, path: str) -> dict:
        logger.info("Publishing resource %s", path)

        response = self.session.put(
            self.publish_url,
            headers=self.headers,
            params={"path": self._disk_path(path)},
            timeout=self.default_timeout,
        )
        response.raise_for_status()

        return self.get_public_info(path)

    def get_public_link(self, path: str) -> str:
        logger.info("Fetching public link for %s", path)

        public_info = self.get_public_info(path)
        public_url = public_info.get("public_url")
        if not public_url:
            raise RuntimeError(f"Resource {path} is not published")
        return public_url

    def get_public_info(self, path: str) -> dict:
        logger.info("Fetching public info for %s", path)

        response = self.session.get(
            self.resource_url,
            headers=self.headers,
            params={
                "path": self._disk_path(path),
                "fields": "name,path,type,size,public_key,public_url",
            },
            timeout=self.default_timeout,
        )
        response.raise_for_status()
        return response.json()

    def unpublish(self, path: str) -> None:
        logger.info("Unpublishing resource %s", path)

        response = self.session.put(
            self.unpublish_url,
            headers=self.headers,
            params={"path": self._disk_path(path)},
            timeout=self.default_timeout,
        )
        response.raise_for_status()

    def _build_session(self) -> requests.Session:
        retry = Retry(
            total=3,
            backoff_factor=0.3,
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


def get_adapter(token):
    return YandexAdapter(token)
