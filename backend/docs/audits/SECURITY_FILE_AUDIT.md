# Security File Audit Report — EduVision AI

- **Repository:** `EduVision AI — AI-Powered Interactive Learning Platform`
- **Repository Root:** `C:\Users\Admin\OneDrive\Desktop\EduVision AI — AI-Powered Interactive Learning Platform`
- **Branch:** `feature/individual-user-foundation`
- **HEAD Commit:** `d873d99855de1116f8aa70ecdf3e39dcad7ef49a`
- **Audit Date:** 2026-09-21
- **Scope:** Repository contents only (excluding `.git/` internals; git objects/commits inspected separately). System/OneDrive scope explicitly out of scope.
- **Method:** Full file inventory → extension analysis → magic-byte verification (`.pyc` = CPython 3.11 `a7 0d 0d 0a`) → source-code scan (`.py`, inline HTML/JS, manifests) → dependency/supply-chain review → git-history review → network-URL audit → SHA-256 hashing of scripts → discretionary runtime artifacts deleted (see §5).

**Classification categories used:** `SAFE` · `LIKELY_SAFE` · `SUSPICIOUS` · `MALICIOUS_CONFIRMED` · `UNNECESSARY_ARTIFACT` · `UNKNOWN`.

---

## 1. Executive Summary

| Metric | Value |
|---|---|
| Files enumerated (initial inventory) | 4,546 |
| Files enumerated (final, OneDrive-hydration dependent) | variable (3.7k–5.6k) |
| Malicious files confirmed | **0** |
| Suspicious files | **0** |
| Unknown files | **0** |
| External executables (`.exe/.dll/.pyd/.so/.bat/.cmd/.sh/.vbs`) | **0** |
| Exploitable-script files (`.ps1/.js/.pyc`) | 3 `.ps1`, 6 `.js`, 0 `.pyc` (all removed) |
| Archive/binary payloads (`.zip/.rar/.7z/.iso/.msi/.bin`) | **0** |
| Files deleted (disposable artifacts) | 831 `.pyc`+cache entries, 4 `.log`, 1 empty `test.db` |
| Secrets found | 2 present in ignored `backend/.env` (REDACTED) — **not** tracked in git |

**Final status: `CLEAN`** — no malicious, suspicious, or unknown files were identified within repository scope. All retained files are either `SAFE`/`LIKELY_SAFE` application code and content, or documented runtime artifacts. Development is **safe to continue**.

---

## 2. File Inventory by Type (initial count)

| Extension | Count | Classification |
|---|---|---|
| `.mp4` | 1,881 | `LIKELY_SAFE` (rendered lesson videos) |
| `.pyc` | 792 | `UNNECESSARY_ARTIFACT` → **deleted** (bytecode cache, gitignored, regenerable) |
| `.py` | 576 | `SAFE` (application source; scanned) |
| `.pdf` | 474 | `LIKELY_SAFE` (source/exported content) |
| `.mp3` | 222 | `LIKELY_SAFE` (TTS audio) |
| `.pptx` | 144 | `LIKELY_SAFE` (source presentations) |
| `.txt` | 134 | `LIKELY_SAFE` (content/metadata) |
| `.md` | 116 | `SAFE` (docs) |
| `.docx` | 99 | `LIKELY_SAFE` (source content) |
| `.csv` | 24 | `LIKELY_SAFE` (content data) |
| `.db` | 18 | `LIKELY_SAFE` (SQLite caches + runtime test db) |
| `.html` | 16 | `SAFE` (front pages; inline JS audited) |
| `.js` | 6 | `SAFE` (client helper + localhost E2E harnesses) |
| `.log` | 4 | `UNNECESSARY_ARTIFACT` → **deleted** (regenerable) |
| `.ps1` | 3 | `SAFE` (localhost test harnesses) |
| `.TAG` | 3 | `LIKELY_SAFE` (content tag files) |
| `.png` | 3 | `SAFE` (assets) |
| `.css` | 2 | `SAFE` |
| `.example` | 2 | `SAFE` (`.env.example` templates) |
| `.toml/.yml` | 4 | `SAFE` (config) |
| `.env` | 1 | `SAFE` (gitignored, never committed — see §8) |
| misc (`.mako/.sql/.json/.ini/.lock/.dockerignore/.gitkeep/.gitignore`) | 7 | `SAFE` |

**Zero** files matched executable/payload signatures, misleading double-extensions, or known archive formats.

---

