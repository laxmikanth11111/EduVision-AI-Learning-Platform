from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repository import BaseRepository
from app.models.export_template import ExportTemplate


class ExportTemplateRepository(BaseRepository[ExportTemplate]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ExportTemplate)

    async def create_template(self, template: ExportTemplate) -> ExportTemplate:
        self._session.add(template)
        await self._session.flush()
        return template

    async def get_by_key(self, template_key: str) -> ExportTemplate | None:
        stmt = select(ExportTemplate).where(
            ExportTemplate.template_key == template_key,
            ExportTemplate.is_active.is_(True),
            ExportTemplate.deleted_at.is_(None),
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_default(self, kind: str, format: str) -> ExportTemplate | None:
        stmt = (
            select(ExportTemplate)
            .where(
                ExportTemplate.kind == kind,
                ExportTemplate.format == format,
                ExportTemplate.is_default.is_(True),
                ExportTemplate.is_active.is_(True),
                ExportTemplate.deleted_at.is_(None),
            )
            .order_by(ExportTemplate.created_at.asc())
        )
        res = await self._session.execute(stmt)
        tpl = res.scalar_one_or_none()
        if tpl:
            return tpl

        # Fallback to any active template with template_key='standard'
        return await self.get_by_key("standard")

    async def list_active_templates(
        self, kind: str | None = None, format: str | None = None
    ) -> list[ExportTemplate]:
        stmt = select(ExportTemplate).where(
            ExportTemplate.is_active.is_(True), ExportTemplate.deleted_at.is_(None)
        )
        if kind:
            stmt = stmt.where(ExportTemplate.kind == kind)
        if format:
            stmt = stmt.where(ExportTemplate.format == format)

        stmt = stmt.order_by(ExportTemplate.name.asc())
        res = await self._session.execute(stmt)
        return list(res.scalars().all())
