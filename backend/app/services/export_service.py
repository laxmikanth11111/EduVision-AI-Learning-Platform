from __future__ import annotations

import io
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError
from app.database.unit_of_work import UnitOfWork
from app.models.export_file import ExportFile
from app.models.export_job import ExportJob
from app.models.presentation import Presentation
from app.repositories.export_file_repository import ExportFileRepository
from app.repositories.export_job_repository import ExportJobRepository
from app.repositories.export_template_repository import ExportTemplateRepository
from app.schemas.export import ExportContentData, ExportOptions
from app.services.exporters.exporter_factory import ExporterFactory
from app.storage.base import StorageBackend
from app.storage.factory import get_storage_backend
from shared.constants import ExportJobStatus, ExportKind, ExportRetryState

logger = logging.getLogger(__name__)


class ExportService:
    def __init__(
        self,
        uow: UnitOfWork,
        storage_backend: StorageBackend | None = None,
    ) -> None:
        self._uow = uow
        self._storage = storage_backend

    async def _get_storage(self) -> StorageBackend:
        if self._storage is None:
            self._storage = await get_storage_backend()
        return self._storage

    async def create_export_job(
        self,
        user_id: uuid.UUID,
        kind: str,
        format: str,
        target_id: str | None,
        include_modes: list[str],
        options: ExportOptions | None = None,
        template_key: str = "standard",
    ) -> ExportJob:
        async with self._uow as uow:
            job_repo = ExportJobRepository(uow.session)
            template_repo = ExportTemplateRepository(uow.session)

            if target_id:
                active_job = await job_repo.get_active_job_for_target(
                    user_id=user_id, target_id=target_id, kind=kind, format=format
                )
                if active_job:
                    return active_job

            tpl = await template_repo.get_by_key(template_key)
            tpl_key = tpl.template_key if tpl else "standard"

            options = options or ExportOptions()
            expires_at = datetime.now(UTC) + timedelta(hours=24)
            options_dict = options.model_dump(by_alias=True)
            options_dict["includeModes"] = include_modes

            now = datetime.now(UTC)
            job = ExportJob(
                user_id=user_id,
                kind=kind,
                format=format,
                status=ExportJobStatus.QUEUED.value,
                template=tpl_key,
                target_id=target_id,
                options=options_dict,
                progress_percentage=0,
                expires_at=expires_at,
                retry_state=ExportRetryState.NONE.value,
                created_at=now,
                updated_at=now,
            )
            await job_repo.create_job(job)
            await uow.flush()
            return job

    async def count_active_jobs(self, user_id: uuid.UUID) -> int:
        """Count a user's active (queued/processing) export jobs.

        Used by the API to enforce a per-user concurrency cap before a new
        export job is created, preventing unbounded task accumulation.
        """
        async with self._uow as uow:
            job_repo = ExportJobRepository(uow.session)
            return await job_repo.count_active_for_user(user_id=user_id)

    async def count_user_exports(self, user_id: uuid.UUID) -> int:
        async with self._uow as uow:
            job_repo = ExportJobRepository(uow.session)
            return await job_repo.count_jobs(user_id=user_id)

    async def dispatch_export_job(self, public_id: str) -> None:
        """Enqueue the durable export job for processing (bounded retry).

        Must only be called after the job row has been committed so a broker
        hiccup never references a row the worker cannot read back.
        """
        from app.workers.tasks import export_generation_task, safe_dispatch

        safe_dispatch(export_generation_task, public_id, on_failure=None)

    async def get_export_job_status(
        self, user_id: uuid.UUID, public_id: str
    ) -> dict[str, Any]:
        async with self._uow as uow:
            job_repo = ExportJobRepository(uow.session)
            file_repo = ExportFileRepository(uow.session)

            job = await job_repo.get_user_job_by_public_id(user_id=user_id, public_id=public_id)
            if not job:
                raise NotFoundError(f"Export job '{public_id}' not found")

            download_url: str | None = None
            file_size = 0
            expires_at = job.expires_at

            if job.status == ExportJobStatus.COMPLETED.value:
                files = await file_repo.get_by_job_id(job.id)
                if files:
                    exp_file = files[0]
                    file_size = exp_file.file_size_bytes
                    expires_at = exp_file.expires_at
                    storage = await self._get_storage()
                    download_url = await storage.generate_presigned_url(
                        key=exp_file.file_path, expiration=3600, method="get_object"
                    )

            return {
                "exportId": job.public_id,
                "status": job.status,
                "downloadUrl": download_url,
                "expiresAt": expires_at,
                "fileSize": file_size,
                "format": job.format,
                "progressPercentage": job.progress_percentage,
                "errorMessage": job.error_message,
            }

    async def process_export_job(self, public_id: str) -> None:
        async with self._uow as uow:
            job_repo = ExportJobRepository(uow.session)
            job = await job_repo.get_by_public_id(public_id)
            if not job:
                logger.error("Export job %s not found during processing", public_id)
                return

            if job.status in (ExportJobStatus.COMPLETED.value, ExportJobStatus.CANCELLED.value):
                return

            await job_repo.update_job_progress(
                job_id=job.id, progress_percentage=10, status=ExportJobStatus.PROCESSING.value
            )

        try:
            content_data = await self._build_export_content(job)

            async with self._uow as uow:
                job_repo = ExportJobRepository(uow.session)
                await job_repo.update_job_progress(job_id=job.id, progress_percentage=50)
                tpl_repo = ExportTemplateRepository(uow.session)
                template = await tpl_repo.get_by_key(job.template)

            exporter = ExporterFactory.get_exporter(job.format)
            raw_options = job.options or {}
            options = ExportOptions(
                includeAnswerKey=raw_options.get("includeAnswerKey", False),
                pageSize=raw_options.get("pageSize", "letter"),
                includeDiagrams=raw_options.get("includeDiagrams", True),
                theme=raw_options.get("theme", "standard"),
                headerText=raw_options.get("headerText"),
                footerText=raw_options.get("footerText"),
            )

            result = await exporter.export(data=content_data, options=options, template=template)

            storage = await self._get_storage()
            storage_key = f"exports/user_{job.user_id.hex}/{job.public_id}/{result.filename}"
            file_obj = io.BytesIO(result.content_bytes)
            await storage.upload_fileobj(
                file_obj=file_obj, key=storage_key, content_type=result.mime_type
            )

            now = datetime.now(UTC)
            expires_at = now + timedelta(hours=24)

            async with self._uow as uow:
                job_repo = ExportJobRepository(uow.session)
                file_repo = ExportFileRepository(uow.session)

                exp_file = ExportFile(
                    job_id=job.id,
                    user_id=job.user_id,
                    filename=result.filename,
                    file_path=storage_key,
                    mime_type=result.mime_type,
                    file_size_bytes=result.file_size_bytes,
                    checksum_sha256=result.checksum_sha256,
                    expires_at=expires_at,
                    created_at=now,
                    updated_at=now,
                )
                await file_repo.create_file(exp_file)

                await job_repo.update_job_progress(
                    job_id=job.id, progress_percentage=100, status=ExportJobStatus.COMPLETED.value
                )

        except Exception as exc:
            logger.exception("Failed to process export job %s: %s", public_id, exc)
            async with self._uow as uow:
                job_repo = ExportJobRepository(uow.session)
                job = await job_repo.get_by_public_id(public_id)
                if job:
                    await job_repo.update_job_progress(
                        job_id=job.id,
                        progress_percentage=job.progress_percentage,
                        status=ExportJobStatus.FAILED.value,
                        error_message=str(exc)[:500],
                    )

    async def _build_export_content(self, job: ExportJob) -> ExportContentData:
        target_id = job.target_id or ""
        kind = job.kind

        async with self._uow as uow:
            if kind in (ExportKind.NOTES.value, ExportKind.SUMMARY.value, ExportKind.BUNDLE.value, "presentation") and target_id:
                from sqlalchemy import or_
                try:
                    target_uuid = uuid.UUID(target_id)
                    where_clause = or_(Presentation.public_id == target_id, Presentation.id == target_uuid)
                except ValueError:
                    where_clause = (Presentation.public_id == target_id)

                stmt_pres = (
                    select(Presentation)
                    .where(where_clause, Presentation.owner_id == job.user_id)
                    .options(selectinload(Presentation.content_units))
                )
                res_pres = await uow.session.execute(stmt_pres)
                pres = res_pres.scalar_one_or_none()

                if pres:
                    sections = []
                    for unit in pres.content_units:
                        sections.append({
                            "title": unit.title or f"Unit {unit.position}",
                            "content": unit.raw_text or "",
                            "blocks": []
                        })
                    if not sections:
                        sections = [{"title": "Overview", "content": pres.description or pres.title, "blocks": []}]

                    return ExportContentData(
                        title=pres.title,
                        subtitle=f"Topic: {pres.topic or 'General'}",
                        author="EduVision AI Platform",
                        created_at=pres.created_at.isoformat() if pres.created_at else None,
                        sections=sections,
                    )

        return ExportContentData(
            title=f"EduVision Export — {kind.capitalize()}",
            subtitle="Generated Study Document",
            sections=[{
                "title": "Study Notes",
                "content": f"Export content for target {target_id or 'General'}",
                "blocks": []
            }],
        )

    async def export_presentation_analytics_csv(
        self, user_id: uuid.UUID, presentation_id: str
    ) -> dict[str, Any]:
        """Export analytics CSV for a presentation.

        NOTE: This method is NOT wired to any router and is unreachable.
        Real analytics export is implemented via GET /api/v1/effectiveness/export.
        This method intentionally returns no data to avoid fabricating analytics.
        """
        raise NotImplementedError(
            "Presentation-level analytics export is not implemented. "
            "Use GET /api/v1/effectiveness/export for real study data export."
        )

    async def list_user_exports(
        self, user_id: uuid.UUID, offset: int = 0, limit: int = 20
    ) -> list[ExportJob]:
        async with self._uow as uow:
            job_repo = ExportJobRepository(uow.session)
            return await job_repo.list_jobs(user_id=user_id, offset=offset, limit=limit)

    async def cancel_export_job(self, user_id: uuid.UUID, public_id: str) -> None:
        async with self._uow as uow:
            job_repo = ExportJobRepository(uow.session)
            job = await job_repo.get_user_job_by_public_id(user_id=user_id, public_id=public_id)
            if not job:
                raise NotFoundError(f"Export job '{public_id}' not found")

            if job.status not in (ExportJobStatus.COMPLETED.value, ExportJobStatus.FAILED.value):
                await job_repo.update_job_progress(
                    job_id=job.id,
                    progress_percentage=job.progress_percentage,
                    status=ExportJobStatus.CANCELLED.value,
                )
