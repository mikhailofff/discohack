import logging
import requests

logger = logging.getLogger("Adapter")

class YandexAdapter:
    def __init__(self, token: str, base_url: str = "https://cloud-api.yandex.net/v1/disk"):
        self.token = token
        self.base_url = base_url
    
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
        result = []
        for item in items:
            result.append({
                "name": item["name"],
                "size": item.get("size", 0),
                "is_dir": item.get("type") == "dir",
                "path": item.get("path"),
            }
        )
        return result
    
    def get_metadata(self, path: str) -> dict:
        raise NotImplementedError

    def read_file(self, path: str) -> bytes:
        raise NotImplementedError

    def create_file(self, path: str) -> None:
        raise NotImplementedError

    def write_file(self, path: str, data: bytes) -> None:
        raise NotImplementedError

    def mkdir(self, path: str) -> None:
        raise NotImplementedError

    def delete(self, path: str) -> None:
        raise NotImplementedError

    def move(self, old_path: str, new_path: str) -> None:
        raise NotImplementedError
    
    def _headers(self) -> dict:
        return {
           "Authorization": f"OAuth {self.token}",
        }  
    
    def _disk_path(self, path: str) -> str:
        if path == "/":
            return "disk:/"
        return f"disk:{path}"
    
    def _resource_url(self) -> str:
        return f"{self.base_url}/resources"

    
# def get_remote_files():
#     logger.info("Fetching files from Yandex.Disk (Mock)...")
#     return [
#         {'name': 'document.pdf', 'size': 1024500},
#         {'name': 'photo.jpg', 'size': 5400300},
#         {'name': 'notes.txt', 'size': 450}
#     ]

# def download_file_content(path):
#     return b"Real data from Yandex will be here soon!"

# def get_file_content(path):
#     return f"This is real-time simulated content for {path}".encode()