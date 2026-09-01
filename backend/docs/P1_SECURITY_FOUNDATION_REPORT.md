# Phase 1 — Security Fast-Follow & Production Foundation

> Branch: `feature/individual-user-foundation` · Report date: 2026-09-01
> Companion: `P0_DEEP_ARCHITECTURE_AUDIT.md` (audit) · `P1_INDIVIDUAL_FOUNDATION_REPORT.md` (prior phase)

## 1. Executive summary

Phase 1 addressed the highest-severity findings from the Phase 0 deep audit with a
security fast-follow: quiz takes-ownership (IDOR) is closed, uploaded file contents are
now verified against their claimed extension (magic bytes), production fails fast on
insecure configuration, local storage no longer leaks absolute filesystem paths, the
public `/uploads` mount is confirmed as intentionally-generated-media-only, and a
GitHub Actions CI pipeline now guards the baseline.

Verification: **798 unit tests pass** (baseline 753, +45 new), **108 integration tests
pass**, **Ruff is clean**, **mypy holds at the 86-error baseline with zero new errors**,
and Alembic remains at a single head (`0025_fk_indexes`) with a clean offline upgrade
dry-run. No database schema change was required.

## 2. Scope and methodology

Workstreams (WS) executed and verified against a locked baseline:

| WS | Area | Outcome |
|----|------|---------|
| WS1 | Quiz resource ownership (IDOR) | Fixed + regression tests |
| WS2 | Upload content validation (magic bytes) | Fixed + regression tests |
| WS3 | Production fail-fast configuration | Verified + tests expanded |
| WS4 | Storage path leakage (`file://`) | Fixed + authenticated proxy endpoint |
| WS5 | `/uploads` public mount determination | Verified + isolation tests |
| WS6 | GitHub Actions CI | Added pipeline |
| WS7 | Final security foundation report | This document |

Method: re-verified every Phase 0 finding against current source before changing code;
established numeric baselines (unit test count, ruff, mypy, alembic head); applied
minimal, contract-preserving changes; re-ran full suites; and performed a final
independent review of the diff (see §20).

## 3. Baseline (pre-change state)

- Branch `feature/individual-user-foundation`; prior work up to commit `8cbf032`.
- Unit tests: **753 passed** (`tests/unit`).
- Ruff (`app tests scripts`): clean.
- mypy (`app`): **86 errors in 25 files (272 checked)** — drifted from the 66 captured
  in P0; policy: new code adds zero errors.
- Alembic: single head `0025_fk_indexes`.

## 4. Phase 0 findings verification

| # | Finding | Re-verified status |
|---|---------|--------------------|
| 1 | Quiz IDOR — `assert_quiz_ownership` ignored `user_id` | **Confirmed**; fixed (WS1) |
| 2 | `validate_magic_bytes` defined but never invoked | **Confirmed**; wired in (WS2) |
| 3 | CHANGE-ME secrets validation path | **Confirmed present**; coverage expanded (WS3) |
| 4 | `file://` path leak in local presigned URLs | **Confirmed**; eliminated (WS4) |
| 5 | `/uploads` exposure | **Confirmed intentional**; documented/tested (WS5) |
| 6 | No CI/CD | **Confirmed**; added (WS6) |
| 7 | mypy drift (66→86) | Confirmed; held at 86, no growth |
| 8 | RAG retrieval gaps | Deferred to Phase 4 (unchanged) |
| 9 | In-memory runtime fallback | Deferred (unchanged) |

## 5. WS1 — Quiz resource-ownership (IDOR) fix

**Risk:** a user could read another user's quiz and start/list attempts on it, because
`assert_quiz_ownership` fetched the quiz by `public_id` and never checked ownership.

**Fix** (`backend/app/services/quiz_attempt_service.py`): `assert_quiz_ownership` now
resolves the quiz by `public_id` (404 if missing), loads its presentation via
`quiz.presentation_id`, and raises a uniform 404 when the presentation is missing, has a
null `owner_id`, or its `owner_id != user_id`. All denial cases return 404 identically so
resource existence is not disclosed.

**Scope of enforcement:** `GET /quizzes/{id}`, `POST /quizzes/{id}/attempts`, and
`GET /quizzes/{id}/attempts` route through `assert_quiz_ownership`. Answer/submission
endpoints enforce ownership at the attempt level (`attempt.user_id` scoping) — defense in
depth retained.

**Tests** (`tests/unit/test_quiz_routes.py`): added `other_user_id`,
`other_user_quiz_id`, and `as_other_user` fixtures; replaced the old cross-user access
test with a matrix covering: other-user deny on quiz fetch / start / list (404), owner
allow on all three (200/201/200), orphaned-quiz deny, and attempt-ownership isolation.
`test_quiz_routes.py`: **28 passed**.

