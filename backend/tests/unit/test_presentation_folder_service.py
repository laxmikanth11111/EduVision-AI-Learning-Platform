from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import ConflictError, NotFoundError
from app.services.presentation_folder_service import PresentationFolderService

pytestmark = pytest.mark.asyncio

TEST_OWNER = uuid.uuid4()
OTHER_OWNER = uuid.uuid4()


@pytest.fixture
def mock_uow() -> MagicMock:
    uow = MagicMock()
    uow.session = AsyncMock()
    uow.flush = AsyncMock()
    return uow


@pytest.fixture
def folder_service(mock_uow: MagicMock) -> PresentationFolderService:
    service = PresentationFolderService(mock_uow)
    return service


def _make_folder(**overrides: dict) -> MagicMock:
    now = datetime.now(UTC)
    folder = MagicMock()
    folder.id = overrides.get("id", uuid.uuid4())
    folder.name = overrides.get("name", "Folder")
    folder.owner_id = overrides.get("owner_id", TEST_OWNER)
    folder.parent_id = overrides.get("parent_id")
    folder.created_at = overrides.get("created_at", now)
    folder.updated_at = overrides.get("updated_at", now)
    return folder


class TestCreateFolder:
    async def test_create_root_folder(
        self, folder_service: PresentationFolderService, mock_uow: MagicMock
    ) -> None:
        folder = _make_folder(name="Math", owner_id=TEST_OWNER)
        folder_service._repo.create = AsyncMock(return_value=folder)

        result = await folder_service.create_folder("Math", owner_id=TEST_OWNER)

        assert result is folder
        folder_service._repo.create.assert_awaited_once_with(
            name="Math", owner_id=TEST_OWNER, parent_id=None
        )
        mock_uow.flush.assert_awaited_once()

    async def test_create_nested_folder_validates_parent(
        self, folder_service: PresentationFolderService,
    ) -> None:
        parent = _make_folder(name="Parent", owner_id=TEST_OWNER)
        child = _make_folder(parent_id=parent.id, owner_id=TEST_OWNER)
        folder_service._repo.get = AsyncMock(return_value=parent)
        folder_service._repo.create = AsyncMock(return_value=child)

        result = await folder_service.create_folder(
            "Child", owner_id=TEST_OWNER, parent_id=parent.id
        )

        assert result is child
        folder_service._repo.create.assert_awaited_once_with(
            name="Child", owner_id=TEST_OWNER, parent_id=parent.id
        )

    async def test_create_nested_folder_missing_parent(
        self, folder_service: PresentationFolderService,
    ) -> None:
        folder_service._repo.get = AsyncMock(return_value=None)

        with pytest.raises(NotFoundError, match="Parent folder not found"):
            await folder_service.create_folder(
                "Child", owner_id=TEST_OWNER, parent_id=uuid.uuid4()
            )

    async def test_create_nested_folder_foreign_parent_is_404(
        self, folder_service: PresentationFolderService,
    ) -> None:
        parent = _make_folder(name="Parent", owner_id=OTHER_OWNER)
        folder_service._repo.get = AsyncMock(return_value=parent)

        # A foreign parent is indistinguishable from a missing one (no oracle).
        with pytest.raises(NotFoundError, match="Parent folder not found"):
            await folder_service.create_folder(
                "Child", owner_id=TEST_OWNER, parent_id=parent.id
            )


class TestUpdateFolder:
    async def test_update_name(
        self, folder_service: PresentationFolderService,
    ) -> None:
        folder = _make_folder(name="Old", owner_id=TEST_OWNER)
        folder_service._repo.get = AsyncMock(return_value=folder)

        result = await folder_service.update_folder(
            folder.id, owner_id=TEST_OWNER, name="New"
        )

        assert folder.name == "New"
        assert result is folder

    async def test_update_cannot_be_own_parent(
        self, folder_service: PresentationFolderService,
    ) -> None:
        folder = _make_folder(owner_id=TEST_OWNER)
        folder_service._repo.get = AsyncMock(return_value=folder)

        with pytest.raises(ConflictError, match="own parent"):
            await folder_service.update_folder(
                folder.id, owner_id=TEST_OWNER, parent_id=folder.id
            )

    async def test_update_detects_cycle(
        self, folder_service: PresentationFolderService,
    ) -> None:
        parent = _make_folder(name="Parent", owner_id=TEST_OWNER)
        child = _make_folder(name="Child", parent_id=parent.id, owner_id=TEST_OWNER)
        folder_service._repo.get = AsyncMock(
            side_effect=[parent, child, child]
        )

        with pytest.raises(ConflictError, match="would create a cycle"):
            await folder_service.update_folder(
                parent.id, owner_id=TEST_OWNER, parent_id=child.id
            )

    async def test_update_foreign_folder_is_404(
        self, folder_service: PresentationFolderService,
    ) -> None:
        folder = _make_folder(owner_id=OTHER_OWNER)
        folder_service._repo.get = AsyncMock(return_value=folder)

        with pytest.raises(NotFoundError, match="Folder not found"):
            await folder_service.update_folder(
                folder.id, owner_id=TEST_OWNER, name="Hacked"
            )


