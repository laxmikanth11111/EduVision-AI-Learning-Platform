# POST-P5 Product + Architecture Decision Audit

**Status:** DECISION AUDIT — COMPLETE (documentation only; no application code changed).
**Repository state at start:** clean; HEAD = `cba306b` on `feature/individual-user-foundation`. P5 complete (browser-verified).
**Audit date:** 2026-09-03

> Every claim below is evidence-sourced to repository files/documents.
> Where evidence is insufficient the status is marked **NOT VERIFIED** explicitly.

---

## 1. Executive Summary

EduVision AI has completed P0–P5 (security foundation, data/runtime hardening, production hardening, production capability, and the interactive learner journey). The backend is production-hardened and the content-generation pipeline is strong. P5 added persistent per-user lesson progress, assessment checkpoint status, and mastery/next-action surfacing to the active vanilla SPA player.

However, the **single largest remaining product gap** is the **absence of a quiz-taking UI in the active frontend**. The backend has a complete quiz subsystem (generate, attempt, answer, submit, score, evaluate) with full ownership isolation, but the learner cannot take a quiz through the browser. The learner journey panel shows "Checkpoint pending" but provides no pathway to start, answer, or submit the quiz. This means:

- Mastery never updates from quiz results through the browser
- The recommendation engine produces next actions but the learner cannot act on them
- The learning loop (Learn → Understand → Visualize → Practice → Assess → Measure → Next Action → Learn Again) is **broken at the Assess step**

**Recommendation:** P6 should be **Interactive Assessment + Complete Learning Loop** — building the quiz-taking UI in the vanilla SPA player, wiring it to the existing quiz/mastery/recommendation backend services, and verifying the full closed loop in the browser.

---

## 2. Verified Repository State

| Check | Expected | Actual | Status |
|-------|----------|--------|--------|
| HEAD | `cba306b` | `cba306b` | VERIFIED |
| Branch | `feature/individual-user-foundation` | `feature/individual-user-foundation` | VERIFIED |
| Working tree | clean | clean | VERIFIED |
| `git diff --check` | no issues | no issues | VERIFIED |
| Alembic head | single head | `0028_ws10_idempotency_key_index` | VERIFIED |
| Fast tests | 1062 passed | 1062 passed | VERIFIED |
| PostgreSQL tests | 15 passed | 15 passed | VERIFIED |
| Ruff | clean | clean | VERIFIED |
| Mypy | 83 errors, zero new | 83 errors, zero new | VERIFIED |
| Secret scan | clean | clean | VERIFIED |

---

## 3. P0–P5 Inheritance Matrix

| Phase | Focus | Status | Key Deliverables | Inherited by P6 |
|-------|-------|--------|------------------|-----------------|
| P0 | Deep architecture audit | COMPLETE | Audit, 14-phase roadmap, risk register | Architecture baseline, tech stack truth |
| P1 | Security foundation | COMPLETE | Quiz IDOR fix, upload validation, fail-fast config, CI | Ownership-404 pattern, auth infrastructure |
| P2 | Data/runtime foundation | COMPLETE | PG verification, commit-before-dispatch, bounded state | Database reliability, worker patterns |
| P3 | Production hardening | COMPLETE | N+1 fix, bounded memory, observability, uniform ownership | Performance patterns, security hardening |
| P4 (WS1–WS6) | Production capability | COMPLETE | Deployment fixes, export, vector RAG, bounded caches, browser E2E | RAG retrieval, export, caching, E2E infrastructure |
| P5 | Interactive learner journey | COMPLETE | Persistent progress, checkpoint status, mastery surfacing | Learning sessions, mastery display, SPA player patterns |

---

## 4. Current Product Capability Matrix

