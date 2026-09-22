# EduVision AI — Security Verification Final Report

- **Verdict:** `B. REPOSITORY CLEAN — MACHINE NOT FULLY VERIFIED`
- **Date:** 2026-09-21
- **Auditor:** Senior Security Engineer / Malware Analyst (independent verification pass)
- **Prior baseline:** `backend/docs/audits/SECURITY_FILE_AUDIT.md` (previous pass; treated as baseline, not as certifying the machine)

---

## 1. Executive Summary

This pass independently re-verified the **EduVision AI repository** and conducted a **targeted, read-only, project-relevant machine assessment** (running processes, autostart locations, Run/RunOnce keys, scheduled tasks).

| Metric | Result |
|---|---|
| Malicious files (repository) | **0** |
| Suspicious files (repository) | **0** |
| Unknown files (repository) | **0** |
| Obfuscation indicators | **0** (all 16 matches benign, see §4) |
| Suspicious outbound destinations | **0** |
| Suspicious dependencies | **0** |
| Secrets committed to Git | **0** |
| Project-created persistence | **0** |
| Suspicious running processes | **0** |
| Files deleted during this pass | **0** (read-only pass) |
| Repository integrity | Intact (40 modified `M`, 54 untracked `??` — unchanged from baseline) |

The repository is **clean**. The machine is **partially assessed**: all EduVision-relevant runtime and persistence surfaces checked are benign; a full machine-wide endpoint scan was **not** performed and is **not justified** by repository evidence.

---

## 2. Exact Scope

