# P4 / WS4 — Runtime Memory Bounds (Bounded Caches) — Implementation Report

## Status

**COMPLETE** — committed as part of the P4-C4/WS4 logical commit.

## 1. Objective

Replace the six identified **unbounded in-memory dictionaries/caches** with a
**safe bounded cache mechanism** using appropriate **TTL and eviction
behavior**. The goal is bounded memory usage + predictable eviction without
breaking API, assistant, visual, animation, session, context, memory, or player
behavior.

The six scoped caches are:

1. `_VIDEO_PROJECT_CACHE`
2. `_BLUEPRINT_CACHE`
3. `_SESSIONS`
4. `_memories`
5. `_contexts`
6. visual `_cache`

## 2. Previous unbounded behavior

All six were plain `dict` instances with **no size cap and no TTL**. Under
sustained request load, each process's memory would grow without bound as
sessions, projects, blueprints, memories, contexts, and generated visual models
accumulated. This is the P3 `P3_P4_HANDOFF_AUDIT.md` "PARTIAL" gap for runtime
memory bounds.

## 3. Bounded cache design

A shared, reusable `BoundedCache` utility in
`app/utils/bounded_cache.py` provides:

- **Maximum entry count** (`max_size`) — hard cap enforced on every `set`.
- **TTL / expiration** (`ttl`, seconds) — lazy expiration on read
  (`get`, `__contains__`, `__getitem__`, `get_value`).
- **LRU-style eviction** — least-recently **accessed** entry evicted once the
  cap is reached (deterministic, `OrderedDict`-backed).
- **Dict-compatible operations** — `set`, `get`, `delete`, `pop`, `clear`,
  `touch`, `__contains__`, `__getitem__`, `__setitem__`, `__delitem__`,
  `__len__`, `__iter__`, `keys`, `values`, `items`, `get_value`.
- **Eviction callback** (`on_evict`) — invoked synchronously on every removal
  (explicit delete, size eviction, TTL expiration). Exceptions are swallowed so
  a misbehaving callback can never break cache operations.
- **Concurrency protection** — a `threading.Lock` guards all operations. This
  is a safety net; the FastAPI runtime uses a single asyncio loop per process
  so contention is minimal.
- **Complexity** — `set`/`get`/`delete` are O(1) amortized. Eviction is O(1)
  per evicted entry. `keys`/`values`/`items` are O(n) but only used for
  enumeration, which is bounded by the cache's own size cap.

### Why TTL is safe for each cache

TTL is not "invented arbitrarily". It is derived from each cache's real
lifecycle:

- **Ephemeral regenerable caches** (`_VIDEO_PROJECT_CACHE`, `_BLUEPRINT_CACHE`,
  visual `_cache`, `_contexts`): the underlying projects/blueprints/models and
  learning contexts can be **rebuilt on demand** from the topic/description if
  evicted or expired. A short TTL simply drops a regenerable value.
- **Session state** (`_SESSIONS`): sessions are lightweight and a new one can
  be started on demand. A 1-hour TTL matches a reasonable lesson-player session
  lifetime while still bounding memory.
- **User memory** (`_memories`): **DB-backed**; the in-memory copy is a read
  buffer / write cache. TTL merely forces a refresh from the authoritative
  `educational_memories` row.

## 4. Per-cache configuration and rationale

### 1. `_VIDEO_PROJECT_CACHE`
- **location:** `app/api/v1/video_router.py`
- **max size:** `500`
- **TTL:** `1800` s (30 min)
- **eviction:** LRU (least-recently-accessed)
- **rationale:** Video project objects can be large (full project + timeline +
  storyboard + metadata). A video project is regenerable from the original
  topic/description, so eviction/expiration only costs a rebuild. 500 entries
  bounds memory while comfortably covering active `GET`/`render` workflows.
- **safety:** values carry an `owner_id`; ownership-404 semantics are enforced
  at read time (`_get_owned_project`), unchanged. Eviction does not cross
  authorization boundaries because a cache miss simply rebuilds under the
  requesting user's own identity.

### 2. `_BLUEPRINT_CACHE`
- **location:** `app/api/v1/animation_router.py`
- **max size:** `500`
- **TTL:** `1800` s (30 min)
- **eviction:** LRU
- **rationale:** Blueprints are regenerable from the topic/description, same as
  video projects. 500 entries bounds memory. Owner-404 semantics preserved.

### 3. `_SESSIONS`
- **location:** `app/services/lesson_player_service.py`
- **max size:** `2048`
- **TTL:** `3600` s (1 hour)
- **eviction:** LRU
- **rationale:** Session state is lightweight and a new session can be started
  on demand. 1 hour matches a reasonable lesson-player session lifetime. 2048
  concurrent in-flight sessions per process is a generous, safe bound.
- **concurrency / iteration:** `get_state` iterates all sessions to find an
  active one; `BoundedCache.items()` returns a bounded snapshot list.

### 4. `_memories`
- **location:** `app/services/educational_memory_service.py`
- **max size:** `5000`
- **TTL:** `1800` s (30 min)
- **eviction:** LRU
- **rationale:** DB-backed. The in-memory copy is a read/write cache; eviction
  or expiration loses nothing (the authoritative row lives in PostgreSQL).
  `on_evict` is **not** required because values are persisted via
  `save_to_db` when the owning session flushes; a dropped cache entry only means
  the next read reloads from DB.
- **privacy/security:** `reset_memory` / `delete_memory` now use
  `BoundedCache.delete`, preserving the "purge this user's memory" contract.

