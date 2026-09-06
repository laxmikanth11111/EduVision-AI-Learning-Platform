# Post-P14 Capability Matrix — EduVision AI

**Phase:** P14 (Retention & Review Automation) complete — matrix for P15 selection
**HEAD:** `88af40946ee3bbf46571214c1518d7ad9801176e`
**Date:** 2026-09-06

Status legend: **COMPLETE** (implemented + wired + tested + persisted) · **PARTIAL** (implemented but wiring/gap) · **BROKEN** (fails at runtime / does not deliver the promise) · **DEFERRED** (explicitly out of scope, documented) · **MISSING** (absent).

---

## 1. Capability Matrix

| # | Capability | Status | Learner-visible? | Evidence (source/tests) |
|---|---|:---:|---|----|
| 1 | Authentication & user isolation (Argon2id, JWT, httpOnly cookies, 404-equalization) | COMPLETE | yes | auth.py, security.py; two-user isolation suites green |
| 2 | Lesson ingestion (upload → extract → generate → versioned lesson) | COMPLETE | yes | upload/processing/player path; `test_e2e_pipeline` |
| 3 | Topic/lesson sequencing + slide engine | COMPLETE | yes | `topic_outline_service`, player slide engine + keyboard nav |
| 4 | Visual learning (SVG canvas/strategy renderers) | COMPLETE | yes | player visual types; P4 WS3 |
| 5 | Animation / simulation runtime | PARTIAL | partial | player `/animations/plan` + runtime sync; in-memory runtime state; classify + 5 GET routes unwired |
| 6 | Video learning runtime | PARTIAL / RISK | partial | `/videos/create` sync-renders in async handler (4× subprocess.run blocks loop); `/videos/runtime` dead from UI |
| 7 | Interactive player (render, journey panel, adaptive quiz overlay) | COMPLETE | yes | player.html; P6/P10 E2E |
| 8 | Quiz/assessment persistence (PG-correct) | COMPLETE | yes | quiz→attempts→answers→score summaries; P12 PG parity |
| 9 | Adaptive assessment (within-attempt `/next`, deterministic) | COMPLETE | yes | `adaptive_assessment.py`; PG + unit + E2E |
| 10 | Mastery calculation (quiz-owned, stable invariant) | COMPLETE | yes | `educational_memory_service`; P10 NG-3 invariant preserved |
| 11 | Mastery-aware recommendations (Next Best Actions) | COMPLETE | yes | `recommendation_engine`; dashboard deep-links |
| 12 | Spaced review scheduling (1/3/7/14 ladder, lazy seeding) | COMPLETE | yes | `review_scheduler`; due queue bounded |
| 13 | Review outcomes + adaptive interval (P14) | COMPLETE | yes | `retention.py`; `complete(outcome)`; E2E P14 |
| 14 | Retention/recall signal + dashboard surface (P14) | COMPLETE | yes | `GET /me/analytics/retention`; Retention panel; E2E P14 |
| 15 | Remediation (tutor knowledge-check CTA) | COMPLETE | yes | tutor remediate; P8 E2E |
| 16 | Learner dashboard (stats, actions, plan, path, goals, progress) | COMPLETE | yes | dashboard.html; P7/P11 E2E |
| 17 | Learner analytics / trajectory (P13) | COMPLETE | yes | 4 `/me/analytics/*`; 3 panels; E2E P13 |
| 18 | Retention trend over time | DEFERRED | — | P14 history exists; chart extension deferred |
| 19 | **Lesson resume / continuity ("pick up where you left off")** | **BROKEN** | no | signin.html:55 + dashboard.html:332 promise it; player ignores `session.topic_index` and always starts at slide 0; `learning_sessions.current_slide_position` unused |
| 20 | Post-login hub navigation (upload.html → dashboard/tutor) | PARTIAL→BROKEN | no | upload.html has no dashboard/tutor link (dead-end after sign-in) |
| 21 | Study plans / goals / learning paths | COMPLETE | yes | P11, browser-verified |
| 22 | AI tutor (multi-turn RAG, fallback, remediation) | COMPLETE | yes | tutor.html; P8 E2E |
| 23 | Semantic RAG (embedding + cosine + positional fallback) | COMPLETE | yes | `embedding_service` + RAG retrieval; tutor-scoped |
| 24 | RAG fusion (RRF/MMR) | DEFERRED | — | knobs inert (`TUTOR_RETRIEVAL_RRF_K/MMR_LAMBDA`) |
| 25 | Educational memory (concept bands, JSONB, cache) | COMPLETE | yes | migration 0033; cache-backed |
| 26 | Mastery decay (persisted, separate metric) | DEFERRED | — | P14 retention signal = observed recall (separate); decay-as-rewrite avoided |
| 27 | Effectiveness/learning-gain analytics | COMPLETE | yes | baseline/post/retention assessments; exports |
| 28 | Export (jobs/files; CSV/DOCX/PPTX) | COMPLETE | yes | export API; `test_p3_12_export` |
| 29 | Observability (metrics, request IDs, structlog) | COMPLETE | no | `/api/v1/metrics`; `p11_*`…`p14_*` |
| 30 | Browser E2E coverage | COMPLETE (21/10 files) | — | smoke … P14 retention |
| 31 | PostgreSQL parity (behavioral) | COMPLETE | no | 30 PG tests; JSONB round-trip; head guard |
| 32 | Performance/scalability bounds | PARTIAL | no | bounded learner reads; sync video render (HIGH), `effectiveness` `.all()` (MED), stale rate-limit config (MED) |
| 33 | Production hardening (rate-limit routes, uploads auth, CSRF, injection guard) | PARTIAL | no | carried MED/HIGH items (§9 of audit) |
| 34 | Learning workspace (bookmarks/notes/save-surface) | DEFERRED | — | never implemented; new capability, no journey break |
| 35 | Retention nudges / beat task | DEFERRED | — | requires functional Redis/Celery test first |