| Capability | Browser Verified | API Verified | Backend Implemented | Partially Implemented | Planned Only | Not Implemented |
|------------|:---:|:---:|:---:|:---:|:---:|:---:|
| User registration (email/password) | ✅ | | | | | |
| Google OAuth sign-in | ✅ | | | | | |
| File upload (PDF/DOCX/PPTX/TXT) | ✅ | | | | | |
| Manual deck creation | ✅ | | | | | |
| AI presentation generation | ✅ | | | | | |
| AI lesson generation | ✅ | | | | | |
| Player (concept slides) | ✅ | | | | | |
| Player (visual slides) | ✅ | | | | | |
| Canvas diagram rendering (SVG) | ✅ | | | | | |
| Animation rendering (Motion Engine v2) | ✅ | | | | | |
| Video playback | ✅ | | | | | |
| Simulation step-through | ✅ | | | | | |
| Present mode (fullscreen) | ✅ | | | | | |
| Persistent lesson progress | ✅ | | | | | |
| Checkpoint status display | ✅ | | | | | |
| Mastery summary display | ✅ | | | | | |
| Next-action text display | ✅ | | | | | |
| Quiz generation (AI) | | ✅ | | | | |
| Quiz CRUD | | ✅ | | | | |
| Quiz attempt start/resume | | ✅ | | | | |
| Quiz answer submission | | ✅ | | | | |
| Quiz submit + scoring | | ✅ | | | | |
| Quiz attempt listing | | ✅ | | | | |
| Visual canvas CRUD | | ✅ | | | | |
| Simulation definitions + sessions | | ✅ | | | | |
| Animation planning + runtime | | ✅ | | | | |
| Video creation | | ✅ | | | | |
| AI tutor (assistant) sessions | | ✅ | | | | |
| Effectiveness assessments | | ✅ | | | | |
| Exports (PDF/DOCX/PPTX/MD/HTML/CSV) | | ✅ | | | | |
| RAG indexing + semantic retrieval | | ✅ | | | | |
| Educational memory | | ✅ | | | | |
| Recommendation engine | | ✅ | | | | |
| Adaptive assessment engine | | ✅ | | | | |
| **Quiz-taking UI in SPA** | ❌ | | | | | **CRITICAL GAP** |
| Learner progress history/dashboard | ❌ | | | | | **GAP** |
| Concept mastery visualization | ❌ | | | | | **GAP** |
| Adaptive recommendation actions (buttons) | ❌ | | | | | **GAP** |
| Analytics CSV export | | | | ❌ | | |
| Study-data deletion endpoint | | | | ❌ | | |
| Statistical analysis | | | | | ❌ | |
| 2D slide-element editor | | | | | ❌ | |
| Framework frontend migration | | | | | ❌ | |
| ML/DL learner intelligence | | | | | ❌ | |
| Collaboration/teacher roles | | | | | ❌ | |
| Mobile applications | | | | | ❌ | |
| Microservices/Kubernetes | | | | | ❌ | |
| Animation/simulation HA persistence | | | | | ❌ | |

---

## 5. Active Frontend Architecture

### Active Frontend
**Location:** `backend/frontend/`
**Architecture:** Vanilla JS multi-page SPA (no framework, no build, no package.json)

| File | Purpose | Auth Required |
|------|---------|:---:|
| `index.html` | Landing page | No |
| `signup.html` | Registration (email/password + Google OAuth) | No |
| `signin.html` | Login (email/password + Google OAuth) | No |
| `upload.html` | Dashboard — create decks, list recent decks | Yes |
| `processing.html` | Poll extraction status, trigger lesson generation | Yes |
| `player.html` | Full presentation player + learner journey panel | Yes |
| `assets/app.js` | Shared utilities (IntersectionObserver, tab handlers) | No |
| `assets/style.css` | Global styles | No |

### Inactive Frontend
**Location:** `EduVision_AI_Frontend/eduvision_frontend/` — older copy, NOT active.

### Auth Architecture
- JWT tokens in `localStorage` (`access_token`, `refresh_token`)
- `authFetch()` wrapper with automatic 401 → refresh → retry → redirect
- Google OAuth via `/api/v1/auth/google` redirect

### Player Capabilities (verified in `player.html`)
- Concept slides: title + description per topic
- Visual slides: 5 render modes (auto/image/animation/video/simulation)
- Sidebar thumbnails with slide navigation
- Learner Journey panel: progress bar, checkpoint chip, mastery next-action text
- Present mode: fullscreen with keyboard navigation
- Session tracking: syncs current topic to server via `/player/set-topic`

### Missing Frontend Capabilities (for P6 scope)
- **No quiz-taking UI** — the learner journey panel shows "Checkpoint pending" but has no button to start or take the quiz
- **No question rendering** — no multiple-choice, true/false, or any question type UI
- **No answer selection** — no interactive answer picking
- **No submit + results** — no quiz submission or score display
- **No action buttons** — next-action is text-only, not clickable

### Assessment
The current vanilla SPA architecture is **sufficient** for the next product milestone (P6). The player already handles complex visual rendering (canvas, animation, video, simulation), auth, session management, and the learner journey panel. Adding a quiz-taking overlay or panel within the existing `player.html` structure follows the established patterns and requires no framework migration.

---

## 6. P5 Learner Loop Analysis

### What P5 Delivered

P5 implemented 5 commits (C1–C5):

1. **C1 — Persistent per-user sessions:** `LearningSessionService` with DB-backed progress (user-scoped), replacing in-memory state for authenticated users
2. **C2 — Assessment checkpoint:** `GET /lessons/{id}/player/checkpoint` reports whether a quiz exists and past attempt status
3. **C3 — Mastery + next action:** `GET /lessons/{id}/player/mastery` reusing `educational_memory_service` + `recommendation_engine`
4. **C4 — Vanilla SPA integration:** Learner journey panel in `player.html` with progress bar, assessment chip, next-action display
5. **C5 — Tests:** Unit tests, PostgreSQL integration tests, skip-gated E2E tests

### What P5 Verified (Browser)
All 6 E2E tests passed across 3 repeatable runs. The learner journey panel renders with:
- Progress percentage
- Assessment checkpoint status (exists/completed/pending)
- Mastery summary (average, weak/developing/mastered counts)
- Next action (title + reason text)