- **In scope:** the repository only, plus a targeted read-only look at EduVision-relevant machine surfaces (running processes, user+common Startup folders, HKCU/HKLM Run/RunOnce, scheduled tasks filtered for EduVision/AI/vision/python names or paths).
- **Explicitly NOT scanned:** entire `C:\`, `C:\Users\*` personal folders, `C:\Windows`, `C:\Program Files`, `AppData` content beyond the Orient-listed autostart keys above, other project folders (e.g., `Desktop\AI visual learning`).
- **Classification standard:** SAFE / LIKELY_SAFE / TEMPORARY_ARTIFACT / POTENTIALLY_UNWANTED / SUSPICIOUS / MALICIOUS_CONFIRMED / UNKNOWN.
- **Deletion policy:** nothing was deleted this pass (previous pass removed only regenerable caches/logs inside the repo). All query commands were read-only.

---

## 3. Environment

| Item | Value |
|---|---|
| Repo root | `C:\Users\Admin\OneDrive\Desktop\EduVision AI — AI-Powered Interactive Learning Platform` |
| Branch | `feature/individual-user-foundation` |
| HEAD | `d873d99855de1116f8aa70ecdf3e39dcad7ef49a` (`d873d99`) |
| Parent | `57aaee3` |
| Working tree | 40 modified (`M`), 54 untracked (`??`) — in-progress feature work, no unexpected deletions |
| OS | Windows 11, build 26200 (Win32 NT 10.0.26200.0) |
| PowerShell | 5.1.26100.9444 |
| Git | 2.50.1.windows.1 |
| Python | **3.11.9** at `C:\Users\Admin\AppData\Local\Programs\Python\Python311\` — **NOT on PATH**; the `python`/`py` on PATH resolve to the **Windows Store stub** (`WindowsApps\python.exe`) which hangs (0-byte app-execution alias). `Python313\` directory exists but is **empty** (orphaned/partial install). Project `pyproject.toml` requires `>=3.13` — **environment/Python-version mismatch (3.11 vs required 3.13)**; `.pyc` bytecode in prior caches was CPython 3.11. |
| Node | v24.14.1 (`C:\Program Files\nodejs\node.exe`, real binary) |
| Docker | **Not installed** (no `Docker Desktop.exe`; `docker` command absent). Note: a leftover `HKCU\...\Run` entry "Docker Desktop" points at a non-existent binary — benign stale entry. |
| Note | An empty `C:\Users\Admin\AppData\Local\Programs\Python\Python313\` dir is present (dev-install leftover, not malware). |

---

## 4. Obfuscation Findings

611 code files scanned (`.py/.js/.ps1/.html/.css/.json/.ini/.toml/.yml/.mako/.sql`) against 30+ indicators: `Invoke-Expression`/`IEX`, `Start-Process`, `-EncodedCommand`, base64 decode chains, `Assembly.Load`, `CreateObject`+`WScript.Shell`, `eval()`, `exec()`, `pickle.loads`, `marshal.loads`, registry `reg add`, `schtasks`, `HKCU/HKLM`, `RunOnce`, DPAPI/credential APIs, browser-cookie dumps, webhooks/telegram/paste/onion references.

**Result: 16 string matches — every one verified benign.**

| Match | File | Why benign |
|---|---|---|
| `eval(` (Redis Lua) | `backend/app/middleware/rate_limit.py:297` | `redis.eval(SLIDING_WINDOW_SCRIPT,…)` — industry-standard rate-limit Lua atomic script. |
| `eval(` (jsdom/puppeteer) | `_mv_load_probe.js`, `_mv_player_test.js`, `_mv_browser_e2e.js`, `_mv_diag_click.js` | Test harnesses invoking player functions (`nextSlide()`, `goTo()`) in a sandboxed DOM; and `page.$eval/$$eval` (CSS-based DOM reads). Not code injection. |
| `eval(` (test mock) | `tests/integration/test_p17_redis_reliability.py:25` | A stub `async def eval()` recording calls on a fake Redis — unit-test double. |
| `__import__` | `app/utils/retry_helpers.py` (`__import__("logging")`), tests (`__import__("uuid")`, `__import__("app.main")`) | Lazy stdlib/app imports; static strings only, no attacker input. |
| `createObject` | `backend/frontend/player.html:1169` | `URL.createObjectURL(blob)` to download a transcript/export. Client-side Blob, safe. |
| `StartUp` / `startup` | `app/main.py`, `app/core/config.py`, `workers/celery_app.py`, `tests/*`, `scripts/init-db.sql` | App-lifespan migration config (`AUTO_MIGRATE_ON_STARTUP`), Celery broker retry flag, test fixtures, SQL init comment. |

**No** dynamically-constructed PowerShell, hidden windows, encoded commands, remote script downloads, executable extraction, registry mutation, service/scheduled-task creation, credential harvesting, cookie/database dumping, wallet access, SSH-key access, or suspicious DLL loading was found.

---

## 5. Network Findings

All external URLs in 611 source/config/doc files extracted and classified:

| Destination | Count | Classification | Evidence |
|---|---|---|---|
| `fonts.googleapis.com` / `fonts.gstatic.com` | ~20 | `LEGITIMATE` | Google Fonts on front pages + CSP allowlist in `app/middleware/security.py` |
| `www.w3.org` | ~12 | `LEGITIMATE` | SVG/W3C XML namespace in inline SVG (`player.html`, `c3_svg_renderer.py`) |
| `cdn.jsdelivr.net` | 7 | `LEGITIMATE` | Bootstrap CDN in `EduVision_AI_Frontend` prototype pages |
| `api.openai.com`, `generativelanguage.googleapis.com` | 4 | `PROJECT-REQUIRED` | LLM provider SDKs (`app/ai/providers/openai.py`, `gemini.py`) |
| `accounts.google.com`, `oauth2.googleapis.com`, `www.googleapis.com` | 3 | `PROJECT-REQUIRED` | Google OAuth in `app/api/v1/auth.py` |
| `console.cloud.google.com`, `github.com` | 2 | `DEVELOPMENT-ONLY` | Documentation links |
| `s3.amazonaws.com`, `example.com`, `mycompany-s3.example.com`, `test` | ~12 | `DEVELOPMENT-ONLY` | Test fixtures (`test_s3_adapter.py`, export/lifecycle tests) |
| Raw-IP URLs | 13 | `DEVELOPMENT-ONLY` | All `127.0.0.1`, `0.0.0.0` (localhost dev/test), `https://127.0.0.1:9000` (in-test MinIO) |

**No** URL shorteners, paste services, Discord/Telegram/webhook sinks, file-sharing services, `.onion`, or unknown external IPs. **No `UNKNOWN` or `SUSPICIOUS` destinations.**

Runtime connections (see §10) were likewise local-only or normal browser traffic.

---

## 6. Dependency / Supply-Chain Findings

- `backend/requirements.txt` (23 pinned packages) and `backend/requirements-dev.txt` (13): **all standard, well-known** — fastapi, uvicorn, pydantic, sqlalchemy, asyncpg, alembic, redis, celery, boto3, pypdf, pptx/docx, opencv-headless, numpy, pillow, gtts, edge-tts, httpx, jose, argon2, passlib, structlog, tenacity, orjson; dev: pytest stack, playwright, ruff/black/isort/mypy/pre-commit. **No typosquatting, no `git+`, no local paths, no install hooks.**
- `backend/uv.lock`: **all** artifact URLs on `files.pythonhosted.org` (official PyPI CDN). No custom indexes, no shadow registries.
- `backend/pyproject.toml` / `shared/pyproject.toml`: standard `setuptools.build_meta`; deps match requirements; no postinstall steps.
- No `package.json` / `package-lock.json` anywhere (frontend is static HTML; the only Node usage is dev IP-tooling).
- **No suspicious dependencies found.**

---

## 7. Secrets Findings

| Secret | Location | Git-tracked | Git-ignored | In history | Status |
|---|---|---|---|---|---|
| `AI_API_KEY` | `backend/.env` | No | **Yes** | **No** | `FOUND` (value REDACTED) — local only |
| `GOOGLE_CLIENT_SECRET` | `backend/.env` | No | **Yes** | **No** | `FOUND` (value REDACTED) — local only |
| Other keys (`AI_MODEL`, `REDIS_URL`, `CELERY_*`, Google OAuth IDs, embedding config) | `backend/.env` | No | Yes | No | Config, non-secret or locally set |

History-wide scan of all commits for `PRIVATE KEY`, `AKIA…`, `AIza…`, `sk-…`, GitHub tokens, Slack `xox…`, JWTs, `GOOGLE_CLIENT_SECRET=`/`AI_API_KEY=` with values → the only 5 hits were:
1. `.env.example` placeholders (`AI_API_KEY=your…` [34-ch], `GOOGLE_CLIENT_SECRET=…` [25-ch]) — templates, no valid secret.
2. `.github/workflows/ci.yml` — the string `-----BEGIN … PRIVATE KEY-----` is a **secret-scanning regex pattern** defined inside the CI secret-scan job, not a key.
3. `test_production_readiness.py` — asserts `AI_API_KEY=None` is rejected → unit-test logic, not a secret.
4–5. Docs mentioning "private" (prose).

**No real credentials exist anywhere in Git history.** No history rewrite was needed or performed.

---

## 8. Git-History Findings

- **No `.env`** ever existed in any commit tree (`git log --all --name-only`).
- Only binary-class files in history: the 3 legitimate localhost test harnesses `backend/scripts/_mv_{dbg_lesson,mlunit3_test,wire_check}.ps1`.
- Dangling objects (4 commits + blobs, from rebase/amend): **no `.env` files and no secret patterns** in any dangling blob (values checked for `PRIVATE KEY`, `AI_API_KEY=`, `GOOGLE_CLIENT_SECRET=`, `S3_SECRET_ACCESS_KEY=` — 0 hits).
- No binary archives, no executables, no `.bat/.cmd/.vbs`, no unusual scripts ever tracked.
- Recent history (`git log -10`) matches the branch's feature narrative (C3/C4 pipeline, P12–P17 persistence/reliability work); no unexpected commits.

---

## 9. Persistence Findings

**Project-created persistence: none.**
- Source-level scan for `schtasks`, `reg add`, `HKCU/HKLM` mutation, `RunOnce`, StartupFolder manipulation, service creation, CRON, hooks → **zero** matches; the only `startup`/`injection` strings are app-lifespan migration config and the app's own prompt-injection defense feature.
- `.github/workflows/ci.yml`: triggers are `push`/PR only — **no `schedule`/`cron` job** runs on the repo.
- `docker-compose.yml`/Dockerfile: standard dev images (Postgres/Redis/MinIO) with local volumes — expected development infrastructure, not an unexpected persistence mechanism.

**Machine autostart surfaces (targeted, read-only):**
- User + Common **Startup folders**: only `desktop.ini` (default). **No `.exe/.lnk/.ps1/.bat`.**
- **HKCU\…\Run**: OneDrive, Edge Update, Opera, Teams, Edge/Chrome session-start, stale `Docker Desktop` entry, and a preinstalled `Web Companion` (Lavasoft) entry — all unrelated to EduVision; none reference EduVision or encoded PowerShell.
- **HKCU\…\RunOnce, HKLM\…\RunOnce, WOW6432Node\…\Run**: empty.
- **HKLM\…\Run**: SecurityHealth (Defender tray), Realtek audio, Avast tray, Nearby Share — standard system/AV.
- **Scheduled tasks (216)**: filtered for edu/vision/ai/python/EduVision names/paths → only Windows/Opera system tasks (`EduPrintProv` is the Windows print provider, Defrag, Update, Opera AutoUpdate). **No EduVision-created task.**

---

## 10. Runtime-Process Findings

29 project-relevant processes enumerated (PID, executable, parent, command line):

- **postgres.exe** PID 9136 + 7 worker children — PostgreSQL 5432 listening (repo's primary DB). `EXPECTED`.
- **redis-server.exe** PID 6304 — Redis 6379 listening (rate-limit + Celery broker). `EXPECTED`.
- **chrome.exe** (~15, root PID 9028) — normal browser multi-process from `C:\Program Files\Google\Chrome\Application\`. `EXPECTED`.
- **node.exe** (PIDs 12944/10448/17608/21932) — `npx chrome-devtools-mcp@latest --autoConnect --no-usage-statistics` (two pairs: npx-launcher + worker). This is the IDE's DevTools MCP server (openCode/Antigravity tooling). `DEVELOPMENT EXPECTED`. No remote exfil; connects to Chrome DevTools locally.
- **powershell.exe** — terminal shell-integration processes + this audit's own command.
- **No python.exe/uvicorn/celery/docker processes running** (server not currently executing).

**Connections for audited PIDs (read-only):** Redis/Postgres bound to dev ports (local only). Chrome's network-service process: 443 → `172.64.148.235` (Cloudflare CDN, normal browsing) and 5228 → `192.178.158.188` (Google push service, normal Chrome). Node MCP processes: no unexpected connections.

**No suspicious processes. Nothing terminated.**

---

## 11. Machine-Wide Findings

A full machine-wide scan was **not** performed. Per the audit framework, it is only justified when repository evidence indicates compromise — repository evidence is clean, so the appropriate scope is the targeted read-only check above (processes, startup, Run/RunOnce, scheduled tasks).

Observations surfaced (all benign, none EduVision-related, noneacted upon):
- `python`/`py` on PATH hang (Windows Store app-execution aliases); real CPython is 3.11.9 off-PATH; project wants 3.13. **Dev-environment hygiene item, not malware.**
- Preinstalled **Lavasoft "Web Companion"** autostart (PUA-flagged family) — noted for awareness; outside EduVision scope, no action taken.
- Stale `Docker Desktop` Run entry (binary absent).

---

## 12. Malware Findings

**0** files classified MALICIOUS_CONFIRMED. **Nothing quarantined.** No payload was executed at any point.

---

## 13. Suspicious Findings

**0** files classified SUSPICIOUS. **0** UNKNOWN. The quarantine policy was not triggered.

---

## 14. Safe Findings

- All 576 `.py` source modules, 16 HTML pages, 6 `.js`, 3 `.ps1`, manifests, templates, CI/CD, Docker files: `SAFE`.
- All runtime content (`uploads/` 1,981 media files, `storage-data/` 844 content files): `LIKELY_SAFE` (app-generated/imported educational content; verified by extension/name and absence of executable magic — large media not individually hashed due to OneDrive hydration timeouts).
- Doc tree (`backend/docs`, `docs/`, `EduVision_AI_Frontend` prototypes): `SAFE` engineering documentation.

---

## 15. Files Deleted

**None during this verification pass.** (Previous pass removed only regenerable caches `/872+ `.pyc`/`__pycache__`, `.mypy_cache`, `.pytest_cache`, `.ruff_cache`, `.egg-info`, 4 runtime `.log`, empty root `test.db` — all inside the repo, gitignored, and verified as not affecting tracked content.)

---

## 16. Files NOT Deleted and Why

| Path | Reason |
|---|---|
| `backend/.env` | Active credentials; gitignored; must not be deleted/printed. |
| `backend/test.db` | Runtime SQLite test DB (2 MB) in use by the test suite. |
| `backend/uploads/**` (1,981), `backend/storage-data/**` (844) | User/imported content — not disposable, not malicious. |
| `C:\Users\Admin\AppData\Local\Programs\Python\Python313\` | Outside repo; empty leftover install — dev hygiene, not a security action. |
| Machine autostart entries | None are malicious or EduVision-related; deleting system/AV/legit app entries would be out of scope and could harm the user. |

---

## 17. SHA-256 Evidence

All hashes computed during this pass and the prior baseline (read-only; verified identical contents):

| File | SHA-256 |
|---|---|
| `backend/scripts/_mv_dbg_lesson.ps1` | `B5E9A58F382339D52982B2D6118C407BB2EC78FFF899C409A77BD9C4DB4B4C7B` |
| `backend/scripts/_mv_mlunit3_test.ps1` | `D9CD3AA9A171B7E7D47704F2D97E2708197D7F0737990224BB899174D8B22BE8` |
| `backend/scripts/_mv_wire_check.ps1` | `A63D35ECC52F44FC3F528578934FC4903AABDBDBE9950AA056609CE582BFD304` |
| `backend/scripts/_mv_browser_e2e.js` | `DE4CDC0B4A6182E03A627CDBC3A90C4452149024A835110433850301E18C5D97` |
| `backend/scripts/_mv_diag_click.js` | `A4BDDF3AFFE15107AAC02CC29820517A4247C9967B0C2838973458C7A39FF266` |
| `backend/scripts/_mv_load_probe.js` | `8B5AE681EE862617780C11C77415CFF804FAB29D00B3C8E5C811DC4CEDBDE58E` |
| `backend/scripts/_mv_player_test.js` | `F4DB4B91C825BAC9FEAF0193AFB60A05B0F78EE8518A206E94581ED1F74AB809` |
| `backend/scripts/port_3000_forwarder.py` | `7A9D026ACE63B20962FE5A3C07ADC99F17E082E6F1BDE3CD05B23970B17FC4BA` |
| `backend/scripts/backup_db.py` | `8373F09715D050AC1D7EF7E3892522BC40D203004ED41139D286D87DD9E00799` |
| `backend/scripts/click_test.py` | `7266C5376F0D2A0398CE98404809C1573A943EE6B3258EE8575961FB5F10F158` |
| `backend/frontend/assets/app.js` | `37BB85E9FCAC9678395B83C539DA4A6DB49AC1D3FDE2F2C3D2D8DAAF1746A515` |
| `EduVision_AI_Frontend/eduvision_frontend/assets/app.js` | `37BB85E9FCAC9678395B83C539DA4A6DB49AC1D3FDE2F2C3D2D8DAAF1746A515` (identical) |
| `backend/.env` (not disclosed) | `CCA22CB8056197EA0289EB0BC593DE19BD5FEE062018015386C3C4337A104BB1` |

---

## 18. Evidence Matrix

| Finding | Path | Type | Classification | Evidence | SHA-256 | Action |
|---|---|---|---|---|---|---|
| Dev test harness | `backend/scripts/_mv_dbg_lesson.ps1` | PowerShell | SAFE | localhost API harness only | B5E9A58F… | None |
| Dev test harness | `backend/scripts/_mv_mlunit3_test.ps1` | PowerShell | SAFE | localhost harness | D9CD3AA9… | None |
| Dev test harness | `backend/scripts/_mv_wire_check.ps1` | PowerShell | SAFE | localhost + PPTX check | A63D35EC… | None |
| E2E browser tests | `backend/scripts/_mv_*.js` (4) | JavaScript | SAFE | puppeteer/jsdom vs localhost; `$eval` = DOM reads | listed §17 | None |
| Player helper | `backend/frontend/assets/app.js` (+ prototype copy) | JavaScript | SAFE | 40-line DOM UI helper; no network/eval | 37BB85E9… | None |
| LLM/session tooling | `port_3000_forwarder.py`, `backup_db.py`, `click_test.py`, `verify_*.py`, `generate_sample_*.py` | Python | SAFE | localhost proxies/verification | listed §17 | None |
| Redis Lua eval | `app/middleware/rate_limit.py` | Python | SAFE | rate-limit sliding window script | — | None |
| Prompt-injection defense | `app/ai/prompt_injection.py`, `lesson_safety.py` | Python | SAFE | app security feature (matches "injection") | — | None |
| Obfuscation flags | 16 string matches | mixed | SAFE | all benign (see §4) | — | Review recorded |
| `.env` secrets | `backend/.env` | env | SAFE (untracked) | 2 credentials local-only, gitignored | CCA22CB8… | Rotate on schedule |
| Runtime infra | postgres.exe / redis-server.exe | process | SAFE | dev DB/broker listening locally | — | None |
| Browser/IDE tooling | chrome.exe / chrome-devtools-mcp node | process | SAFE | browsing + IDE DevTools MCP + Google/Cloudflare traffic | — | None |
| Machine autostart | Startup folders, Run/RunOnce, tasks | registry | SAFE | only standard system/AV/legit app entries; no EduVision entries | — | None |
| Stale Docker entry | HKCU Run "Docker Desktop" | registry | POTENTIALLY_UNWANTED | points to non-existent binary; stale | — | None (out of scope) |
| Preinstalled PUP | HKCU Run "Web Companion" (Lavasoft) | registry | POTENTIALLY_UNWANTED | preinstalled PUA-family app; unrelated to EduVision | — | Report only |
| Empty Python313 dir | `AppData\…\Python\Python313\` | system | TEMPORARY_ARTIFACT | empty leftover install | — | Report only |

---

## 19. Project-Integrity Verification (post-pass)

- `git status --short`: 40 `M` + 54 `??` — **identical to baseline**; no tracked file changed or deleted by this audit.
- `git rev-parse HEAD`: unchanged (`d873d99`). No refs moved.
- File counts unchanged: 576 `.py`, 3 `.ps1`, 6 `.js`, 0 `.pyc`; `backend/test.db` intact.
- No source, config, definition, or test file was modified; no commit authored.
- (This pass performed no modifications; the previous cache removal was separately verified — no tracked files, `git fsck` clean, and `git status` before/after identical.)

---

## 20. Remaining Risks

1. **Machine not fully verified:** this report certifies the repository and the EduVision-relevant surfaces enumerated above — not the entire Windows machine. Additional endpoint security tooling (Defender full scan, EDR) is recommended for complete coverage.
2. **OneDrive hydration:** large media (`uploads/*.mp4`, `storage-data/*.pdf/pptx/docx`) could not be individually hashed (hydration timeouts); verified by name/extension and absence of executable/suspicious magic only.
3. **Runtime `.db` files:** `backend/test.db` (in-use test DB) not binary-depth-scanned for injected code paths; treated as app-managed data.
4. **Credentials:** `AI_API_KEY` and `GOOGLE_CLIENT_SECRET` are present in the local `.env` (gitignored/untracked). Rotate them on a schedule; ensure `.env` is never exported or backed up outside this machine.
5. **Dev hygiene:** Python 3.13 required by manifests but 3.11.9 on disk (empty 3.13 dir, PATH shadowed by Store stub) — a functional/environmental gap, not a security defect.
6. **PUP awareness:** preinstalled Lavasoft "Web Companion" autostart is a potentially-unwanted program unrelated to EduVision; consider uninstalling it.

---

## 21. Final Verdict

**B. REPOSITORY CLEAN — MACHINE NOT FULLY VERIFIED**

- The EduVision AI repository contains **no** malicious, suspicious, or unknown files. All scripts, source, manifests, dependencies, network destinations, git history, and project-created persistence are accounted for and benign.
- Running processes and autostart surfaces relevant to the project are benign.
- A complete machine-wide security scan was not performed; it is not indicated by repository evidence but is recommended as extended assurance. Do not extrapolate this verdict to "the laptop is 100% clean."
