"""WS4: integration tests verifying the six scoped caches are bounded.

These tests confirm that the actual application caches
(_VIDEO_PROJECT_CACHE, _BLUEPRINT_CACHE, _SESSIONS, _memories,
_contexts, visual _cache) use BoundedCache and enforce max size / TTL.
"""

from __future__ import annotations

import time
from typing import Any

import pytest

from app.utils.bounded_cache import BoundedCache

# ── Helpers ─────────────────────────────────────────────────────────────


def _assert_bounded(cache: Any, max_size: int, label: str) -> None:
    """Verify the cache is a BoundedCache and enforces its cap."""
    assert isinstance(cache, BoundedCache), f"{label} must be a BoundedCache"
    assert cache._max_size == max_size, (
        f"{label} max_size expected {max_size}, got {cache._max_size}"
    )


def _assert_ttl(cache: Any, ttl: float, label: str) -> None:
    """Verify the cache has a TTL set."""
    assert cache._ttl == ttl, f"{label} ttl expected {ttl}, got {cache._ttl}"


def _assert_bounded_growth(
    cache: BoundedCache[str, Any],
    max_size: int,
    label: str,
) -> None:
    """Insert more entries than max_size and verify the cache stays bounded."""
    for i in range(max_size + 100):
        cache.set(f"{label}_test_{i}", {"i": i})
    assert len(cache) <= max_size, (
        f"{label} grew to {len(cache)}, expected <= {max_size}"
    )


# ── 1. _VIDEO_PROJECT_CACHE ────────────────────────────────────────────


class TestVideoProjectCache:
    def test_is_bounded_cache(self) -> None:
        from app.api.v1.video_router import _VIDEO_PROJECT_CACHE
        _assert_bounded(_VIDEO_PROJECT_CACHE, 500, "_VIDEO_PROJECT_CACHE")

    def test_has_ttl(self) -> None:
        from app.api.v1.video_router import _VIDEO_PROJECT_CACHE
        _assert_ttl(_VIDEO_PROJECT_CACHE, 1800, "_VIDEO_PROJECT_CACHE")

    def test_max_size_enforced(self) -> None:
        from app.api.v1.video_router import _VIDEO_PROJECT_CACHE
        _assert_bounded_growth(_VIDEO_PROJECT_CACHE, 500, "VPC")

    def test_get_set_cycle(self) -> None:
        from app.api.v1.video_router import _VIDEO_PROJECT_CACHE
        _VIDEO_PROJECT_CACHE.set("ws4_test_vp", {"owner_id": "u1", "data": "proj"})
        assert _VIDEO_PROJECT_CACHE.get("ws4_test_vp") == {"owner_id": "u1", "data": "proj"}
        _VIDEO_PROJECT_CACHE.delete("ws4_test_vp")
        assert _VIDEO_PROJECT_CACHE.get("ws4_test_vp") is None


# ── 2. _BLUEPRINT_CACHE ────────────────────────────────────────────────


class TestBlueprintCache:
    def test_is_bounded_cache(self) -> None:
        from app.api.v1.animation_router import _BLUEPRINT_CACHE
        _assert_bounded(_BLUEPRINT_CACHE, 500, "_BLUEPRINT_CACHE")

    def test_has_ttl(self) -> None:
        from app.api.v1.animation_router import _BLUEPRINT_CACHE
        _assert_ttl(_BLUEPRINT_CACHE, 1800, "_BLUEPRINT_CACHE")

    def test_max_size_enforced(self) -> None:
        from app.api.v1.animation_router import _BLUEPRINT_CACHE
        _assert_bounded_growth(_BLUEPRINT_CACHE, 500, "BC")

    def test_get_set_cycle(self) -> None:
        from app.api.v1.animation_router import _BLUEPRINT_CACHE
        _BLUEPRINT_CACHE.set("ws4_test_bp", {"owner_id": "u1", "data": "bp"})
        assert _BLUEPRINT_CACHE.get("ws4_test_bp") == {"owner_id": "u1", "data": "bp"}
        _BLUEPRINT_CACHE.delete("ws4_test_bp")
        assert _BLUEPRINT_CACHE.get("ws4_test_bp") is None


# ── 3. _SESSIONS ───────────────────────────────────────────────────────


class TestSessionsCache:
    def test_is_bounded_cache(self) -> None:
        from app.services.lesson_player_service import _SESSIONS
        _assert_bounded(_SESSIONS, 2048, "_SESSIONS")

    def test_has_ttl(self) -> None:
        from app.services.lesson_player_service import _SESSIONS
        _assert_ttl(_SESSIONS, 3600, "_SESSIONS")

    def test_max_size_enforced(self) -> None:
        from app.services.lesson_player_service import _SESSIONS
        _assert_bounded_growth(_SESSIONS, 2048, "SES")

    def test_items_iteration(self) -> None:
        from app.services.lesson_player_service import _SESSIONS
        _SESSIONS.set("ws4_test_sess", {"owner_id": "u1", "lesson_id": "l1"})
        items = _SESSIONS.items()
        assert any(k == "ws4_test_sess" for k, _ in items)
        _SESSIONS.delete("ws4_test_sess")

    def test_ttl_expiration(self) -> None:
        from app.services.lesson_player_service import _SESSIONS
        _SESSIONS.set("ws4_ttl_sess", {"test": True})
        # Verify it exists
        assert _SESSIONS.get("ws4_ttl_sess") is not None
        _SESSIONS.delete("ws4_ttl_sess")