### P5 Known Limitations (documented in P5_BROWSER_ACCEPTANCE_VERIFICATION.md)
> "No interactive quiz submission UI in SPA (assessment checkpoint display only)"
> "No quiz submission through browser UI"

---

## 7. Remaining Product Gaps

### Critical Gap: Quiz-Taking UI (P6 scope)
The learner can see "Checkpoint pending" but **cannot take the quiz**. The backend quiz subsystem is complete (generate → attempt → answer → submit → score → evaluate → mastery update) but has **zero frontend integration** for interactive quiz-taking.

### Secondary Gaps (future phases)
1. **Learner progress history** — only shows current lesson; no cross-lesson dashboard
2. **Concept mastery visualization** — text only; no charts or trend lines
3. **Actionable next-action buttons** — text display only; no "Take quiz" or "Review concept" buttons
4. **Analytics CSV export** — raises `NotImplementedError` at `analytics_helpers.py`
5. **Study-data deletion** — no user deletion endpoint

---

## 8. Architecture Health

| Area | Current State | Evidence | Risk | User Impact | Priority |
|------|---------------|----------|------|-------------|----------|
| Backend | Production-hardened, 18 routers, 61 models | P0–P4 reports, verified | Low | None | P3 |
| Database | PostgreSQL (prod), SQLite (dev/test), Alembic 0028 | Verified | Low | None | P3 |
| Authentication | JWT + refresh + Google OAuth + Redis revoke | P1 verified | Low | None | P3 |
| Authorization | Ownership-404 pattern, user-scoped | P1–P5 verified | Low | None | P3 |
| Storage | Local + S3 adapter, export engine | P4 WS2 verified | Low | None | P3 |
| Workers | Celery + DLQ + bounded retry + idempotency | P2–P3 verified | Low | None | P3 |
| Redis | Session revoke, bounded cache fallback | P1 verified | Low | None | P3 |
| Caching | 6 bounded TTL/LRU caches (WS4) | P4 WS4 verified | Low | None | P3 |
| RAG | Vector semantic retrieval + cosine ranking (WS3) | P4 WS3 verified | Low | None | P3 |
| AI providers | Gemini/OpenAI/local with retry/rate-limit/cost | P0 verified | Low | None | P3 |
| Embeddings | Full lifecycle pipeline (batch/refresh/cleanup/integrity) | P2 verified | Low | None | P3 |
| Observability | structlog + request IDs + Prometheus | P3 verified | Low | None | P3 |
| API design | RESTful, consistent patterns, APIResponse envelope | Verified | Low | None | P3 |
| Frontend | Vanilla JS SPA, 6 pages, no build system | Verified | Low | None | P3 |
| Browser E2E | Playwright + system Chrome, 6 tests | P4 WS5 + P5 verified | Low | None | P3 |
| Docker | Multi-stage build, non-root, prod import verified | P4 WS6 verified | Low | None | P3 |
| CI | GitHub Actions (lint/unit/integration/migration/PG/secret/Docker) | P1 verified | Low | None | P3 |
| Configuration | `.env` + `.env.example`, fail-fast startup | P1 verified | Low | None | P3 |
| Testing | 1062 fast, 15 PG, 6 E2E, Ruff clean, 83 mypy (Δ=0) | Verified | Low | None | P3 |
| Migrations | 28 migrations, single head, verified | Verified | Low | None | P3 |
| Security | P1 hardened, IDOR fixed, upload validated | P1 verified | Low | None | P3 |
| Performance | N+1 fixed, bounded memory, bounded caches | P3 verified | Low | None | P3 |

**Conclusion:** Architecture health is strong across all areas. No P0/P1/P2 risks identified. The system is ready for feature development.

---

## 9. Deferred Work Review

| Phase | Deferred Item | Why Deferred | Still Relevant? | Current Risk | User Value | Impl. Cost | Recommended Action |
|-------|---------------|--------------|:---:|:---:|:---:|:---:|---|
| P0 Phase 2 | Framework frontend migration | No product need | No | None | Low | High | Keep Deferred |
| P0 Phase 3 | 2D slide-element editor | Highest complexity | Yes (later) | None | High | Very High | Build Later |
| P0 Phase 7 | Animation/simulation HA persistence | Infra, no HA need | No | Low | Low | Medium | Keep Deferred |
| P0 Phase 8 | Simulation engine (DB definitions) | 5 hardcoded defs sufficient | No | Low | Low | Medium | Keep Deferred |
| P0 Phase 9 | Knowledge graph breadth | Partial (visual KB exists) | Yes (later) | None | Medium | High | Build Later |
| P0 Phase 10 | ML/DL learner intelligence | Eval-gated; must beat heuristics | Yes (later) | None | Medium | Very High | Keep Deferred |
| P0 Phase 11 | Adaptive learning | Heuristic exists | Yes (later) | None | Medium | Medium | Build Later |
| P0 Phase 13 | Multimodal voice/video | Video+TTS exist | No | Low | Low | High | Keep Deferred |
| P2 | `record_retry` / `schedule_retry` (no callers) | Dead code | No | Low | None | Low | Close as Obsolete |
| P2 | Historical migration fragility | Not reproducible | No | Low | None | None | Close as Obsolete |
| P3 | RAG soft-delete consistency | Low impact | No | Low | None | Low | Keep Deferred |
| P3 | Analytics CSV export | Hardcoded sample data | No | Low | Low | Low | Build Later |
| P3 | Study-data deletion | No IRB requirement | No | Low | Low | Low | Keep Deferred |
| P3 | Statistical analysis | By design | No | Low | Medium | Medium | Keep Deferred |
| P4 | `P4_IMPLEMENTATION_AUDIT.md` | Referenced but does not exist | No | None | None | None | Close as Obsolete |