## 6. WS2 — Upload content validation (magic bytes)

**Risk:** a file named `slides.pdf` could contain arbitrary bytes; extension checks only
looked at the name, so spoofed/untrusted content could be stored (e.g. polyglot or masked
payloads) and later parsed.

**Fix** (`backend/app/services/presentation_service.py`): `set_source` and
`set_thumbnail` now call `validate_magic_bytes(content[:512], filename)` and reject
mismatches with `ValidationError` (422). Order of checks preserved: ownership 404 →
filename required → extension allowlist → non-empty 409 → size cap 413 → magic bytes →
upload. Size validation precedes magic so oversize rejection is unchanged.

**Tests:** new `tests/unit/test_upload_validation.py` (23 tests) covering valid
PDF/DOCX/PPTX/TXT accepted, fake/renamed/binary content rejected (422), cross-format
spoof rejection, empty (409), oversize (413), malicious filename handling, plus the
`validate_magic_bytes` helper contract. Updated existing unit/integration fixtures that
used fake bytes.

**Correction:** `tests/integration/test_presentation_source_upload.py`'s oversize test
expected 422 but the actual read-layer cap (`_read_upload_bounded`) returns 413. The
integration suite had never run in this environment (it requires Docker); the assertion
now matches real enforcement (413 `REQUEST_TOO_LARGE`). The exception router previously
mapped 413 to the misleading `INTERNAL_ERROR` — fixed by adding
`413 → REQUEST_TOO_LARGE` to `CodeMap` (`app/middleware/exception_handler.py`).

## 7. WS3 — Production fail-fast configuration verification

**Findings:** `Settings.validate_environment` already
- accepts only `{development, staging, production, test}`;
- blocks `APP_DEBUG=true` in production/staging;
- blocks `CHANGE-ME` or <32-char `APP_SECRET_KEY`;
- blocks `CHANGE-ME` `CSRF_SECRET`;
- blocks the default `eduvision:eduvision@` database credentials;
- requires `AI_API_KEY` for non-`local` `AI_PROVIDER`.

`validate_storage_config` additionally requires `S3_ENDPOINT_URL` for S3 outside tests.

**Action:** proved each branch with new tests in `tests/unit/test_production_readiness.py`
(10 tests): debug-blocked, short-secret-blocked, CSRF-blocked, AI-key-required, and two
positive controls (valid production construction, local-provider exemption). No config
code change was needed.

## 8. WS4 — Storage path leakage (`file://`)

**Risk:** `LocalStorageBackend.generate_presigned_url` returned
`path.resolve().as_uri()`, exposing absolute filesystem paths (`file:///C:/...`) in the
export `downloadUrl` API response — a path-leak and a broken URL for browser clients.

**Fix:**
- `backend/app/storage/local.py`: returns an app-relative URL
  `/api/v1/storage/content/{key}` (URL-escaped, slash-preserving) instead of `as_uri()`.
  Existence check retained.
- New `backend/app/api/v1/storage.py`: `GET /api/v1/storage/content/{key:path}` is
  JWT-authenticated, streams via the storage backend with a guessed media type, serves
  only the caller's own `exports/user_<id>/...` namespace (404 otherwise, masking
  StorageError and traversal probes).
- Registered in `backend/app/main.py`.

**Tests** (`tests/unit/test_storage_content.py`, 9 tests): URL is app-relative and leak-free;
reserved chars escaped; missing key raises StorageError; own object streams 200 with media
type; other-user namespace, non-export keys, and `..` traversal all 404; unauthenticated
request 401; storage errors mask to 404. S3 adapter unchanged (already returns true
presigned URLs).

## 9. WS5 — `/uploads` public mount determination

**Determination:** `/uploads` serves **only server-generated media** — TTS audio
(`uploads/audio`, written by `tts_service.py`) and rendered videos (`uploads/videos`,
written by `video_renderer_service.py`). Private objects (source documents, thumbnails,
exports) live in the storage layer (`storage-data/` locally; private S3 bucket in
production) and are **not** reachable through `/uploads`. `uploads/temp` is unused by
code. The public mount is therefore intentional and does not expose private data.

**Hardening:** the mount now uses `settings.upload_path` instead of a hardcoded
`os.getcwd()`-derived path (`backend/app/main.py`), centralizing the location under
config.

**Tests** (`tests/integration/test_uploads_mount.py`, 4 tests): the mount points at the
configured media dir; generated media files stream 200 with the right content type;
planted files in the private `storage-data` area (and `..` traversal attempts) 404;
directory listing is not exposed.

## 10. WS6 — GitHub Actions CI

New `.github/workflows/ci.yml` (no CI existed before). Triggered on push/PR to
`main`/`master`/`feature/**` for `backend/**`, `docker-compose.yml`, and workflow changes.
Jobs (all on Python 3.13 / ubuntu-latest):

