from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response, status

from app.core.dependencies import get_current_user
from app.database.unit_of_work import UnitOfWork, get_unit_of_work
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.presentation_folder import (
    BreadcrumbResponse,
    FolderCreateRequest,
    FolderResponse,
    FolderUpdateRequest,
)
from app.services.presentation_folder_service import PresentationFolderService

folders_router = APIRouter(prefix="/folders", tags=["Presentation Folders"])


@folders_router.get("", response_model=APIResponse[list[FolderResponse]])
async def list_folders(
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[list[FolderResponse]]:
    service = PresentationFolderService(uow)
    folders = await service.list_folders(owner_id=user.id)
    return APIResponse(data=[FolderResponse(**folder) for folder in folders])


@folders_router.post(
    "",
    response_model=APIResponse[FolderResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_folder(
    request: FolderCreateRequest,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[FolderResponse]:
    service = PresentationFolderService(uow)
    folder = await service.create_folder(
        name=request.name,
        owner_id=user.id,
        parent_id=request.parent_id,
    )
    return APIResponse(
        data=FolderResponse(**service._serialize(folder)),
        message="Folder created successfully",
    )


@folders_router.get(
    "/{folder_id}/breadcrumbs",
    response_model=APIResponse[list[BreadcrumbResponse]],
)
async def get_folder_breadcrumbs(
    folder_id: uuid.UUID,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[list[BreadcrumbResponse]]:
    service = PresentationFolderService(uow)
    crumbs = await service.get_breadcrumbs(folder_id, owner_id=user.id)
    return APIResponse(data=[BreadcrumbResponse(**crumb) for crumb in crumbs])


@folders_router.patch(
    "/{folder_id}",
    response_model=APIResponse[FolderResponse],
)
async def update_folder(
    folder_id: uuid.UUID,
    request: FolderUpdateRequest,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[FolderResponse]:
    service = PresentationFolderService(uow)
    folder = await service.update_folder(
        folder_id=folder_id,
        owner_id=user.id,
        name=request.name,
        parent_id=request.parent_id,
    )
    return APIResponse(data=FolderResponse(**service._serialize(folder)))


@folders_router.delete(
    "/{folder_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_folder(
    folder_id: uuid.UUID,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> Response:
    service = PresentationFolderService(uow)
    await service.delete_folder(folder_id=folder_id, owner_id=user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