---

## 10. Candidate Comparison

### Candidate A — Interactive Assessment + Complete Learning Loop
- **Scope:** Quiz-taking UI in SPA, answer submission, score display, mastery update, next-action actionability, full loop browser E2E
- **Backend readiness:** HIGH — QuizAttemptService, QuizGenerationService, EducationalMemoryService, RecommendationEngine all complete and tested
- **Frontend readiness:** MEDIUM — player.html has panel patterns, auth, session management; needs quiz UI addition
- **Database impact:** NONE — quiz/mastery/learning tables exist
- **AI impact:** Reuse existing quiz generation; no new AI calls

### Candidate B — Interactive 2D Visual Learning Workspace
- **Scope:** Canvas interaction (drag, connect, label, manipulate), visual state persistence
- **Backend readiness:** LOW — no interactive canvas backend
- **Frontend readiness:** LOW — SVG rendering exists but no interaction layer
- **Database impact:** HIGH — new schema for interactive visual state
- **AI impact:** None

### Candidate C — Animation/Simulation Engine Improvement
- **Scope:** More simulation definitions, persistence, safety sandbox
- **Backend readiness:** MEDIUM — engine exists, 5 hardcoded definitions
- **Frontend readiness:** MEDIUM — step-through UI exists
- **Database impact:** MEDIUM — new simulation persistence tables
- **AI impact:** None

### Candidate D — RAG/AI Teacher Improvement
- **Scope:** Better retrieval, grounding, citations, hallucination controls
- **Backend readiness:** MEDIUM — WS3 delivered semantic retrieval
- **Frontend readiness:** LOW — no tutor chat UI changes needed
- **Database impact:** LOW — embedding infrastructure exists
- **AI impact:** HIGH — core of the candidate

### Candidate E — Learner Analytics/Mastery Intelligence
- **Scope:** Historical dashboards, trend visualization, learning velocity
- **Backend readiness:** LOW — blocked by quiz gap (no data flowing)
- **Frontend readiness:** LOW — no dashboard pages exist
- **Database impact:** LOW — tables exist
- **AI impact:** None (analytics, not ML)

### Candidate F — Frontend Architecture Migration
- **Scope:** Migrate vanilla SPA to React/Vue/Svelte/etc.
- **Backend readiness:** N/A
- **Frontend readiness:** LOW — rewrite of working code
- **Database impact:** None
- **AI impact:** None

### Candidate G — Production Scale / HA
- **Scope:** Multi-instance, distributed state, Redis caching, backup, DR
- **Backend readiness:** LOW — single-instance only
- **Frontend readiness:** N/A
- **Database impact:** MEDIUM — connection pooling, replicas
- **AI impact:** None

---

## 11. Weighted Scoring

Scale 1–10 (10 = best). Evidence-based, not manipulated.

| Criterion (Weight) | A: Quiz+Loop | B: 2D Workspace | C: Anim/Sim | D: RAG/AI | E: Analytics | F: FE Migration | G: Scale/HA |
|---------------------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Learner Value (20%) | 10 | 6 | 4 | 5 | 6 | 2 | 1 |
| Product Differentiation (15%) | 7 | 9 | 5 | 6 | 7 | 3 | 2 |
| Current Readiness (15%) | 9 | 3 | 7 | 7 | 4 | 5 | 6 |
| Technical Risk (10%) [lower=riskier→lower score] | 9 | 3 | 6 | 7 | 7 | 3 | 6 |
| Implementation Cost (10%) [lower=cheaper→better] | 8 | 2 | 5 | 5 | 5 | 2 | 3 |
| Architecture Fit (10%) | 9 | 5 | 8 | 8 | 7 | 4 | 7 |
| Dependency Count (5%) [fewer=better] | 9 | 4 | 7 | 6 | 6 | 5 | 5 |
| Browser UX Impact (10%) | 10 | 7 | 5 | 3 | 6 | 5 | 1 |
| Demo/Portfolio Value (5%) | 9 | 8 | 6 | 5 | 7 | 4 | 2 |
| Long-Term Strategic Value (5%) | 8 | 8 | 6 | 7 | 8 | 4 | 6 |
| **Weighted Total** | **9.30** | **5.70** | **5.95** | **6.15** | **6.40** | **3.65** | **3.75** |

