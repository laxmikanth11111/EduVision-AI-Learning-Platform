"""Best-effort in-process TTL cache for AI responses.

Gated by ``AI_CACHE_ENABLED``. This is a short-lived, bounded cache intended to
deduplicate identical successful generations. A Redis-backed cache is a future
enhancement; the interface is deliberately small so it can be swapped out.
"""

from __future__ import annotations

import hashlib
import json
import time

from app.ai.models import AIRequest, AIResponse


def _canonical_request_payload(request: AIRequest) -> dict[str, object]:
    """Stable, cache-key-relevant view of a request.

    Request IDs, correlation IDs and application ``metadata`` are intentionally
    excluded so identical prompts across contexts share a cache entry.
    """
    return {
        "user_prompt": request.user_prompt,
        "system_prompt": request.system_prompt,
        "messages": (
            [m.model_dump() for m in request.messages] if request.messages else None
        ),
        "temperature": request.temperature,
        "top_p": request.top_p,
        "max_tokens": request.max_tokens,
        "stop_sequences": request.stop_sequences,
        "response_format": request.response_format.value,
        "language": request.language,
        "difficulty": request.difficulty,
        "model_override": request.model_override,
    }


class AIResponseCache:
    def __init__(self, *, ttl: int, max_entries: int) -> None:
        self._ttl = ttl
        self._max_entries = max_entries
        self._entries: dict[str, tuple[float, AIResponse]] = {}

    @staticmethod
    def key_for(request: AIRequest) -> str:
        payload = json.dumps(
            _canonical_request_payload(request),
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get(self, key: str) -> AIResponse | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        stored_at, response = entry
        if self._ttl > 0 and time.monotonic() - stored_at >= self._ttl:
            self._entries.pop(key, None)
            return None
        return response

    def set(self, key: str, response: AIResponse) -> None:
        if self._max_entries <= 0:
            return
        now = time.monotonic()
        self._entries[key] = (now, response)
        self._evict(now)

    def _evict(self, now: float) -> None:
        if self._ttl > 0:
            expired = [k for k, (ts, _) in self._entries.items() if now - ts >= self._ttl]
            for key in expired:
                self._entries.pop(key, None)
        while len(self._entries) > self._max_entries:
            oldest_key = min(self._entries, key=lambda k: self._entries[k][0])
            self._entries.pop(oldest_key, None)

    def clear(self) -> None:
        self._entries.clear()

    @property
    def size(self) -> int:
        return len(self._entries)
