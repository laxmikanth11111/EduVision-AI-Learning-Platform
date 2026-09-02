# P4 / WS3 — Vector Semantic RAG Retrieval (Implementation Report)

## Status

**COMPLETE** — committed as part of the P4-C3/WS3 logical commit.

## 1. Objective

Move assistant/lesson RAG retrieval from positional-only chunk ranking to
**vector semantic retrieval** (embedding-similarity), preserving the existing
architecture and the deterministic positional fallback.

WS3 uses **application-side cosine similarity over the persisted
`ChunkEmbedding.vector` values**. This is **not** pgvector and **not**
database-native vector search — vectors remain stored in the existing JSONB
(Postgres) / JSON (SQLite) column and are compared in Python. This keeps a
single production engine (PostgreSQL) and requires **no schema migration**.

## 2. Existing retrieval behavior (before WS3)

`LearningAssistantService._retrieve_relevant_chunks` (in
`app/services/learning_assistant_service.py`) was positional-only:

1. Resolves `lesson_id → GeneratedLesson → presentation_id`.
2. Collects all `ContentUnit.id` rows for that presentation.
3. Selects `DocumentChunk` rows where `content_unit_id IN (cu_ids)`,
   `content IS NOT NULL` and `content != ''`, ordered by `position`, limited
   to the requested `limit`.
4. Truncates each chunk to `content[:500]` and returns the snippets.

Notably it did **not** use the query text, did **not** consult embeddings, and
did **not** filter soft-deleted chunks (a correctness gap relative to every
RAG repository method, which filters `deleted_at.is_(None)`).

## 3. Semantic retrieval implementation

The retrieval path was extended so that:

```
query text
   ↓
embedding provider (existing provider-agnostic EmbeddingProvider.embed)
   ↓
query vector
   ↓
application-side cosine similarity
   ↓
ChunkEmbedding.vector (active, same provider/model)
   ↓
threshold filter + deterministic rank
   ↓
top-k snippets (= the existing `limit` param)
```

New module-level helper `_cosine_similarity(query, candidate) -> float | None`
in `learning_assistant_service.py` — numerically safe, returns `None` (skips)
for missing/empty/malformed/dimension-mismatched/zero-norm vectors and never
propagates NaN/Infinity (clamped to `[-1, 1]`).

New service paths:

- `_retrieve_relevant_chunks(...)` — unchanged public shape; now attempts
  semantic retrieval when a provider is supplied (or available) and the query
  is non-empty, then falls back to positional.
- `_retrieve_relevant_chunks_semantic(...)` — embeds the query, loads active
  chunk/embedding candidates with **one bounded query**, computes cosine,
  filters by `TUTOR_RETRIEVAL_SIMILARITY_THRESHOLD`, and sorts
  deterministically: **similarity desc → position asc → chunk id**.
- `_retrieve_relevant_chunks_positional(...)` — the original positional query
  (unchanged behavior plus the soft-delete filter).

The `limit` argument remains the top-k (the assistant calls it with `limit=3`),
reusing the existing applied retrieval limit rather than introducing a new
configuration. The candidate-set size is bounded by
`TUTOR_EMBEDDING_SEARCH_LIMIT` (default 200).

## 4. Vector storage (verified)

- Model: `ChunkEmbedding.vector` — `list[float] | None` stored via
  `JSON().with_variant(JSONB(), "postgresql")`.
- Production: **PostgreSQL JSONB**; tests: **SQLite JSON**.
- No pgvector, no `Vector` type, no vector index (HNSW/IVFFlat). None were
  added.
- Active-embedding predicate (`_active_embedding_predicate` in
  `app/repositories/rag_repository.py`) requires matching `provider`/`model`,
  `status == ACTIVE`, and `deleted_at IS NULL`.

## 5. New repository method

`DocumentChunkRepository.list_embedded_pairs_for_content_units(
content_unit_ids, provider, model, limit)` added in
`app/repositories/rag_repository.py` — a **single bounded inner join** of
`DocumentChunk` + active `ChunkEmbedding`, scoped to the content-unit set and
excluding soft-deleted chunks (`deleted_at IS NULL`). This avoids any
per-chunk SELECT/N+1 pattern.

## 6. Positional fallback (preserved)

Semantic retrieval falls back to positional when:

