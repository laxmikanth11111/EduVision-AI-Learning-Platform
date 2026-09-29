"""Phase 7: live grounding verification with the real embedding provider.

Embeds source passages and a query with the live provider, then applies the
same cosine-similarity ranking the application uses, to confirm the relevant
passage outranks an unrelated one.
"""

from __future__ import annotations

import json
import math
import os
import sys
import urllib.request
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


def embed(texts: list[str]) -> list[list[float]]:
    from app.core.config import settings
    key = settings.AI_API_KEY
    model = settings.EMBEDDING_MODEL
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:batchEmbedContents?key={key}")
    payload = {
        "model": f"models/{model}",
        "requests": [{"model": f"models/{model}",
                      "content": {"parts": [{"text": t}]}} for t in texts],
    }
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        body = json.loads(r.read())
    return [e["values"] for e in body["embeddings"]]


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


TARGET = ("The mitochondrion is the organelle responsible for cellular "
          "respiration, where glucose and oxygen are converted into ATP.")
DISTRACTOR = ("The Declaration of Independence was adopted in 1776 and "
              "listed grievances against the British Crown.")
QUERY = "Which organelle produces ATP from glucose and oxygen?"


def main() -> int:
    try:
        vecs = embed([TARGET, DISTRACTOR, QUERY])
    except Exception as exc:  # noqa: BLE001
        record("live embeddings for source passages + query", False,
               f"{type(exc).__name__}: {exc}"[:200])
        print("\n0/3 live grounding checks passed", flush=True)
        return 1

    t, d, q = vecs
    record("live embeddings for source passages + query", True,
           f"dimensions={len(t)}/{len(d)}/{len(q)}")

    s_target = cosine(q, t)
    s_distract = cosine(q, d)
    record("relevant passage outranks unrelated passage", s_target > s_distract,
           f"target={s_target:.4f} distractor={s_distract:.4f}")
    record("relevant passage clears a meaningful similarity margin",
           s_target - s_distract > 0.05,
           f"margin={s_target - s_distract:.4f}")
    record("query embedding is normalised and finite",
           all(math.isfinite(x) for x in q) and 0.99 < math.sqrt(
               sum(x * x for x in q)) < 1.01,
           f"norm={math.sqrt(sum(x * x for x in q)):.6f}")

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"\n{passed}/{len(RESULTS)} live grounding checks passed", flush=True)
    for n, ok, dtl in RESULTS:
        if not ok:
            print(f"  FAILED: {n} :: {dtl}", flush=True)
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
