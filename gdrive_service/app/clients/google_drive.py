from typing import Any

import httpx
from fastapi import HTTPException, status


GOOGLE_DRIVE_API_URL = "https://www.googleapis.com/drive/v3"
GOOGLE_DRIVE_FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"


class GoogleDriveClient:
    def __init__(self, access_token: str) -> None:
        self._headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

    async def create_folder(self, name: str, parent_id: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {
            "name": name,
            "mimeType": GOOGLE_DRIVE_FOLDER_MIME_TYPE,
        }
        if parent_id:
            body["parents"] = [parent_id]

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{GOOGLE_DRIVE_API_URL}/files",
                headers=self._headers,
                json=body,
                params={"fields": "id,name,mimeType,parents,webViewLink"},
            )

        if response.is_error:
            raise google_drive_error(response)

        return response.json()

    async def list_files(self, parent_id: str = "root", page_size: int = 100) -> dict[str, Any]:
        query = f"'{parent_id}' in parents and trashed = false"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{GOOGLE_DRIVE_API_URL}/files",
                headers=self._headers,
                params={
                    "q": query,
                    "pageSize": page_size,
                    "fields": (
                        "nextPageToken,"
                        "files(id,name,mimeType,size,modifiedTime,parents,webViewLink,iconLink)"
                    ),
                    "orderBy": "folder,name",
                },
            )

        if response.is_error:
            raise google_drive_error(response)

        return response.json()


def google_drive_error(response: httpx.Response) -> HTTPException:
    try:
        payload = response.json()
    except ValueError:
        payload = {"error": {"message": response.text}}

    error = payload.get("error", {})
    message = error.get("message") or "Google Drive API error"

    status_map = {
        400: status.HTTP_400_BAD_REQUEST,
        401: status.HTTP_401_UNAUTHORIZED,
        403: status.HTTP_403_FORBIDDEN,
        404: status.HTTP_404_NOT_FOUND,
        409: status.HTTP_409_CONFLICT,
        429: status.HTTP_429_TOO_MANY_REQUESTS,
    }

    return HTTPException(
        status_code=status_map.get(response.status_code, status.HTTP_502_BAD_GATEWAY),
        detail={
            "message": message,
            "google_status_code": response.status_code,
            "google_error": error,
        },
    )