**Scoring explanation:**
- **A (9.30)** dominates because: highest learner value (the learner literally cannot take a quiz), highest readiness (backend 95% complete), lowest risk (frontend-only work reusing existing patterns), highest browser UX impact (closes the broken loop), and direct alignment with the core product promise.
- **B (5.70)** scores high on differentiation but very low on readiness, architecture fit, and implementation cost.
- **C–E (5.95–6.40)** are viable future phases but have lower learner value or are blocked by the quiz gap.
- **F–G (3.65–3.75)** are rejected: F has no product need, G has no scale need.

---

## 12. Recommended Next Phase

### P6 — Interactive Assessment + Complete Learning Loop

**Why now:** The learner loop is broken at the assessment step. The learner can see "Checkpoint pending" but cannot take the quiz. The backend quiz subsystem is complete; only the frontend UI is missing. This is the highest-value, lowest-risk, highest-readiness work available.

**Why not the others:**
- B (2D Workspace): High complexity, low readiness, blocked by the more fundamental quiz gap
- C (Animation/Sim): Already works; low incremental value
- D (RAG/AI): WS3 already improved retrieval; not the biggest gap
- E (Analytics): Blocked by quiz gap (no data flowing from quiz results)
- F (FE Migration): No product need; violates "do not migrate without evidence"
- G (Scale): No scale need; violates "do not build enterprise infra prematurely"

**What dependency does it unlock:** Completing the learning loop enables analytics (Candidate E), adaptive learning improvements, and creates the data flow for future intelligence features.

**What learner problem does it solve:** "I can see my checkpoint but I can't take it. I can't practice what I've learned. My mastery never changes. I don't know what to do next because there's no action I can take."

**What existing code can be reused:**
- `QuizAttemptService` (full quiz lifecycle: start → answer → submit → score → evaluate)
- `QuizGenerationService` (AI quiz generation from lesson content)
- `EducationalMemoryService` (mastery tracking with DB persistence)
- `RecommendationEngine` (deterministic mastery-driven next actions)
- `LearningSessionService` (persistent per-user progress)
- `lesson_player_service.py` (checkpoint + mastery endpoints already wired)
- `player.html` patterns (sidebar panel, auth, session management, visual area)
- `authFetch()` pattern (JWT handling with automatic refresh)

**What should explicitly NOT be built:**
- No new database tables (quiz/mastery/learning tables already exist)
- No new AI providers (reuse existing quiz generation path)
- No new backend services (reuse existing services)
- No frontend framework migration
- No 2D editor
- No ML/DL
- No vector database additions
- No microservices
- No mobile applications

---

## 13. Rejected Alternatives

| Candidate | Rejection Reason |
|-----------|-----------------|
| B (2D Workspace) | High complexity, low readiness, blocked by quiz gap. Appropriately scoped as a later phase. |
| C (Animation/Sim) | Already functional (Motion Engine v2 + simulation step-through). Low incremental value. |
| D (RAG/AI) | WS3 already delivered semantic retrieval. Not the biggest remaining gap. |
| E (Analytics) | Blocked by quiz gap — no data flows from quiz results to analytics. Premature. |
| F (FE Migration) | No product need. Current vanilla SPA is sufficient. Violates "do not migrate without evidence." |
| G (Scale/HA) | No scale need. Single-instance is adequate. Violates "do not build enterprise infra prematurely." |

---

## 14. Proposed Scope

### MUST HAVE
1. Quiz-taking UI in the vanilla SPA player (question display, answer selection, submit)
2. Multiple question type rendering (at minimum: multiple-choice, true/false)
3. Quiz submission with score/results display
4. Mastery update after quiz submission (backend wiring verification)
5. Next-action refresh after mastery change
6. Assessment checkpoint → start quiz → answer → submit → see results flow in browser
7. Ownership-404 on all quiz endpoints (already exists; verify in browser context)
8. Two-user security regression tests for quiz-taking
9. Browser E2E of the full loop: open lesson → reach checkpoint → take quiz → submit → see score → mastery updates → next action changes

### SHOULD HAVE
1. "Take Quiz" / "Retake Quiz" action buttons in the learner journey panel
2. Quiz attempt history display (previous scores)
3. Post-quiz mastery summary update (visual feedback)
4. Cross-session quiz resume (already backend-supported; verify in browser)

### NICE TO HAVE
1. Question-by-question navigation (prev/next within quiz)
2. Time limit display (if quiz has time_limit_minutes)
3. Immediate feedback after each answer (if quiz.show_feedback_after is set)
4. Concept-level mastery breakdown after quiz

---

## 15. Explicit Non-Scope

- 2D slide-element editor / new 2D schema
- Framework frontend migration (React/Vue/Svelte/Next.js)
- ML/DL learner intelligence
- Knowledge graph breadth
- Collaboration/teacher roles
- Mobile applications
- Microservices/Kubernetes
- Animation/simulation video runtime HA persistence
- New database tables
- New AI providers
- New backend services
- Vector database additions