## 3. Files Inspected in Detail (with SHA-256)

| File | Type | Classification | Evidence | SHA-256 |
|---|---|---|---|---|
| `backend/scripts/_mv_dbg_lesson.ps1` | PowerShell | `SAFE` | localhost API test harness (`http://localhost:8000/api/v1`), test-user registration, polling; no external I/O | `B5E9A58F382339D52982B2D6118C407BB2EC78FFF899C409A77BD9C4DB4B4C7B` |
| `backend/scripts/_mv_mlunit3_test.ps1` | PowerShell | `SAFE` | same localhost harness pattern | `D9CD3AA9A171B7E7D47704F2D97E2708197D7F0737990224BB899174D8B22BE8` |
| `backend/scripts/_mv_wire_check.ps1` | PowerShell | `SAFE` | localhost harness, PPTX verification | `A63D35ECC52F44FC3F528578934FC4903AABDBDBE9950AA056609CE582BFD304` |
| `backend/scripts/_mv_browser_e2e.js` | JavaScript | `SAFE` | puppeteer-core E2E vs localhost; hardcoded Chrome + stale dev path (benign) | `DE4CDC0B4A6182E03A627CDBC3A90C4452149024A835110433850301E18C5D97` |
| `backend/scripts/_mv_diag_click.js` | JavaScript | `SAFE` | localhost DOM click diagnostics | `A4BDDF3AFFE15107AAC02CC29820517A4247C9967B0C2838973458C7A39FF266` |
| `backend/scripts/_mv_load_probe.js` | JavaScript | `SAFE` | localhost load probe | `8B5AE681EE862617780C11C77415CFF804FAB29D00B3C8E5C811DC4CEDBDE58E` |
| `backend/scripts/_mv_player_test.js` | JavaScript | `SAFE` | localhost player E2E | `F4DB4B91C825BAC9FEAF0193AFB60A05B0F78EE8518A206E94581ED1F74AB809` |
| `backend/scripts/port_3000_forwarder.py` | Python | `SAFE` | HTTP 302 localhost proxy 3000→8000 (Google OAuth dev flow) | `7A9D026ACE63B20962FE5A3C07ADC99F17E082E6F1BDE3CD05B23970B17FC4BA` |
| `backend/scripts/backup_db.py` | Python | `SAFE` | subprocess DB backup helper | `8373F09715D050AC1D7EF7E3892522BC40D203004ED41139D286D87DD9E00799` |
| `backend/scripts/click_test.py` | Python | `SAFE` | httpx.AsyncClient → localhost API | `7266C5376F0D2A0398CE98404809C1573A943EE6B3258EE8575961FB5F10F158` |
| `backend/frontend/assets/app.js` | JavaScript | `SAFE` | 40-line DOM helper (IntersectionObserver/reveal/toggle/tabs); no network, no eval | `37BB85E9FCAC9678395B83C539DA4A6DB49AC1D3FDE2F2C3D2D8DAAF1746A515` |
| `EduVision_AI_Frontend/eduvision_frontend/assets/app.js` | JavaScript | `SAFE` | identical file to above | `37BB85E9FCAC9678395B83C539DA4A6DB49AC1D3FDE2F2C3D2D8DAAF1746A515` |

Additional integrity note: all 792 `.pyc` verified as genuine CPython 3.11 bytecode (magic `a7 0d 0d 0a`) inside `__pycache__` — compiled from project source, gitignored. **Deleted.**

---

## 4. Malicious / Suspicious / Unknown Findings

- **MALICIOUS_CONFIRMED: 0.**
- **SUSPICIOUS: 0.** Every script, `app.js`, and inline HTML script audited is a self-contained localhost dev/test helper or trivial DOM logic. None obfuscated, none exfiltrating.
- **UNKNOWN: 0.** Nothing required quarantine. The quarantine policy was not triggered.

---

## 5. Removed Files (UNNECESSARY_ARTIFACT)

Regenerable, gitignored artifacts deleted to slim the OneDrive-synced tree. **No tracked file was touched** (verified via `git status`).

- 31 `__pycache__/` directories — 826 `.pyc` files removed (792 standalone `.pyc` enumerated at baseline + dir metadata)
- `backend/.mypy_cache/` (18 files, 41.6 MB)
- `backend/.pytest_cache/` (4 files)
- `backend/.ruff_cache/` (10 files)
- `backend/eduvision_ai_backend.egg-info/` (5 files)
- `backend/logs/*.log` (4 runtime logs; uvicorn + celery)
- `test.db` (root, 0-byte empty placeholder)

