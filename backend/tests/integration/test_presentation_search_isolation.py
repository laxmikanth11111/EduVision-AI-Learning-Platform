"""Cross-user isolation for presentation search/listing.

`PresentationRepository.search()` builds its WHERE clause incrementally. A
non-admin caller who supplies no `user_id` used to skip the owner predicate
entirely, which returned every presentation in the table regardless of owner.

These tests pin the fail-closed contract at the repository layer, which is the
layer that actually builds the query.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.presentation import Presentation
from app.repositories.presentation_repository import PresentationRepository


@pytest_asyncio.fixture
async def owned_presentations(db_session: AsyncSession):
    """Two presentations owned by two different users.

    The integration session is shared, so public ids are made unique per test
    instead of reusing literals that would collide with earlier rows.
    """
    owner_a = uuid.uuid4()
    owner_b = uuid.uuid4()
    token = uuid.uuid4().hex[:10]
    id_a = f"pres_{token}_a"
    id_b = f"pres_{token}_b"
    for public_id, owner in ((id_a, owner_a), (id_b, owner_b)):
        db_session.add(
            Presentation(
                public_id=public_id,
                title=f"Owned by {public_id}",
                owner_id=owner,
                status="draft",
                visibility="private",
            )
        )
    await db_session.commit()
    return SimpleNamespace(id_a=id_a, id_b=id_b, owner_a=owner_a, owner_b=owner_b)


async def test_search_without_user_id_returns_nothing(db_session, owned_presentations):
    """The regression: no owner scope must mean no rows, not all rows."""
    repo = PresentationRepository(db_session)

    rows, total = await repo.search(user_id=None, is_admin=False)

    assert total == 0
    assert rows == []


async def test_search_scoped_to_owner_only_returns_own(
    db_session, owned_presentations
):
    repo = PresentationRepository(db_session)

    rows, total = await repo.search(user_id=owned_presentations.owner_a, is_admin=False)

    assert total == 1
    assert [r.public_id for r in rows] == [owned_presentations.id_a]


async def test_search_admin_scope_still_sees_everything(
    db_session, owned_presentations
):
    """Fixing the fail-closed path must not break the legitimate admin path."""
    repo = PresentationRepository(db_session)

    _rows, total = await repo.search(user_id=None, is_admin=True)

    assert total >= 2
    found = {r.public_id for r in _rows}
    assert {owned_presentations.id_a, owned_presentations.id_b} <= found


async def test_search_excludes_soft_deleted_for_owner(
    db_session, owned_presentations
):
    repo = PresentationRepository(db_session)
    victim = await repo.get_by_public_id(owned_presentations.id_a)
    assert victim is not None
    victim.soft_delete()
    await db_session.commit()

    rows, total = await repo.search(user_id=owned_presentations.owner_a, is_admin=False)

    assert total == 0
    assert rows == []


@pytest.mark.parametrize("bad_status", ["not-a-status", "DRAFT", "deleted", "draft "])
async def test_search_rejects_unknown_status(
    db_session, owned_presentations, bad_status
):
    """Non-empty, non-allowlisted status values are rejected, not silently ignored."""
    from app.core.exceptions import ValidationError

    repo = PresentationRepository(db_session)

    with pytest.raises(ValidationError):
        await repo.search(
            user_id=owned_presentations.owner_a,
            status=bad_status,
            is_admin=False,
        )


async def test_search_empty_status_is_treated_as_no_filter(
    db_session, owned_presentations
):
    """An empty string means 'do not filter', so it must not raise."""
    repo = PresentationRepository(db_session)

    rows, total = await repo.search(
        user_id=owned_presentations.owner_a, status="", is_admin=False
    )

    assert total == 1
    assert [r.public_id for r in rows] == [owned_presentations.id_a]