---

## 2. Open-High X / Y Mapping (product loop)

| Loop stage | Learn | Understand | Visualize | Practice | Assess (adaptive) | Measure | Recommend | Review | Recall | Return |
|---|---|---|---|---|---|---|---|---|---|---|
| Status | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ (P13) | ✓ | ✓ (P10/11) | ✓ (P14) | **✗ BROKEN (resume)** + hub dead-end |

The only remaining **BROKEN** stage is **Return** — the learner cannot resume previous work and the post-login hub is a dead-end. Everything upstream is complete and learner-visible.

---

## 3. Evidence Snapshot (this audit)

- SQLite 1295 · PG 30 · E2E 21 · Ruff clean · mypy 83/24 · single head `0033` (verified from live runs).
- P14 13/13 contract items verified from source (§4 of `POST_P14_PRODUCT_ARCHITECTURE_AUDIT.md`).
- Resume gap: `player.html:339-362` (ignores session position) vs `learning_session_service.py:94-192` (server persists + returns `topic_index`) vs migration `0009:57-63` (idle `current_slide_position`).
- Hub dead-end: `upload.html:103-106` (nav has no dashboard link); sign-in redirects to upload.html (`signin.html:131`).
- No new security finding from P14 (audit §9). Carried HIGHs documented (OAuth link, refresh-JTI). New latent MED: analytics snapshot models absent from migrations (zero callers today).

---

## 4. Final Ranking → P15

Per the weighted candidate scoring (§16 of the audit): **A — Persistent Lesson Resume & Learner Continuity (459)** leads B (387) / F (321) / E (310) / I (302) / G (292) / H (274) / D (253) / C (250).

P15 = **Resume & continuity**: the player restores the learner's saved slide from any entry point, dashboard lesson-progress emits server-built resume deep-links, and the navigation loop (post-login hub → dashboard; player completion → dashboard; signs out) is closed. Deterministic, zero AI, zero migration, fully browser-verifiable, User A/B isolatable.