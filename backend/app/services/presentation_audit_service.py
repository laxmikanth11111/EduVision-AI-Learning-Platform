from __future__ import annotations

import uuid
from typing import Any

from app.core.logging import get_logger
from app.database.unit_of_work import UnitOfWork
from app.models.presentation_audit_log import PresentationAuditLog
from app.repositories.presentation_audit_log_repository import PresentationAuditLogRepository
from shared.constants import PresentationAction

logger = get_logger(__name__)


class PresentationAuditService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        self._repo = PresentationAuditLogRepository(uow.session)

    async def log(
        self,
        presentation_id: uuid.UUID,
        action: PresentationAction,
        actor_id: uuid.UUID | None = None,
        entity_type: str = "presentation",
        entity_id: uuid.UUID | None = None,
        details: dict[str, Any] | None = None,
    ) -> PresentationAuditLog:
        entry = await self._repo.create(
            presentation_id=presentation_id,
            action=action.value,
            actor_id=actor_id,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details,
        )
        logger.info(
            "presentation_audit_logged",
            presentation_id=str(presentation_id),
            action=action.value,
            actor_id=str(actor_id) if actor_id else None,
        )
        return entry

    async def list_logs(
        self,
        presentation_id: uuid.UUID,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        logs = await self._repo.list_for_presentation(presentation_id, limit=limit)
        return [self._serialize(entry) for entry in logs]

    @staticmethod
    def _serialize(entry: PresentationAuditLog) -> dict[str, Any]:
        return {
            "id": entry.id,
            "presentation_id": entry.presentation_id,
            "actor_id": entry.actor_id,
            "action": entry.action,
            "entity_type": entry.entity_type,
            "entity_id": entry.entity_id,
            "details": entry.details,
            "created_at": entry.created_at,
        }