### 5. `_contexts`
- **location:** `app/services/learning_context_service.py`
- **max size:** `2048`
- **TTL:** `1800` s (30 min)
- **eviction:** LRU
- **rationale:** Learning contexts are in-memory state for active learner
  sessions, rebuildable on new session creation. 2048 bounds concurrent
  contexts; 30 min bounds their lifetime.

### 6. visual `_cache`
- **location:** `app/services/visual_intelligence_service.py`
- **max size:** `200`
- **TTL:** `1800` s (30 min)
- **eviction:** LRU
- **rationale:** Cache of generated `VisualLearningModel` keyed by
  content-hash. Models are regenerable and the generation pipeline is the
  expensive path this cache exists to avoid re-running. 200 entries is a modest,
  safe cap; 30 min matches the generation cadence.
- **note:** this cache is **per-instance** (not a singleton) — each
  `VisualIntelligenceService()` has its own `_cache`. Bounding it is still
  valuable because routers instantiate new services per request.

## 5. Concurrency model

All six caches are **process-local** runtime state. They are accessed primarily
by the FastAPI async handlers (single asyncio event loop per worker process)
and service singletons. Each `BoundedCache` uses a `threading.Lock` as a safety
net for any concurrent callers, but the primary access pattern is the asyncio
single loop.

**These caches are NOT cross-replica / cross-process consistent.** Each process
has its own independent copy. This matches the pre-existing architecture where
these were module-level `dict`s; WS4 only bounds their growth, it does not make
them distributed.

## 6. Observability

Lightweight observability **was not added**. Cache hit/miss/eviction/expiration
metrics are out of WS4 scope (the P4 metrics registry is unchanged). The visual
cache already logs a `visual_intelligence_cache_hit` on hits. No noisy logging
was introduced.

## 7. Memory safety & performance

- **Maximum cache size is enforced** — a `set` that would exceed `max_size`
  immediately evicts the LRU entry, so a cache can never grow past its cap, even
  under repeated insertion.
- **Expired entries do not accumulate** — TTL expiration is checked on every
  read and the expired entry is removed (with `on_evict` firing).
- **Repeated insertion stays bounded** — tested with 1000 inserts into a
  max-5 cache (stays at 5).
- **Complexity** — set/get/delete/contains are O(1) amortized; eviction is O(1)
  per evicted item; enumeration helpers are O(n) but bounded by the cap.

## 8. Bounding entry count vs value size

Bounding the **entry count** is the primary memory-control mechanism. The
individual **values** can still be large (e.g., a full `VisualLearningModel` or
a video project object). Byte-level memory accounting was **not** added, per
scope; the caps chosen (especially the tighter 200/500 caps for value-heavy
caches) make the trade-off safe for the current workloads.

## 9. Security & isolation

- Keys carry **user/session identity** (`owner_id` in video/blueprint entries,
  `user_id` in memories, `session_id` in contexts/sessions).
- Ownership-404 semantics are **unchanged** — enforced at read time against
  the cached entry's `owner_id`.
- Cache eviction/expiration **cannot** cross authorization boundaries: a cache
  miss simply reloads/rebuilds under the requesting user's own identity. No
  cross-user data exposure, no stale-session reuse across users.
- `delete`/`reset` privacy operations still fully purge the targeted user's
  memory.

## 10. Tests

**New:** `tests/unit/test_ws4_bounded_caches.py` (26 tests) — verifies each of
the six application caches is a `BoundedCache`, has the expected `max_size` and
`ttl`, enforces the cap under repeated insertion, and supports the get/set/
delete/pop/clear/items/iteration operations the call sites depend on.

**Extended:** `tests/unit/test_bounded_cache.py` (31 tests) — the original 4
LRU/size tests plus new coverage for:
- delete / pop / clear (present and missing keys)
- TTL expiration on get and contains; TTL refresh on get; no-ttl never expires
- eviction callback on size eviction / delete / pop / clear / TTL expiration
- eviction callback exceptions do not propagate
- touch, keys, values, items, iteration, get_value (read-only peek)
- repeated-insertion bounded growth
- replacement/update semantics

## 11. Verification

- `pytest tests/unit/test_bounded_cache.py -q` → **31 passed**
- `pytest tests/unit/test_ws4_bounded_caches.py -q` → **26 passed**
- `pytest tests -m "not postgres" -q` → **1049 passed, 12 deselected**
- `ruff check app tests scripts --no-fix` → clean
- `mypy app` → **85 errors / 25 files** (matches P3/P4-C3 baseline; zero new)
- `pytest tests/postgres -m postgres -q` → **12 passed** (live PostgreSQL)
- `alembic heads` → single head **`0028_ws10_idempotency_key_index`** (no
  migration added — MySQL rule respected; PostgreSQL-only preserved)
- `git diff --check` → clean (no whitespace errors)

## 12. Known limitations

- caches are **process-local**; not consistent across workers/replicas (matches
  existing architecture).
- byte-level memory accounting not added; the caps assume reasonably sized
  values per entry, which holds for the current workloads.
- expired entries are removed lazily on access, not by a background sweeper;
  this is fine because the hard size cap independently bounds total entries
  regardless of expiration.
- `_memories` eviction does not force an immediate `save_to_db`; a dropped cache
  entry simply reloads from the authoritative DB row on the next access (the
  value is persisted by `save_to_db` within the owning request lifecycle).

## 13. Scope compliance

Only the six scoped caches and the shared `BoundedCache` utility were modified.
No RAG redesign, no pgvector, no schema migration, no frontend change, no
dependency changes, no unrelated refactor. WS4 scope: **YES**.
