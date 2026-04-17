from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_google_access_token
from app.clients.google_drive import GoogleDriveClient
from app.schemas.resources import CreateFolderRequest


router = APIRouter(prefix="/drive", tags=["drive"])


@router.post("/folders", status_code=status.HTTP_201_CREATED)
async def create_folder(
    payload: CreateFolderRequest,
    access_token: Annotated[str, Depends(get_google_access_token)],
):
    client = GoogleDriveClient(access_token)
    return await client.create_folder(payload.name, payload.parent_id)


@router.get("/files")
async def list_files(
    access_token: Annotated[str, Depends(get_google_access_token)],
    parent_id: str = "root",
    page_size: int = 100,
):
    client = GoogleDriveClient(access_token)
    return await client.list_files(parent_id, page_size)