class TestDeleteFolder:
    async def test_delete_detaches_presentations_and_children(
        self, folder_service: PresentationFolderService, mock_uow: MagicMock
    ) -> None:
        folder = _make_folder(owner_id=TEST_OWNER)
        child = _make_folder(parent_id=folder.id, owner_id=TEST_OWNER)
        folder_service._repo.get = AsyncMock(return_value=folder)
        folder_service._repo.find_all = AsyncMock(return_value=[child])
        folder_service._repo.delete = AsyncMock()

        await folder_service.delete_folder(folder.id, owner_id=TEST_OWNER)

        assert child.parent_id is None
        folder_service._repo.delete.assert_awaited_once_with(folder.id, hard=True)
        mock_uow.flush.assert_awaited_once()

    async def test_delete_foreign_folder_is_404(
        self, folder_service: PresentationFolderService,
    ) -> None:
        folder = _make_folder(owner_id=OTHER_OWNER)
        folder_service._repo.get = AsyncMock(return_value=folder)

        with pytest.raises(NotFoundError, match="Folder not found"):
            await folder_service.delete_folder(folder.id, owner_id=TEST_OWNER)


class TestListFolders:
    async def test_list_includes_presentation_count(
        self, folder_service: PresentationFolderService,
    ) -> None:
        folder = _make_folder(name="Math", owner_id=TEST_OWNER)
        folder_service._repo.find_owned = AsyncMock(return_value=[folder])
        folder_service._repo.count_presentations = AsyncMock(return_value=3)

        result = await folder_service.list_folders(owner_id=TEST_OWNER)

        assert result[0]["id"] == folder.id
        assert result[0]["name"] == "Math"
        assert result[0]["presentation_count"] == 3


class TestBreadcrumbs:
    async def test_root_folder_breadcrumb(
        self, folder_service: PresentationFolderService,
    ) -> None:
        folder = _make_folder(name="Math", owner_id=TEST_OWNER)
        folder_service._repo.get = AsyncMock(return_value=folder)

        crumbs = await folder_service.get_breadcrumbs(folder.id, owner_id=TEST_OWNER)

        assert len(crumbs) == 1
        assert crumbs[0]["id"] == folder.id
        assert crumbs[0]["name"] == "Math"
        assert crumbs[0]["parent_id"] is None

    async def test_nested_folder_returns_root_first(
        self, folder_service: PresentationFolderService,
    ) -> None:
        root = _make_folder(name="Root", owner_id=TEST_OWNER)
        parent = _make_folder(name="Parent", parent_id=root.id, owner_id=TEST_OWNER)
        child = _make_folder(name="Child", parent_id=parent.id, owner_id=TEST_OWNER)
        folder_service._repo.get = AsyncMock(side_effect=[child, parent, root])

        crumbs = await folder_service.get_breadcrumbs(child.id, owner_id=TEST_OWNER)

        assert [crumb["name"] for crumb in crumbs] == ["Root", "Parent", "Child"]

    async def test_missing_folder(
        self, folder_service: PresentationFolderService,
    ) -> None:
        folder_service._repo.get = AsyncMock(return_value=None)

        with pytest.raises(NotFoundError, match="Folder not found"):
            await folder_service.get_breadcrumbs(uuid.uuid4(), owner_id=TEST_OWNER)

    async def test_breadcrumbs_foreign_folder_is_404(
        self, folder_service: PresentationFolderService,
    ) -> None:
        folder = _make_folder(owner_id=OTHER_OWNER)
        folder_service._repo.get = AsyncMock(return_value=folder)

        with pytest.raises(NotFoundError, match="Folder not found"):
            await folder_service.get_breadcrumbs(folder.id, owner_id=TEST_OWNER)
