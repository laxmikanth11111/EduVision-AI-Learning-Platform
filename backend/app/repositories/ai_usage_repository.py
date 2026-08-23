from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.errors import AIError
from app.ai.models import AIRequest, AIResponse
from app.database.repository import BaseRepository
from app.models.ai_usage import AIUsageLog

_ZERO = Decimal("0.000000")


class AIUsageRepository(BaseRepository[AIUsageLog]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, AIUsageLog)

    async def create_from_response(
        self,
        response: AIResponse,
        *,
        resource_type: str | None = None,
        resource_id: str | None = None,
        cache_hit: bool = False,
    ) -> AIUsageLog:
        return await self.create(
            request_id=response.request_id,
            correlation_id=response.correlation_id,
            provider=response.provider,
            model=response.model,
            status="success",
            finish_reason=response.finish_reason.value if response.finish_reason else None,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            total_tokens=response.usage.total_tokens,
            estimated_cost=response.usage.estimated_cost or _ZERO,
            latency_ms=response.latency_ms,
            retry_count=response.retry_count,
            cache_hit=cache_hit,
            resource_type=resource_type,
            resource_id=resource_id,
        )

    async def create_error_record(
        self,
        *,
        request: AIRequest,
        error: AIError,
        provider: str | None = None,
        model: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
    ) -> AIUsageLog:
        return await self.create(
            request_id=request.request_id or "",
            correlation_id=request.correlation_id,
            provider=provider or error.provider or "",
            model=model or error.model or "",
            status="error",
            error_code=error.code.value if error.code else "AI_ERROR",
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            estimated_cost=_ZERO,
            latency_ms=0,
            retry_count=0,
            cache_hit=False,
            resource_type=resource_type,
            resource_id=resource_id,
        )

    async def total_tokens(self) -> int:
        stmt = select(func.coalesce(func.sum(AIUsageLog.total_tokens), 0))
        result = await self._session.execute(stmt)
        return int(result.scalar_one())