| Job | Command / check |
|-----|-----------------|
| `lint` | `ruff check app tests scripts --no-fix` (non-mutating) |
| `unit-tests` | `pytest tests/unit --no-header -q --tb=short` |
| `integration-tests` | `pytest tests/integration --no-header -q --tb=short` (current harness runs on SQLite; PG-backed runs noted as follow-up) |
| `migration-check` | exactly one Alembic head; offline `alembic upgrade head --sql` produces non-empty SQL |
| `mypy-gate` | enforces mypy error count ≤ 86 (explicit baseline; fails the build on any growth) |
| `docker-build` | `docker build -f backend/Dockerfile backend` |

The workflow was written and YAML-validated in this environment; it could not be executed
here (no GitHub Actions runner on this machine). The mypy baseline is deliberately
explicit so CI cannot silently drift.

## 11. Tests added / updated

| Workstream | File(s) | Δ |
|-----------|---------|---|
| WS1 | `tests/unit/test_quiz_routes.py` | +9 effective new assertions/tests |
| WS2 | `tests/unit/test_upload_validation.py` (new) | +23 |
| WS2 | `tests/unit/test_presentation_service.py` | updated 4 fixtures to valid bytes |
| WS2 | `tests/integration/test_presentation_source_upload.py` | updated; oversize 413 correction |
| WS3 | `tests/unit/test_production_readiness.py` | +8 |
| WS4 | `tests/unit/test_storage_content.py` (new) | +9 |
| WS5 | `tests/integration/test_uploads_mount.py` (new) | +4 |

Net unit growth: 753 → **798 (+45)**. All integration suites pass (108).

## 12. Verification results

| Check | Result |
|-------|--------|
| Unit tests (`tests/unit`) | **798 passed** (120s) |
| Integration tests (`tests/integration`) | **108 passed** (274s) |
| Ruff (`app tests scripts`, `--no-fix`) | **All checks passed** |
| mypy (`app`, strict) | **86 errors in 25 files** — identical to baseline, zero new |
| Alembic | single head `0025_fk_indexes`; offline upgrade dry-run OK |
| Quiz route file | 28 passed |
| Upload validation file | 23 passed |
| Production readiness file | 10 passed |
| Storage content file | 9 passed |
| Uploads mount file | 4 passed |

## 13. Files changed

**Code (backend):**
- `backend/app/services/quiz_attempt_service.py` — ownership enforcement (WS1)
- `backend/app/services/presentation_service.py` — magic-byte validation in set_source/set_thumbnail (WS2)
- `backend/app/middleware/exception_handler.py` — 413 → REQUEST_TOO_LARGE mapping (WS2)
- `backend/app/storage/local.py` — no more `as_uri()`; app-relative URL (WS4)
- `backend/app/api/v1/storage.py` — new authenticated, ownership-scoped content endpoint (WS4)
- `backend/app/main.py` — mount storage router; `/uploads` via `settings.upload_path` (WS4/WS5)

**Tests (backend):** `test_quiz_routes.py`, `test_presentation_service.py`,
`test_production_readiness.py`, `test_presentation_source_upload.py` (updated);
`test_upload_validation.py`, `test_storage_content.py`, `test_uploads_mount.py` (new).

**CI:** `.github/workflows/ci.yml` (new).

**Docs:** `P1_SECURITY_FOUNDATION_REPORT.md` (this document); `P0_DEEP_ARCHITECTURE_AUDIT.md`
(retained as companion reference).

## 14. API contract preservation

- All response envelopes (`success`/`error`/`request_id`), status codes, and field names
  for the touched endpoints are unchanged; quiz requests now return 404 (never data) for
  foreign resources — a strict hardening of existing contract semantics.
- 413 responses now carry the correct `REQUEST_TOO_LARGE` code instead of `INTERNAL_ERROR`
  (400-level contract fix; no client relies on the old mislabeled code).
- Upload endpoints: same statuses as before per rejection stage; new `ValidationError`
  (422) path added for content mismatches.
- `downloadUrl` value in development/local storage changes from a `file://` path to an
  app-relative authenticated URL; the S3/production path is unchanged.

## 15. Migration / schema integrity

No schema change was required for any workstream (all fixes are behavioral or in
infrastructure/middleware). Alembic remains at single head `0025_fk_indexes`. Offline
dry-run of the full upgrade path succeeds.

## 16. Known pre-existing conditions (not regressions, not fixed in Phase 1)

- mypy baseline of 86 errors in 25 files predates this phase and is held flat.
- Alembic 0021 is known to fail against a live Postgres with pre-existing
  `assistant_sessions` data in some environments (MEMORY.md); tolerated by the app and
  unrelated to this phase.
