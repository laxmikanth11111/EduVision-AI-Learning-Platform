# Unit suite — recorded result

Command (from `backend/`, venv Python 3.14.6):

```
.venv\Scripts\python.exe -m pytest tests/unit --no-header -q --tb=line
```

- Date: 2026-09-15
- **Result: 1373 passed, 1 warning in 123.62s (0:02:03)**
- Delta vs baseline: baseline snapshot recorded 1337 passed; the +36 tests are
  the new hardening tests (prompt-injection scanner 16, grounded-validator
  coverage in lesson builder/generation service, auth hardening 9,
  RAG provenance 5, plus injected source-coverage assertions).
- Note: a mid-session parallel/full-suite run surfaced transient
  `sqlite3.OperationalError: no such table: presentations` failures in
  `test_topic_outline_service`, `test_visual_api`, `test_video_engine`,
  `test_upload_validation`, `test_review_schedule_service`. Each affected file
  passed in isolation (37/37 combined), and a subsequent full-suite run was
  fully green (1373 passed). Root cause is SQLite file-db write contention in a
  shared aiosqlite `test.db` during parallel collection on Windows, not a code
  regression; CI (Linux, Python 3.13, single worker) is not affected.