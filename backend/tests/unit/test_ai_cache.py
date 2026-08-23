from __future__ import annotations

from unittest.mock import patch

from app.ai.cache import AIResponseCache
from app.ai.models import AIRequest, AIResponse, TokenUsage


def _response(request_id: str = "rid") -> AIResponse:
    return AIResponse(
        text="hello",
        usage=TokenUsage(),
        provider="local",
        model="local-mock-1",
        request_id=request_id,
    )


class TestCacheKey:
    def test_ignores_request_id_correlation_and_metadata(self) -> None:
        base = AIRequest(
            user_prompt="explain gravity",
            system_prompt="be concise",
            metadata={"resource_type": "lesson", "resource_id": "a"},
        )
        variant = base.model_copy(
            update={
                "request_id": "different",
                "correlation_id": "different",
                "metadata": {"resource_type": "lesson", "resource_id": "b"},
            }
        )
        assert AIResponseCache.key_for(base) == AIResponseCache.key_for(variant)

    def test_differs_on_prompt(self) -> None:
        a = AIRequest(user_prompt="explain gravity")
        b = AIRequest(user_prompt="explain relativity")
        assert AIResponseCache.key_for(a) != AIResponseCache.key_for(b)


class TestCacheBehaviour:
    def test_roundtrip(self) -> None:
        cache = AIResponseCache(ttl=60, max_entries=10)
        response = _response()
        cache.set("k", response)
        assert cache.get("k") is response
        assert cache.size == 1

    def test_ttl_expiry(self) -> None:
        clock = {"now": 100.0}
        with patch("app.ai.cache.time.monotonic", side_effect=lambda: clock["now"]):
            cache = AIResponseCache(ttl=10, max_entries=10)
            response = _response()
            cache.set("k", response)
            assert cache.get("k") is response
            clock["now"] = 115.0
            assert cache.get("k") is None
            assert cache.size == 0

    def test_max_entries_evicts_oldest(self) -> None:
        cache = AIResponseCache(ttl=60, max_entries=2)
        cache.set("a", _response())
        cache.set("b", _response())
        cache.set("c", _response())
        assert cache.size == 2
        assert cache.get("a") is None

    def test_zero_max_entries_disables(self) -> None:
        cache = AIResponseCache(ttl=60, max_entries=0)
        cache.set("k", _response())
        assert cache.size == 0

    def test_clear(self) -> None:
        cache = AIResponseCache(ttl=60, max_entries=10)
        cache.set("k", _response())
        cache.clear()
        assert cache.size == 0