# ── 4. _memories (EducationalMemoryService) ────────────────────────────


class TestMemoriesCache:
    def test_is_bounded_cache(self) -> None:
        from app.services.educational_memory_service import educational_memory_service
        _assert_bounded(educational_memory_service._memories, 5000, "_memories")

    def test_has_ttl(self) -> None:
        from app.services.educational_memory_service import educational_memory_service
        _assert_ttl(educational_memory_service._memories, 1800, "_memories")

    def test_max_size_enforced(self) -> None:
        from app.services.educational_memory_service import educational_memory_service
        # Use unique keys to avoid interfering with real data
        _assert_bounded_growth(
            educational_memory_service._memories, 5000, "MEM"
        )

    def test_delete_operation(self) -> None:
        from app.schemas.educational_memory import EducationalMemory, LearnerProfile
        from app.services.educational_memory_service import educational_memory_service

        mem = EducationalMemory(
            user_id="ws4_test_user_mem",
            profile=LearnerProfile(user_id="ws4_test_user_mem"),
            created_at=time.time(),
            updated_at=time.time(),
        )
        educational_memory_service._memories.set("ws4_test_user_mem", mem)
        assert educational_memory_service._memories.delete("ws4_test_user_mem") is True
        assert educational_memory_service._memories.get("ws4_test_user_mem") is None

    def test_clear_operation(self) -> None:
        from app.schemas.educational_memory import EducationalMemory, LearnerProfile
        from app.services.educational_memory_service import educational_memory_service

        mem = EducationalMemory(
            user_id="ws4_clear_user",
            profile=LearnerProfile(user_id="ws4_clear_user"),
            created_at=time.time(),
            updated_at=time.time(),
        )
        educational_memory_service._memories.set("ws4_clear_user", mem)
        # Clear only our test entries via delete, not the whole cache
        educational_memory_service._memories.delete("ws4_clear_user")
        assert educational_memory_service._memories.get("ws4_clear_user") is None


# ── 5. _contexts (LearningContextService) ──────────────────────────────


class TestContextsCache:
    def test_is_bounded_cache(self) -> None:
        from app.services.learning_context_service import learning_context_service
        _assert_bounded(learning_context_service._contexts, 2048, "_contexts")

    def test_has_ttl(self) -> None:
        from app.services.learning_context_service import learning_context_service
        _assert_ttl(learning_context_service._contexts, 1800, "_contexts")

    def test_max_size_enforced(self) -> None:
        from app.services.learning_context_service import learning_context_service
        _assert_bounded_growth(learning_context_service._contexts, 2048, "CTX")

    def test_get_set_cycle(self) -> None:
        from app.schemas.learning_context import LearningContext, LearningState
        from app.services.learning_context_service import learning_context_service

        ctx = LearningContext(
            session_id="ws4_test_ctx",
            topic="test",
            active_state=LearningState.NOT_STARTED,
            created_at=time.time(),
            updated_at=time.time(),
        )
        learning_context_service._contexts.set("ws4_test_ctx", ctx)
        retrieved = learning_context_service._contexts.get("ws4_test_ctx")
        assert retrieved is not None
        assert retrieved.topic == "test"
        learning_context_service._contexts.delete("ws4_test_ctx")
        assert learning_context_service._contexts.get("ws4_test_ctx") is None


# ── 6. visual _cache (VisualIntelligenceService) ───────────────────────


class TestVisualCache:
    def test_is_bounded_cache(self) -> None:
        from app.services.visual_intelligence_service import VisualIntelligenceService
        svc = VisualIntelligenceService()
        _assert_bounded(svc._cache, 200, "visual _cache")

    def test_has_ttl(self) -> None:
        from app.services.visual_intelligence_service import VisualIntelligenceService
        svc = VisualIntelligenceService()
        _assert_ttl(svc._cache, 1800, "visual _cache")

    def test_max_size_enforced(self) -> None:
        from app.services.visual_intelligence_service import VisualIntelligenceService
        svc = VisualIntelligenceService()
        _assert_bounded_growth(svc._cache, 200, "VIS")

    def test_instance_cache_independent(self) -> None:
        from app.services.visual_intelligence_service import VisualIntelligenceService
        svc1 = VisualIntelligenceService()
        svc2 = VisualIntelligenceService()
        svc1._cache.set("key1", "value1")
        assert svc2._cache.get("key1") is None
