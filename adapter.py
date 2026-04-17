import logging

import requests

logger = logging.getLogger("Adapter")

YANDEX_TOKEN = "y0__xCy3YiTBBjywkAg0vWRjxcmgUEIpRLMYtFgA032DcT0p_rw2w"


class YandexAdapter:
    def __init__(
        self,
        token: str,
        base_url: str = "https://cloud-api.yandex.net/v1/disk",
    ):
        self.token = token
        self.base_url = base_url.rstrip("/")

    def listdir(self, path: str) -> list[dict]:
        logger.info("Fetching directory listing for %s", path)

        response = requests.get(
            self._resource_url(),
            headers=self._headers(),
            params={
                "path": self._disk_path(path),
                "limit": 1000,
            },
            timeout=10,
        )
        response.raise_for_status()

        data = response.json()
        embedded = data.get("_embedded", {})
        items = embedded.get("items", [])
        return [self._normalize_resource(item) for item in items]

    def get_metadata(self, path: str) -> dict:
        logger.info("Fetching metadata for %s", path)

        response = requests.get(
            self._resource_url(),
            headers=self._headers(),
            params={"path": self._disk_path(path)},
            timeout=10,
        )
        response.raise_for_status()

        return self._normalize_resource(response.json())

    def read_file(self, path: str) -> bytes:
        logger.info("Reading file %s", path)

        response = requests.get(
            self._download_url(),
            headers=self._headers(),
            params={"path": self._disk_path(path)},
            timeout=10,
        )
        response.raise_for_status()

        href = response.json()["href"]
        download_response = requests.get(href, timeout=30)
        download_response.raise_for_status()
        return download_response.content

    def create_file(self, path: str) -> None:
        logger.info("Creating empty file %s", path)
        self.write_file(path, b"")

    def write_file(self, path: str, data: bytes) -> None:
        logger.info("Uploading file %s", path)

        response = requests.get(
            self._upload_url(),
            headers=self._headers(),
            params={
                "path": self._disk_path(path),
                "overwrite": "true",
            },
            timeout=10,
        )
        response.raise_for_status()

        href = response.json()["href"]
        upload_response = requests.put(href, data=data, timeout=30)
        upload_response.raise_for_status()

    def mkdir(self, path: str) -> None:
        logger.info("Creating directory %s", path)

        response = requests.put(
            self._resource_url(),
            headers=self._headers(),
            params={"path": self._disk_path(path)},
            timeout=10,
        )
        response.raise_for_status()

    def delete(self, path: str) -> None:
        logger.info("Deleting resource %s", path)

        response = requests.delete(
            self._resource_url(),
            headers=self._headers(),
            params={
                "path": self._disk_path(path),
                "permanently": "true",
            },
            timeout=10,
        )
        response.raise_for_status()

    def move(self, old_path: str, new_path: str) -> None:
        logger.info("Moving resource from %s to %s", old_path, new_path)

        response = requests.post(
            self._move_url(),
            headers=self._headers(),
            params={
                "from": self._disk_path(old_path),
                "path": self._disk_path(new_path),
                "overwrite": "true",
            },
            timeout=10,
        )
        response.raise_for_status()

    def get_disk_info(self) -> dict:
        logger.info("Fetching disk info")

        response = requests.get(
            self.base_url,
            headers=self._headers(),
            timeout=10,
        )
        response.raise_for_status()
        return response.json()

    def _headers(self) -> dict:
        return {"Authorization": f"OAuth {self.token}"}

    def _disk_path(self, path: str) -> str:
        if path == "/":
            return "disk:/"
        return f"disk:{path}"

    def _resource_url(self) -> str:
        return f"{self.base_url}/resources"

    def _download_url(self) -> str:
        return f"{self._resource_url()}/download"

    def _upload_url(self) -> str:
        return f"{self._resource_url()}/upload"

    def _move_url(self) -> str:
        return f"{self._resource_url()}/move"

    def _normalize_resource(self, item: dict) -> dict:
        return {
            "name": item["name"],
            "size": item.get("size", 0),
            "is_dir": item.get("type") == "dir",
            "path": item.get("path"),
        }


def get_adapter() -> YandexAdapter:
    if not YANDEX_TOKEN:
        raise RuntimeError(
            "Set YANDEX_TOKEN in adapter.py before starting the FUSE adapter."
        )
    return YandexAdapter(token=YANDEX_TOKEN)