---

## 16. Architecture Plan

### Backend Changes
**NONE** — all required backend services already exist and are tested:
- `QuizAttemptService`: start_attempt, submit_answer, submit_quiz, get_attempt, list_attempts
- `QuizGenerationService`: generate_quiz (AI-powered)
- `EducationalMemoryService`: update_concept_mastery, load_from_db, save_to_db
- `RecommendationEngine`: generate_recommendations (deterministic)
- `LessonPlayerService`: get_checkpoint, get_mastery_and_next_action

### Frontend Changes
Add quiz-taking UI to `player.html`:
1. **Quiz overlay/panel** — triggered by "Take Quiz" button in the learner journey panel
2. **Question renderer** — displays question stem, options (multiple-choice, true/false)
3. **Answer selector** — radio buttons for MC, toggle for T/F
4. **Navigation** — prev/next within quiz, question overview
5. **Submit button** — calls `POST /quizzes/{id}/attempts/{attempt_id}/submit`
6. **Results display** — score, pass/fail, per-question feedback
7. **Action buttons** — "Continue Learning", "Retake Quiz", "Review Mastery"
8. **Journey panel update** — refresh checkpoint + mastery after quiz submission

### Pattern: The quiz UI follows the existing visual-slide pattern in player.html:
- Overlay or inline panel within the slide viewport
- Fetch-based API calls with authFetch()
- DOM manipulation (no framework)
- Closeable (return to lesson)

---

## 17. API Plan

**No new APIs required.** All endpoints already exist:

| Method | Path | Auth | Purpose |
|--------|------|:---:|---------|
| POST | `/api/v1/quizzes/generate` | JWT | Generate quiz from lesson (AI) |
| GET | `/api/v1/quizzes/{quiz_id}` | JWT | Get quiz metadata |
| POST | `/api/v1/quizzes/{quiz_id}/attempts` | JWT | Start/resume attempt |
| GET | `/api/v1/quizzes/{quiz_id}/attempts` | JWT | List user attempts |
| GET | `/api/v1/quizzes/{quiz_id}/attempts/{attempt_id}` | JWT | Get attempt detail |
| POST | `/api/v1/quizzes/{quiz_id}/attempts/{attempt_id}/answers/{question_id}` | JWT | Submit single answer |
| POST | `/api/v1/quizzes/{quiz_id}/attempts/{attempt_id}/submit` | JWT | Submit quiz + score |

Existing player endpoints (already used by P5):
| GET | `/api/v1/lessons/{id}/player/checkpoint` | JWT | Assessment checkpoint status |
| GET | `/api/v1/lessons/{id}/player/mastery` | JWT | Mastery + next action |

---

## 18. Database Decision

**NO DATABASE MIGRATION REQUIRED.**

All necessary tables already exist:
- `quizzes` (migration 0005)
- `quiz_attempts` (migration 0005)
- `quiz_versions` (migration 0005)
- `quiz_contents` / questions (migration 0005)
- `user_answers` (migration 0005)
- `answer_keys` (migration 0005)
- `question_attempts` (migration 0005)
- `question_explanations` (migration 0005)
- `score_summaries` (migration 0005)
- `learning_sessions` (migration 0009)
- `learning_activities` (migration 0010)
- `educational_memories` (migration 0007)
- `concepts` (migration 0007)

Current Alembic head: `0028_ws10_idempotency_key_index` — will remain unchanged.

---

## 19. Security Plan

### Threats
1. **IDOR on quiz attempts** — user A accessing user B's quiz attempt → ALREADY MITIGATED (ownership-404 in `QuizAttemptService.assert_quiz_ownership`)
2. **Cross-user quiz answer leakage** — ALREADY MITIGATED (all queries scoped by user_id)
3. **Unauthorized quiz generation** — ALREADY MITIGATED (requires JWT + presentation ownership)
4. **Quiz submission replay** — ALREADY MITIGATED (attempt status check: only "in_progress" can be submitted)

### Verification
- Existing: `test_two_user_isolation.py` pattern
- Required: E2E test that a second user cannot access another user's quiz attempt
- Required: E2E test that quiz submission updates the correct user's mastery

### Security Acceptance Tests
1. Unauthenticated access to quiz endpoints → 401
2. User A's quiz attempt not accessible by User B → 404
3. Quiz submission only works for "in_progress" attempts → 409 for completed
4. Mastery update scoped to authenticated user only
5. Quiz generation requires lesson ownership

---

## 20. AI/RAG Decision

**AI REQUIRED — but minimal.**

Quiz generation uses the existing AI provider path (`QuizGenerationService` → `AIContentService`). This is already implemented and tested.

**Deterministic behavior where possible:**
- Quiz attempt start/resume: fully deterministic
- Answer submission: fully deterministic
- Scoring/evaluation: fully deterministic (answer key comparison)
- Mastery update: fully deterministic (educational_memory_service)
- Recommendation generation: fully deterministic (recommendation_engine)