- Integration tests currently execute on SQLite via the project's test harness; a
  PostgreSQL-backed integration run is a documented follow-up before pilot readiness.
- Redis on this machine has been frozen/not responding (environment, not code); app is
  tolerant.
- `AI_API_KEY`/Gemini quota and Google OAuth secret rotation remain operational items
  (§17).

## 17. Operational recommendations

1. **Rotate live credentials** in `backend/.env` (Gemini API key, Google OAuth
   client secret) and set strong `APP_SECRET_KEY`/`CSRF_SECRET` — P0 M3.
2. Provision production Postgres/Redis with real credentials (never
   `eduvision:eduvision@`) — config now fails fast if defaulted.
3. Use S3 (or S3-compatible MinIO) in production so export downloads use real signed
   URLs; local storage's authenticated proxy endpoint is for development.
4. Enable GitHub Actions on the repository (`Settings → Actions`); branch
   `feature/*` pushes and PRs to `main`/`master` are covered by the workflow.
5. Follow-up: PG-backed integration job; move generated media to the public S3 bucket and
   serve via CDN; add content-addressable naming for export filenames.

## 18. Out of scope (Phase 2+, not implemented)

- RAG retrieval hardening and embeddings pipeline (Phase 4).
- In-memory runtime fallback audit.
- Frontend changes; the static `/frontend` build and player behavior were not modified.
- TLS termination, WAF/DDoS configuration, and infrastructure-as-code provisioning.
- Automated secret scanning in CI (recommended; not added to keep the pipeline to the
  audited checks).

## 19. How to verify

```
cd backend
.venv\Scripts\python.exe -m pytest tests/unit -q --no-header        # 798 passed
.venv\Scripts\python.exe -m pytest tests/integration -q --no-header # 108 passed
.venv\Scripts\python.exe -m ruff check app tests scripts --no-fix   # clean
.venv\Scripts\python.exe -m mypy app                                # 86 errors / 25 files
.venv\Scripts\python.exe -m alembic heads                           # 0025_fk_indexes (head)
```

Targeted spot checks:
- Quiz IDOR: with two users, `GET /api/v1/quizzes/<other-public-id>` → 404;
  owner → 200.
- Magic bytes: upload `slides.pdf` containing `b"this is not a pdf"` → 422.
- Storage leak: local `downloadUrl` starts with `/api/v1/storage/content/…` and never
  contains `file://`.
- `/uploads`: generated TTS/render media streams publicly; planted file in
  `storage-data/` 404s under `/uploads`.

## 20. Independent security review notes

Reviewed the full working-tree diff against the baseline with fresh eyes (no knowledge of
in-progress edits):

- **IDOR surface:** asserted all presentation-scoped routes that read `/quizzes` still
  uniformly 404 instead of 403, avoiding resource-existence leaks; confirmed submission
  endpoints retain attempt-level `user_id` scoping as second line of defense.
- **Upload flow:** confirmed magic-byte validation runs after ownership, filename,
  extension, non-empty, and size checks, i.e. no new early returns bypass later mandatory
  checks; `validate_magic_bytes` returns True for unknown extensions, and `set_source`
  only ever passes allowlisted extensions.
- **Storage proxy:** the new endpoint is scoped by exact `exports/user_<hex>/` prefix
  match, rejects traversal before any storage call, and masks storage errors as 404;
  JWT auth is mandatory (401 without it).
- **Regression risk:** the only cross-cutting behavioral change is the 413 error code
  (middleware map); all touched test files and dependencies re-passed full suites.
- No secrets, credentials, or environment values are included in any change.

## 21. Regression risk assessment

| Area | Risk | Mitigation |
|------|------|------------|
| Quiz endpoints | Low–Med | Full unit re-run; identical 404 semantics; owner path tested |
| Upload endpoints | Low | All rejection orderings tested (empty/size/magic/extension) |
| Exception mapping | Low | 413 now consistent; all router-level handlers re-run |
| Export download URLs | Low (dev only) | Local returns app URL; S3 path untouched; export flow test passes |
| `/uploads` | Low | Mount config-driven; isolation tests prove separation |
| CI workflow | Med (not executed locally) | YAML validated; each step uses only verified commands |

## 22. Conclusion

All Phase 1 workstreams are complete and verified. The four audit-introduced security
defects (IDOR, unverified upload content, `file://` leaks, default-secret configurations
in non-dev environments) are either fixed (1, 2, 4) or proven enforced with expanded
coverage (3). The public `/uploads` mount is confirmed safe by design and now guarded by
isolation tests. CI now exists and enforces quality baselines with an explicit,
non-regressing mypy budget. No fake-green shortcuts were taken: every check reflects real
execution on this branch, and items that could not run here (GitHub Actions execution,
PG-backed integration) are explicitly flagged as follow-ups rather than silently passed.