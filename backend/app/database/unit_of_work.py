from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.commit_barrier import clear_commit_hook, publish_commit_hook
from app.core.config import settings
from app.database.retry import retry_on_db_failure
from app.database.session import async_session_factory


class UnitOfWork:
    def __init__(
        self,
        session: AsyncSession | None = None,
        retry_on_transient: bool = True,
    ) -> None:
        self._session = session
        self._retry_on_transient = retry_on_transient

    async def __aenter__(self) -> UnitOfWork:
        if self._session is None:
            self._session = async_session_factory()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None:
        if self._session is None:
            return
        try:
            if exc_type is not None:
                await self._session.rollback()
            else:
                if self._retry_on_transient:
                    await self._commit_with_retry()
                else:
                    await self._session.commit()
        finally:
            await self._session.close()
            self._session = None

    async def _commit_with_retry(self) -> None:
        async def _rollback_before_retry(_attempt: int) -> None:
            # A PostgreSQL serialization/deadlock failure leaves the current
            # transaction aborted; retrying a commit against it would fail
            # forever. Roll back so the next attempt starts a fresh transaction.
            await self.session.rollback()

        async def _do_commit() -> None:
            await self.session.commit()

        try:
            await retry_on_db_failure(
                _do_commit,
                max_retries=settings.DATABASE_RETRY_ATTEMPTS,
                base_delay=settings.DATABASE_RETRY_BASE_DELAY,
                max_delay=settings.DATABASE_RETRY_MAX_DELAY,
                jitter=settings.DATABASE_RETRY_JITTER,
                on_retry=_rollback_before_retry,
            )
        except Exception:
            raise

    @property
    def session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("UnitOfWork not entered")
        return self._session

    async def flush(self) -> None:
        await self.session.flush()

    async def commit(self) -> None:
        """Persist pending changes immediately.

        Useful when a write must survive a subsequent exception raised within
        this unit of work (e.g. session revocation before a 401 is propagated),
        since ``__aexit__`` rolls back on any exception.
        """
        if self._retry_on_transient:
            await self._commit_with_retry()
        else:
            await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()


async def get_unit_of_work(request: Request) -> AsyncGenerator[UnitOfWork]:
    """Yield a request-scoped UnitOfWork.

    The commit is published to :class:`~app.core.commit_barrier.CommitBarrierRoute`
    so it runs *before* the response is sent. FastAPI unwinds dependency
    teardown only after the response has left the app, so committing there
    would let a ``201`` reach the client ahead of its own transaction.
    ``__aexit__`` keeps its commit as a fallback for callers that bypass the
    barrier (Celery workers, direct use).
    """
    async with UnitOfWork() as uow:
        publish_commit_hook(request, uow.commit)
        try:
            yield uow
        finally:
            clear_commit_hook(request)