- `lesson_id` is falsy / lesson not found / no content units → `[]`.
- no provider supplied, or the query is empty.
- embedding generation fails (provider raises).
- the provider returns no vectors.
- no valid vectors exist among the candidates.
- every candidate is below the similarity threshold.

The positional path is deterministic (`position asc, chunk id asc`) and
now also filters `deleted_at IS NULL` for consistency with `existing RAG
policy`.

## 7. Ownership / security boundaries

Ownership authorization is **NOT** performed inside
`_retrieve_relevant_chunks`; it remains an **API/service-layer responsibility**
(unchanged from the pre-WS3 architecture). Retrieval itself is scoped strictly
to the caller-provided `lesson_id` and its presentation's content-unit set, so
chunks belonging to any other user's presentations are never candidates. This
means WS3 does not weaken the P1/P2 ownership guarantees; a cross-user
regression test asserts user B's content never surfaces when retrieving via
user A's lesson.

Soft-deleted chunks (`DocumentChunk.deleted_at` set) are excluded by the
repository predicate in both semantic and positional paths.

## 8. Performance characteristics

- **Database retrieval complexity:** one indexed inner join over the content
  units' chunk set, bounded to `TUTOR_EMBEDDING_SEARCH_LIMIT` rows
  (`O(candidate_count)` rows from DB, no N+1).
- **Cosine computation complexity:** `O(candidate_count × dimension)` in
  Python.
- **Memory:** bounded — at most the candidate-set vectors and the returned
  top-k snippets are held in memory.
- Application-side cosine is deliberately **not** equivalent to a
  database-native vector index; this is the current WS3 strategy and the
  trade-off is documented (linear scan of the bounded candidate set in the
  request process).

## 9. Failure handling

- **Invalid vectors** (empty, malformed/non-numeric, null, dimension-mismatch,
  zero-norm): skipped — never crash the whole retrieval.
- **Embedding-service failure:** caught; falls back to positional.
- **NaN/Infinity:** guarded before ranking; similarity is always finite.
- Any unexpected exception in the retrieval path is caught and degrades to
  `[]` (matching the pre-existing fail-safe behavior).

## 10. Tests

New file `tests/unit/test_rag_semantic_retrieval.py` (22 tests):

- cosine numerical safety (identical, orthogonal, zero-norm, empty,
  dimension-mismatch, malformed, `None`, finite-clamp) — pure function.
- high-similarity ranks first; lower-similarity below higher.
- top-k `limit` respected.
- deterministic ordering for equal similarity (position tiebreak).
- zero-norm / dimension-mismatch / malformed / missing vector skipped without
  crash.
- no valid vectors → fallback; embedding failure → fallback; no lesson → `[]`;
  `provider=None` → positional fallback.
- **cross-user ownership isolation** (user B's chunk never retrieved via user
  A's lesson).
- **soft-deleted chunk excluded** from semantic retrieval.

## 11. Verification

- `pytest tests/unit/test_rag_semantic_retrieval.py -q` → **22 passed**
- `pytest tests -m "not postgres" -q` → **996 passed, 12 deselected**
- `ruff check .` → clean
- `mypy app` → **85 errors / 25 files** (matches P3/P4-C2 baseline; zero new)
- `pytest tests/postgres -m postgres -q` → **12 passed** (live PostgreSQL)
- `alembic heads` → single head **`0028_ws10_idempotency_key_index`** (no
  migration added)

## 12. Known limitations

- Application-side cosine is a **linear scan** of the bounded candidate set,
  not an index-backed ANN / HNSW search; suitable for the current
  per-lesson/presentation candidate sizes bounded by
  `TUTOR_EMBEDDING_SEARCH_LIMIT`.
- No new retrieval-latency/relevance metric was added (out of WS3 scope;
  `TUTOR_*` settings remain partially unwired).
- The `TUTOR_RETRIEVAL_*` settings exist for the wider tutor workstream; WS3
  wires `TUTOR_EMBEDDING_SEARCH_LIMIT` and
  `TUTOR_RETRIEVAL_SIMILARITY_THRESHOLD` while `limit` (top-k) stays the
  existing applied argument.
- `get_embedding_provider()` singleton is the wired production source resolved
  inside `_retrieve_relevant_chunks` when no provider is injected; the method
  accepts an injectable provider for testability. If no provider is configured,
  the semantic path is skipped and positional fallback is used.