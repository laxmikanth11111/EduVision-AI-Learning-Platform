# RAG provenance — recorded result

Module: `app/ai/retrieval.py`
Tests: `tests/unit/test_retrieval_provenance.py` (5 tests)

Command:

```
.venv\Scripts\python.exe -m pytest tests/unit/test_retrieval_provenance.py -q --no-header --tb=short
```

- Date: 2026-09-15
- **Result: 5 passed**

## What is covered

- `semantic_retrieve_chunks_with_meta(embedding_service, db, content_unit_ids,
  query, top_k=3)` returns `RetrievedChunk` objects carrying provenance:
  `chunk_id`, `content_unit_id`, `position`, `similarity`, `content`, `snippet`.
- Similarity ranking across multiple content units; `top_k` respected;
  position tie-break stable.
- Content-only wrapper `semantic_retrieve_chunks` is preserved for existing
  callers (no API break).
- The tutor prompt path consumes the meta-carrying retrieval, so answers can be
  attributed to source (chunk + unit + position + similarity).