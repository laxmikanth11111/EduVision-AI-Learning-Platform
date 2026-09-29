"""Phase 6: live AI provider verification through the app's own abstraction.

Uses the real configured provider/credentials. Never prints the key. If the
provider is unreachable or unauthenticated, this reports the failure verbatim
rather than masking it as success.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
os.environ["PYTHONPATH"] = str(BACKEND)
os.environ["ENVIRONMENT"] = "test"
os.chdir(BACKEND)
sys.path.insert(0, str(BACKEND))

RESULTS: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""), flush=True)


async def main() -> int:
    from app.core.config import settings
    record("AI provider configured", bool(settings.AI_PROVIDER), f"provider={settings.AI_PROVIDER}")
    record("AI model configured", bool(settings.AI_MODEL), f"model={settings.AI_MODEL}")
    key = getattr(settings, "AI_API_KEY", "") or ""
    record("AI credential present in config", bool(key), f"key_length={len(key)}")

    from app.ai.factory import get_ai_provider  # type: ignore[attr-defined]

    try:
        provider = get_ai_provider()
    except Exception:
        from app.ai.registry import build_provider  # type: ignore[attr-defined]
        provider = build_provider()

    try:
        health = await provider.health_check()
        healthy = bool(getattr(health, "healthy", False)) if not isinstance(health, bool) else health
        record("live provider health_check", healthy, str(health)[:180])
    except Exception as exc:  # noqa: BLE001
        record("live provider health_check", False, f"{type(exc).__name__}: {exc}"[:200])

    from app.ai.models import AIRequest

    try:
        req = AIRequest(
            user_prompt="Reply with exactly the single word: GROUNDED",
            max_tokens=32,
            temperature=0.0,
        )
        resp = await provider.generate(req)
        text = getattr(resp, "text", "") or getattr(resp, "content", "") or ""
        record("live completion returns content", bool(text.strip()),
               f"response={text.strip()[:140]!r}")
    except Exception as exc:  # noqa: BLE001
        # Distinguish a provider-side outage/quota from an app defect by
        # reporting the upstream status the SDK surfaced.
        record("live completion returns content", False,
               f"{type(exc).__name__}: {exc}"[:220])

    # Embeddings are verified directly against the provider so the result is
    # attributable even when the generation model is unavailable.
    import json
    import urllib.error
    import urllib.request

    key = getattr(settings, "AI_API_KEY", "") or ""
    emodel = getattr(settings, "EMBEDDING_MODEL", "") or ""
    try:
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{emodel}:embedContent?key={key}")
        payload = {"model": f"models/{emodel}",
                   "content": {"parts": [{"text": "EduVision grounding probe"}]}}
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=45) as r:
            body = json.loads(r.read())
        vec = (body.get("embedding") or {}).get("values") or []
        record("live embedding call returns a vector", bool(vec),
               f"status=200 model={emodel} dimensions={len(vec)}")
    except urllib.error.HTTPError as exc:
        record("live embedding call returns a vector", False, f"HTTP {exc.code}")
    except Exception as exc:  # noqa: BLE001
        record("live embedding call returns a vector", False,
               f"{type(exc).__name__}: {exc}"[:200])

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"\n{passed}/{len(RESULTS)} live AI checks passed", flush=True)
    for n, ok, d in RESULTS:
        if not ok:
            print(f"  FAILED: {n} :: {d}", flush=True)
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