**Fallback behavior:**
- AI quiz generation failure → existing error handling (retry with backoff)
- Provider failure → existing provider fallback chain (Gemini → OpenAI → local)

**Cost controls:** existing per-provider rate limiting and cost tracking.

**No new AI calls needed for P6.** The frontend quiz-taking UI calls existing deterministic endpoints. AI is only involved in quiz generation (which is a pre-existing backend operation).

---

## 21. Testing Strategy

| Layer | Scope | Gate |
|-------|-------|------|
| Unit | Quiz UI rendering functions, question type mapping, answer state management | Every commit |
| Integration | API route → service → persistence for quiz start/answer/submit flow | Every commit |
| PostgreSQL | Quiz attempt lifecycle, mastery update, FK constraints | C5 gate |
| Security | Two-user quiz isolation, unauthorized quiz access | C4 gate |
| Browser E2E | Full loop: open lesson → checkpoint → take quiz → submit → score → mastery → next action | C5 gate |
| Regression | Fast (1062+), PostgreSQL (15+), Ruff clean, mypy Δ≤0 | Every commit |

### Required Principle
Every important user-facing capability must have browser-level acceptance evidence when the active frontend supports that capability. The quiz-taking UI is the core user-facing capability of P6; it MUST have browser E2E verification.

---

## 22. Browser Acceptance Contract

The REAL browser journey that must pass before P6 is complete:

```
Sign in (email/password)
  ↓
Open lesson (player.html?lesson=...&deck=...)
  ↓
Verify player loads with topics
  ↓
Verify learner journey panel shows progress + checkpoint status
  ↓
Click "Take Quiz" button in the learner journey panel
  ↓
Quiz overlay/panel opens with questions
  ↓
See question stem + options (multiple choice)
  ↓
Select an answer
  ↓
Navigate to next question
  ↓
Select answers for all questions
  ↓
Click "Submit Quiz"
  ↓
See score result (percent, pass/fail)
  ↓
Close quiz results
  ↓
Learner journey panel refreshes with updated mastery
  ↓
Next action text changes (if mastery changed)
  ↓
Leave lesson (navigate away)
  ↓
Reopen same lesson
  ↓
Progress remains (persistent session)
  ↓
Quiz attempt status shows "completed" with latest score
```

Only steps that P6 actually owns are included. The player concept/visual rendering, canvas/animation/video/simulation, and present mode are P5 scope and not re-tested here.

---

## 23. Checkpoint Plan

### C0 — Baseline
- **Objective:** Confirm P5 baseline is clean; define final P6 scope
- **Files:** None changed
- **Tests:** Fast regression, PG regression, Ruff, mypy
- **Acceptance:** All P5 gates pass; working tree clean
- **Security:** N/A
- **Rollback:** N/A (no changes)

### C1 — Backend Quiz Wiring Verification
- **Objective:** Verify existing quiz endpoints work end-to-end from the API; generate a quiz for a lesson, start attempt, submit answers, verify mastery update
- **Files affected:** None (verification only, or minimal test additions)
- **Tests:** Integration test: generate quiz → start attempt → submit answers → submit quiz → verify mastery updated
- **Acceptance:** Quiz lifecycle works via API; mastery changes after submission
- **Security:** Ownership-404 verified for all quiz endpoints
- **Rollback:** Remove any added tests

### C2 — Quiz-Taking UI in Player
- **Objective:** Build quiz-taking interface in player.html: quiz overlay, question rendering, answer selection, submit button, results display
- **Files affected:** `backend/frontend/player.html`
- **Tests:** Manual browser verification of quiz flow
- **Acceptance:** Learner can open quiz, answer questions, submit, see results in browser
- **Security:** Quiz endpoints called via authFetch() with JWT
- **Rollback:** Revert player.html to P5 state

### C3 — Learner Journey Panel Enhancement
- **Objective:** Add "Take Quiz" / "Retake Quiz" buttons to the learner journey panel; refresh panel after quiz submission; show action buttons for next-action
- **Files affected:** `backend/frontend/player.html`
- **Tests:** Manual browser verification of panel interactions
- **Acceptance:** Panel buttons work; panel refreshes after quiz; mastery updates visible
- **Security:** N/A (frontend-only)
- **Rollback:** Revert player.html to C2 state

### C4 — Security + Integration Tests
- **Objective:** Add security regression tests for quiz-taking; verify two-user isolation in quiz context
- **Files affected:** `backend/tests/integration/` (new or extended test file)
- **Tests:** Two-user quiz isolation test; unauthorized quiz access test
- **Acceptance:** Security tests pass
- **Security:** Two-user isolation verified
- **Rollback:** Remove test file

### C5 — Browser E2E Full Loop
- **Objective:** Browser E2E test of the complete learning loop
- **Files affected:** `backend/tests/e2e/test_learner_journey.py` (extend)
- **Tests:** Full loop: sign in → open lesson → checkpoint → take quiz → submit → score → mastery update → next action change
- **Acceptance:** All E2E tests pass
- **Security:** E2E includes unauthorized access checks
- **Rollback:** Remove E2E test additions