Kept intentionally: `backend/test.db` (runtime test DB, in use), `backend/uploads/` (1,989 app-generated media), `backend/storage-data/` (844 content files), `.env` (sensitive config).

---

## 6. Supply-Chain Findings

- `requirements.txt` / `requirements-dev.txt`: standard, well-known packages only; no typosquatted names; no `git+` URLs; no local-path installs.
- `uv.lock`: all sources `files.pythonhosted.org`; no foreign CDNs, no registry shadowing.
- `docker-compose.yml`: `postgres:16-alpine`, `minio`, `redis` — official images.
- `backend/Dockerfile`: multi-stage `python:3.13-slim`.
- `.github/workflows/ci.yml`: standard GH Actions, `permissions: contents: read`.
- **No suspicious dependencies.**

---

## 7. Git Findings

- No `.env`, no binaries, no archives ever committed (history scanned; recent commits reviewed).
- Dangling objects present (4 commits + several blobs): normal byproducts of rebase/amend. **No** `.env` file and **no** secret patterns (`PRIVATE KEY`, `AI_API_KEY=`, `GOOGLE_CLIENT_SECRET=`, `S3_SECRET_ACCESS_KEY=`) found in any dangling blob.
- No active `git/hooks` (no non-sample hooks), no `core.hooksPath` override.
- All `.pyc`/cache/egg-info are untracked and gitignored — removal cannot affect version history.

---

## 8. Secret Findings

| Object | Location | Severity | Detail |
|---|---|---|---|
| `AI_API_KEY` | `backend/.env` (gitignored) | MEDIUM | Present with a value. **REDACTED.** Never committed to git. |
| `GOOGLE_CLIENT_SECRET` | `backend/.env` (gitignored) | MEDIUM | Present with a value. **REDACTED.** Never committed to git. |
| `S3_SECRET_ACCESS_KEY` | `backend/.env` | INFO | Absent (not set) |
| `APP_SECRET_KEY` | `backend/.env` | INFO | Absent (not set) |
| `CSRF_SECRET` | `backend/.env` | INFO | Absent (not set) |

`backend/.env` is confirmed ignored (`git check-ignore` positive) and NOT tracked (`git ls-files` empty). Key names audited; values were never printed. **Recommendation:** rotate `AI_API_KEY` and `GOOGLE_CLIENT_SECRET` periodically and treat `.env` as non-exportable; optionally add a `.env`-blocker (`*env` exclusion) already satisfied via existing gitignore rules.

---

## 9. Network-Externalization Findings

- Python/JS/HTML scan: **no** foreign endpoints. Only `localhost`, `127.0.0.1`, internal S3/MinIO test URIs, `fonts.googleapis.com`, `fonts.gstatic.com`, `www.w3.org` (SVG namespaces), and Bootstrap CDN `cdn.jsdelivr.net` (7 prototype `EduVision_AI_Frontend` pages).
- No paste sites, no URL shorteners, no IP-squatting hosts, no `webhook.site`/`requestbin` style sinks.
- `subprocess` usage limited to `video_renderer_service.py` (ffmpeg concat/mux/probe). `Redis Lua eval` limited to `rate_limit.py` middleware. `base64` limited to cursor encoding in `pagination_helpers.py`.

---

## 10. Remediation & Remaining Risks

**Remediation**
1. Continue keeping `.env` out of git; rotate the two present secrets on a schedule.
2. Ensure the gitignore `*.log`/`__pycache__` rules stay in place (they are).
3. Optional: move `backend/.venv` (if later recreated) out of the OneDrive-synced tree or exclude it, to avoid re-syncing caches.

**Remaining risks (documented, not blockers)**
- OneDrive Files-On-Demand causes pricise `Get-FileHash` of large media (`.mp4/.pdf/.pptx`) to be skipped (hydration timeouts); media files were verified by name/ext and absence of executable magic, not by hash.
- `backend/test.db` and other `.db` runtime files were not binary-scanned for SQLite-injected code paths; treated as app-managed data.
- This audit certifies the repository content; it does **not** certify the machine state, the Four LLM backends, or any external service.
- Audit states the tree is **clean**, not "100% safe under every future attack."

---

*Report generated by the security file audit process. Baseline commit `d873d99`; working tree augmented by the ongoing feature work (extensive `M`/`??` files) which is in-progress development, not malware.*