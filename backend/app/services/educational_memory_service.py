"""Educational Memory Service.

Tracks concept mastery, learning milestones, and preferences.
Database-backed via JSON blob in educational_memories table,
with in-memory cache for fast read access within a request.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.educational_memory import EducationalMemoryRecord
from app.schemas.educational_memory import (
    ConceptMasteryRecord,
    EducationalMemory,
    LearnerProfile,
    TimelineMilestone,
)
from app.utils.bounded_cache import BoundedCache

logger = get_logger(__name__)


class EducationalMemoryService:

    def __init__(self) -> None:
        self._memories: BoundedCache[str, EducationalMemory] = BoundedCache(
            max_size=5000, ttl=1800,
        )

    async def load_from_db(self, session: AsyncSession, user_id: str) -> EducationalMemory:
        """Load or create educational memory from database."""
        cached = self._memories.get(user_id)
        if cached is not None:
            return cached

        user_uuid = _safe_uuid(user_id)
        if user_uuid is None:
            return self._create_empty(user_id)

        result = await session.execute(
            select(EducationalMemoryRecord).where(
                EducationalMemoryRecord.user_id == user_uuid
            )
        )
        record = result.scalar_one_or_none()

        if record and record.memory_data:
            try:
                memory = EducationalMemory(**record.memory_data)
            except Exception as exc:
                logger.warning(
                    "memory_deserialize_failed",
                    user_id=user_id,
                    error=str(exc),
                )
                memory = self._create_empty(user_id)
        else:
            memory = self._create_empty(user_id)

        self._memories.set(user_id, memory)
        return memory

    async def save_to_db(self, session: AsyncSession, user_id: str) -> None:
        """Persist current memory state to database."""
        memory = self._memories.get(user_id)
        if memory is None:
            return

        user_uuid = _safe_uuid(user_id)
        if user_uuid is None:
            return

        result = await session.execute(
            select(EducationalMemoryRecord).where(
                EducationalMemoryRecord.user_id == user_uuid
            )
        )
        db_record = result.scalar_one_or_none()

        if db_record is None:
            db_record = EducationalMemoryRecord(
                user_id=user_uuid,
                memory_data=memory.model_dump(),
            )
            session.add(db_record)
        else:
            db_record.memory_data = memory.model_dump()

    def get_or_create_memory(self, user_id: str) -> EducationalMemory:
        """Get memory from cache, or create empty one (not yet loaded from DB)."""
        cached = self._memories.get(user_id)
        if cached is not None:
            return cached
        return self._create_empty(user_id)

    def _create_empty(self, user_id: str) -> EducationalMemory:
        now = time.time()
        memory = EducationalMemory(
            user_id=user_id,
            profile=LearnerProfile(user_id=user_id),
            created_at=now,
            updated_at=now,
            milestones=[
                TimelineMilestone(
                    milestone_id=f"ms_{uuid.uuid4().hex[:8]}",
                    title="Educational History Started",
                    timestamp=now,
                    category="profile_created",
                )
            ],
        )
        self._memories.set(user_id, memory)
        return memory

    def update_concept_mastery(
        self,
        user_id: str,
        concept_id: str,
        concept_name: str,
        score: float,
    ) -> EducationalMemory:
        memory = self.get_or_create_memory(user_id)
        now = time.time()

        record = memory.concept_records.get(concept_id)
        if record:
            trend = "improving" if score > record.mastery_score else "regressing" if score < record.mastery_score else "stable"
            record.mastery_score = score
            record.last_reviewed_at = now
            record.review_count += 1
            record.trend = trend
        else:
            record = ConceptMasteryRecord(
                concept_id=concept_id,
                concept_name=concept_name,
                first_learned_at=now,
                last_reviewed_at=now,
                mastery_score=score,
                review_count=1,
            )
            memory.concept_records[concept_id] = record

        # Categorize into Mastered (>= 85%), Developing (50-84%), Weak (< 50%)
        memory.mastered_concepts = [c for c, r in memory.concept_records.items() if r.mastery_score >= 85.0]
        memory.developing_concepts = [c for c, r in memory.concept_records.items() if 50.0 <= r.mastery_score < 85.0]
        memory.weak_concepts = [c for c, r in memory.concept_records.items() if r.mastery_score < 50.0]

        # Update average mastery
        all_scores = [r.mastery_score for r in memory.concept_records.values()]
        if all_scores:
            memory.profile.average_mastery = round(sum(all_scores) / len(all_scores), 1)

        memory.updated_at = now
        return memory

    def record_review_activity(
        self,
        user_id: str,
        concept_id: str,
        concept_name: str | None = None,
    ) -> EducationalMemory:
        """Record that a learner reviewed a concept (P10).

        Resets the review clock (``last_reviewed_at``) and increments
        ``review_count`` without changing the mastery score. Used when a concept
        review is completed through the adaptive review engine, so the decay
        signal reflects the review without rewriting mastery.
        """
        memory = self.get_or_create_memory(user_id)
        now = time.time()

        record = memory.concept_records.get(concept_id)
        if record:
            record.last_reviewed_at = now
            record.review_count += 1
        elif concept_name:
            record = ConceptMasteryRecord(
                concept_id=concept_id,
                concept_name=concept_name,
                first_learned_at=now,
                last_reviewed_at=now,
                review_count=1,
            )
            memory.concept_records[concept_id] = record
            memory.updated_at = now

        memory.updated_at = now
        return memory

    def add_milestone(
        self,
        user_id: str,
        title: str,
        category: str,
        details: dict[str, Any] | None = None,
    ) -> EducationalMemory:
        memory = self.get_or_create_memory(user_id)
        now = time.time()

        ms = TimelineMilestone(
            milestone_id=f"ms_{uuid.uuid4().hex[:8]}",
            title=title,
            timestamp=now,
            category=category,
            details=details or {},
        )

        memory.milestones.append(ms)
        memory.updated_at = now
        return memory

    def update_preferences(
        self, user_id: str, preferences: dict[str, Any]
    ) -> EducationalMemory:
        memory = self.get_or_create_memory(user_id)
        for k, v in preferences.items():
            if hasattr(memory.preferences, k):
                setattr(memory.preferences, k, v)
        memory.updated_at = time.time()
        return memory

    def export_memory(self, user_id: str) -> dict[str, Any]:
        memory = self.get_or_create_memory(user_id)
        return memory.model_dump()

    def import_memory(self, snapshot: dict[str, Any]) -> EducationalMemory:
        memory = EducationalMemory(**snapshot)
        self._memories.set(memory.user_id, memory)
        return memory

    def reset_memory(self, user_id: str) -> EducationalMemory:
        """Reset concept mastery history and milestone records (Privacy control)."""
        self._memories.delete(user_id)
        return self.get_or_create_memory(user_id)

    def delete_memory(self, user_id: str) -> bool:
        """Completely purge educational memory for user (Privacy compliance)."""
        return self._memories.delete(user_id)


def _safe_uuid(user_id: str) -> uuid.UUID | None:
    """Safely convert a string user_id to UUID, returning None on failure."""
    try:
        return uuid.UUID(user_id)
    except (ValueError, TypeError):
        return None


educational_memory_service = EducationalMemoryService()