### C6 — Regression + Release Gate
- **Objective:** Full regression gate before merge
- **Files:** None (verification only)
- **Tests:** Fast (1062+), PG (15+), E2E (all), Ruff, mypy (Δ≤0), Alembic (single head), secret scan, git diff --check
- **Acceptance:** All gates pass
- **Security:** Full security suite
- **Rollback:** N/A

### Gate Summary

| Checkpoint | Fast Tests | PG Tests | Ruff | Mypy | E2E | Security |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| C0 | ✅ | ✅ | ✅ | ✅ | — | — |
| C1 | ✅ | ✅ | ✅ | ✅ | — | ✅ |
| C2 | ✅ | — | ✅ | ✅ | Manual | — |
| C3 | ✅ | — | ✅ | ✅ | Manual | — |
| C4 | ✅ | ✅ | ✅ | ✅ | — | ✅ |
| C5 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| C6 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

---

## 24. Exit Criteria

P6 is complete when ALL of the following are true:

1. A learner can sign in, open a lesson, and see the learner journey panel
2. The learner journey panel has a "Take Quiz" button (when a quiz exists for the lesson)
3. Clicking "Take Quiz" opens a quiz overlay with questions and answer options
4. The learner can select answers for each question
5. The learner can submit the quiz
6. The learner sees a score result (percent, pass/fail)
7. After submission, the mastery summary in the learner journey panel updates
8. The next-action text reflects the new mastery state
9. After leaving and reopening the same lesson, progress and quiz status persist
10. Another user cannot access this user's quiz attempt (404)
11. All existing tests pass (no regression)
12. Browser E2E test passes for the full loop
13. Ruff clean, mypy Δ≤0, single Alembic head, secret scan clean

---

## 25. Future Roadmap

### NOW
**P6 — Interactive Assessment + Complete Learning Loop**

### NEXT (candidates, not committed)
- **P6.1 — Learner Progress Dashboard** — cross-lesson progress history, concept mastery visualization, learning velocity trends (depends on P6 data flow)
- **P7 — 2D Interactive Visual Learning Workspace** — canvas interaction, drag/connect/label, visual state persistence (depends on product decision)

### LATER
- Simulation engine DB definitions + more sim types
- Knowledge graph breadth
- Advanced analytics + effectiveness export
- Adaptive learning improvements (beyond heuristic)
- AI tutor improvements (grounding, citations)

### DEFERRED
- ML/DL learner intelligence (eval-gated; must beat existing heuristics)
- Framework frontend migration (no product need)
- Animation/simulation/video runtime HA persistence (no HA need)
- Multi-role/teacher-student collaboration
- Mobile applications
- Microservices/Kubernetes
- 2D slide-element editor (high complexity; separate phase)

### OUT OF SCOPE (project-wide, per governing rules)
- MySQL (PostgreSQL is production DB)
- Microservices architecture
- Kubernetes deployment
- Mobile applications
- ML/DL without justification
- Vector database replacement
- Knowledge graph as standalone feature

---

## 26. Risks

| Risk | Probability | Impact | Mitigation | Owner |
|------|:-----------:|:------:|------------|-------|
| Quiz generation returns no questions (empty quiz) | MED | MED | Verify quiz generation before allowing quiz start; show "No questions available" fallback | Engineering |
| Question type not supported in UI (e.g., drag-drop, hotspot) | MED | LOW | Start with MC + T/F; defer complex types to later | Engineering |
| Mastery update not reflected in panel after quiz | LOW | MED | Explicit panel refresh after quiz submission; verify in E2E | Engineering |
| Scope creep into quiz generation improvements | MED | HIGH | Enforce §15 NON-SCOPE; P6 only adds frontend UI | Program Owner |
| Player.html becomes too large/unmaintainable | LOW | MEDIUM | Consider extracting quiz JS into a separate file if >200 lines added | Engineering |
| Quiz timing (time_limit_minutes) not enforced in UI | LOW | LOW | Defer to NICE-TO-HAVE; backend does not enforce either | Engineering |
| Existing 83 mypy errors grow | LOW | MEDIUM | Enforce Δ=0 gate; no new mypy errors allowed | Engineering |

---

## 27. Final Recommendation

**P6 — Interactive Assessment + Complete Learning Loop** is the clear next phase for EduVision AI.

The evidence is unambiguous: the learner loop is broken at the assessment step, the backend quiz infrastructure is complete, the frontend architecture is sufficient, no database migration is needed, no new services are required, and the risk is low. P6 closes the largest remaining product gap with the highest reuse of existing code and the lowest implementation cost.

Build P6. Do not build the 2D editor, framework frontend, ML/DL, or enterprise infrastructure yet. Close the loop first.

---

*End of post-P5 product + architecture decision audit. Documentation only; no application, migration, test, CI, Docker, frontend, or dependency changes were made.*
