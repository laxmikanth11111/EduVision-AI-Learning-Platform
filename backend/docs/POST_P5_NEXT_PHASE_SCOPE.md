# POST-P5 Next Phase Scope

**Recommended Phase:** P6 — Interactive Assessment + Complete Learning Loop
**Repository state:** HEAD = `cba306b`, branch `feature/individual-user-foundation`, clean.
**Generated:** 2026-09-03

---

## 1. Phase Name

**P6 — Interactive Assessment + Complete Learning Loop**

---

## 2. Objective

Build the quiz-taking UI in the vanilla SPA player (`player.html`) and verify the complete closed learning loop in the browser: a learner can open a lesson, take an assessment quiz, submit answers, see their score, observe mastery update, and receive an actionable next step — all without leaving the player and without developer/API intervention.

---

## 3. User Problem

The learner can see "Checkpoint pending" in the learner journey panel but **cannot take the quiz**. There is no button to start, no question display, no answer selection, no submit, and no results view. This means:

- The learner cannot practice or test their understanding
- Mastery never updates from quiz results through the browser
- The recommendation engine's next actions are informational only (no action buttons)
- The core promise ("AI-native *learning* platform") is not delivered end-to-end

---

## 4. Success Definition

P6 is complete when a learner can, in a real browser:

1. Sign in and open a lesson
2. See the learner journey panel with progress and checkpoint status
3. Click "Take Quiz" to start an assessment
4. See quiz questions with answer options
5. Select answers for each question
6. Submit the quiz
7. See score results (percent, pass/fail)
8. Observe the mastery summary update in the learner journey panel
9. See the next-action text reflect the new mastery state
10. Leave and reopen the same lesson — progress and quiz status persist
11. Another user cannot access their quiz attempt

---

## 5. Scope

### In Scope
- Quiz-taking UI in `player.html` (overlay or panel)
- Question rendering (multiple-choice, true/false minimum)
- Answer selection UI (radio buttons, toggles)
- Quiz navigation (prev/next within quiz)
- Submit button + loading state
- Score/results display (percent, pass/fail, per-question feedback)
- "Take Quiz" / "Retake Quiz" buttons in learner journey panel
- Panel refresh after quiz submission (mastery + next-action update)
- Mastery update verification (backend already wired; browser path needed)
- Next-action actionability (text display; action buttons are NICE-TO-HAVE)
- Security regression tests (two-user quiz isolation)
- Browser E2E of the full loop
- Unit tests for quiz UI rendering functions

### Not In Scope
- Quiz generation improvements (AI quality)
- Complex question types (drag-drop, hotspot, fill-in-blank) — defer
- Time limit enforcement in UI — defer
- Immediate per-question feedback — defer (NICE-TO-HAVE)
- Quiz analytics dashboard — defer (future P6.1)
- Concept mastery visualization (charts) — defer (future P6.1)
- Cross-lesson progress history — defer (future P6.1)

---

## 6. Non-Scope (Explicitly Excluded)

Per project rules and this audit's decision:

- **No new database tables** — all quiz/mastery/learning tables exist (migrations 0005–0010)
- **No new backend services** — reuse QuizAttemptService, QuizGenerationService, EducationalMemoryService, RecommendationEngine
- **No new AI providers** — reuse existing quiz generation path
- **No frontend framework migration** — enhance existing vanilla SPA
- **No 2D slide-element editor** — separate future phase
- **No ML/DL** — eval-gated; not justified
- **No vector database additions** — existing RAG infrastructure sufficient
- **No microservices** — single-app architecture preserved
- **No mobile applications** — web only
- **No animation/simulation HA persistence** — no HA need
- **No collaboration/teacher roles** — individual learner only
- **No Alembic migration** — schema unchanged

---

## 7. Architecture

### What Changes
Only `backend/frontend/player.html` and `backend/tests/` are modified. No backend application code changes. No database changes. No new dependencies.

### What Reuses Existing Code
| Existing Component | How Reused |
|-------------------|------------|
| `QuizAttemptService` | Frontend calls existing endpoints: start_attempt, submit_answer, submit_quiz |
| `QuizGenerationService` | Called by teacher/system before learner sees quiz (existing) |
| `EducationalMemoryService` | Called by mastery endpoint (already wired in P5) |
| `RecommendationEngine` | Called by mastery endpoint (already wired in P5) |
| `LessonPlayerService` | Checkpoint + mastery endpoints (already wired in P5) |
| `authFetch()` pattern | JWT handling with auto-refresh (existing in player.html) |
| `APIResponse` envelope | Consistent API response shape (existing) |
| Learner journey panel | Extends existing panel with action buttons |

### Quiz Flow Architecture

```
Learner clicks "Take Quiz"
  ↓
Frontend: GET /lessons/{id}/player/checkpoint → get quiz ID
  ↓
Frontend: POST /quizzes/{quiz_id}/attempts → start attempt, get questions
  ↓
Frontend: Render questions + answer options in quiz overlay
  ↓
Learner selects answers
  ↓
Frontend: POST /quizzes/{quiz_id}/attempts/{attempt_id}/submit → submit all answers
  ↓
Backend: Evaluate answers, compute score, update quiz attempt status
  ↓
Frontend: Display score results
  ↓
Frontend: GET /lessons/{id}/player/mastery → refresh mastery + next action
  ↓
Frontend: Re-render learner journey panel with updated data
```

---

## 8. Backend Changes

**NONE.** All required backend endpoints already exist and are tested:

| Endpoint | Method | Path | Purpose |
|----------|--------|------|---------|
| Checkpoint | GET | `/api/v1/lessons/{id}/player/checkpoint` | Get quiz metadata + attempt status |
| Start attempt | POST | `/api/v1/quizzes/{quiz_id}/attempts` | Start or resume a quiz attempt |
| Get quiz | GET | `/api/v1/quizzes/{quiz_id}` | Get quiz details + questions |
| Submit answer | POST | `/api/v1/quizzes/{quiz_id}/attempts/{attempt_id}/answers/{question_id}` | Save single answer |
| Submit quiz | POST | `/api/v1/quizzes/{quiz_id}/attempts/{attempt_id}/submit` | Finalize + score |
| Mastery | GET | `/api/v1/lessons/{id}/player/mastery` | Get mastery + next action |

---

## 9. Database Changes

**NO DATABASE MIGRATION REQUIRED.**

Existing tables (all verified):
- `quizzes` — quiz metadata, linked to lesson
- `quiz_versions` — versioned quiz content
- `quiz_contents` / `questions` — question stems, types, options
- `question_options` — answer choices
- `answer_keys` — correct answers
- `quiz_attempts` — user attempts with status, score
- `question_attempts` — per-question attempt status
- `user_answers` — user's submitted answers
- `question_explanations` — post-quiz explanations
- `score_summaries` — aggregated scores
- `learning_sessions` — persistent user progress
- `educational_memories` — concept mastery data

Alembic head remains at `0028_ws10_idempotency_key_index`.

---

## 10. API Changes

**NONE.** All required APIs already exist. See §8.

---

## 11. Frontend Changes

### Files Modified
| File | Change |
|------|--------|
| `backend/frontend/player.html` | Add quiz-taking UI (overlay/panel), question renderer, answer selector, submit + results, action buttons in learner journey panel |

### Quiz UI Components (within player.html)

1. **Quiz trigger** — "Take Quiz" button in the learner journey panel (`#ljPanel`)
2. **Quiz overlay** — full-screen or panel overlay within the slide viewport
3. **Question header** — question number, total, progress indicator
4. **Question stem** — renders question text
5. **Answer options** — radio buttons (MC), toggle (T/F), styled to match existing design
6. **Navigation** — prev/next buttons within quiz, question overview (optional)
7. **Submit** — submit button with loading state
8. **Results** — score display (percent, pass/fail), per-question feedback
9. **Action buttons** — "Continue Learning", "Retake Quiz" (in results view)
10. **Panel refresh** — after quiz close, re-fetch checkpoint + mastery and re-render panel

### Design Patterns Followed
- Same CSS variables (`--ink`, `--paper`, `--amber`, `--teal`, `--coral`)
- Same font families (Space Grotesk, Manrope)
- Same button styles (`.btn-present`, `.icon-btn`, `.nav-btn`)
- Same panel patterns (`.lj-panel`, `.lj-chip`, `.lj-action`)
- Same auth pattern (`authFetch()`)
- Same DOM manipulation (no framework)
- Same error handling (`apiError()`)

---

## 12. AI Changes

**NONE.** Quiz generation already uses existing AI providers. P6 only adds the frontend UI for quiz-taking (which calls deterministic backend endpoints). No new AI calls are introduced.

---

## 13. RAG Changes

**NONE.** Existing RAG infrastructure is not modified.

---

## 14. Security Requirements

### Already Enforced (backend)
- Ownership-404 on all quiz endpoints (`QuizAttemptService.assert_quiz_ownership`)
- JWT authentication on all quiz endpoints
- Attempt status validation (only "in_progress" can be submitted)
- User-scoped queries (all quiz data filtered by user_id)

### Required for P6
1. **E2E test:** second user cannot access another user's quiz attempt → 404
2. **E2E test:** quiz submission updates correct user's mastery
3. **Verification:** quiz-taking flow works through authFetch() with JWT
4. **Verification:** no quiz data leaks between users in the browser

---

## 15. Testing Requirements

### Unit Tests
- Quiz question rendering function (question type → HTML mapping)
- Answer state management (selected answers tracking)
- Quiz progress calculation (answered / total)

### Integration Tests
- Two-user quiz isolation (User A's attempt not visible to User B)
- Unauthorized quiz access → 404
- Quiz submission only for "in_progress" attempts

### PostgreSQL Tests
- (Verify existing PG tests still pass; no new PG-specific behavior)

### Browser E2E Tests
- Full loop: sign in → open lesson → checkpoint → take quiz → answer questions → submit → see score → mastery update → next action change
- Two-user isolation in browser context

### Regression
- Fast suite (1062+)
- PostgreSQL suite (15+)
- Ruff (clean)
- Mypy (Δ≤0)
- Alembic (single head)
- Secret scan (clean)

---

## 16. Browser E2E Requirements

The following browser journey MUST pass before P6 is complete:

```
1. Sign in via SPA form → redirected to upload.html
2. Create lesson via API (setup)
3. Open player.html?lesson=...&deck=...
4. Player loads topics in sidebar
5. Learner journey panel visible with:
   - Progress bar (X%)
   - Assessment: "Checkpoint pending" chip
   - Next action text
6. Click "Take Quiz" button
7. Quiz overlay opens with:
   - Question 1 stem visible
   - Answer options visible (multiple choice)
8. Select answer for question 1
9. Navigate to question 2
10. Select answer for question 2
11. Click "Submit Quiz"
12. Results display:
   - Score: X%
   - Pass/Fail indicator
13. Close quiz results
14. Learner journey panel refreshes:
   - Assessment: "Checkpoint passed" (if passed)
   - Mastery summary updated
   - Next action text updated
15. Navigate away (upload.html)
16. Reopen same lesson
17. Progress persists (topic position)
18. Quiz attempt shows "completed" with score
```

---

## 17. Checkpoint Plan

| Checkpoint | Objective | Files | Tests | Acceptance | Gate |
|:---:|---------|-------|-------|------------|------|
| C0 | Baseline verification | None | Fast+PG+Ruff+mypy | All P5 gates pass | Full regression |
| C1 | Backend quiz wiring verification | Tests only | Integration | Quiz lifecycle works via API | Fast+PG+Security |
| C2 | Quiz-taking UI in player | `player.html` | Manual browser | Quiz flow works in browser | Fast+Ruff+mypy+Manual |
| C3 | Learner journey panel enhancement | `player.html` | Manual browser | Action buttons + panel refresh | Fast+Ruff+mypy+Manual |
| C4 | Security + integration tests | `tests/integration/` | Unit+Integration | Two-user isolation | Fast+PG+Security |
| C5 | Browser E2E full loop | `tests/e2e/` | E2E | Full loop passes | All gates |
| C6 | Regression + release gate | None | Full suite | All gates pass | Full regression |

---

## 18. Exit Criteria (Detailed)

| # | Criterion | Verification |
|---|-----------|-------------|
| 1 | Learner can sign in and open a lesson | Browser E2E |
| 2 | Learner journey panel shows progress + checkpoint status | Browser E2E |
| 3 | "Take Quiz" button appears when quiz exists | Browser E2E |
| 4 | Clicking "Take Quiz" opens quiz overlay | Browser E2E |
| 5 | Questions display with answer options | Browser E2E |
| 6 | Learner can select answers | Browser E2E |
| 7 | Learner can submit the quiz | Browser E2E |
| 8 | Score results display (percent, pass/fail) | Browser E2E |
| 9 | Mastery summary updates after submission | Browser E2E |
| 10 | Next-action text changes after mastery update | Browser E2E |
| 11 | Progress persists after leaving and reopening | Browser E2E |
| 12 | Another user cannot access quiz attempt | Security test |
| 13 | All existing tests pass (no regression) | Full regression |
| 14 | Ruff clean | Lint gate |
| 15 | Mypy Δ≤0 | Type gate |
| 16 | Single Alembic head | Migration gate |
| 17 | Secret scan clean | Security gate |
| 18 | Working tree clean (after commit) | Git gate |

---

## 19. Risks and Mitigations

| Risk | Probability | Impact | Mitigation |
|------|:-----------:|:------:|------------|
| Quiz generation returns no questions | MED | MED | Verify quiz exists before showing "Take Quiz"; show fallback message |
| Complex question types unsupported | MED | LOW | Limit to MC + T/F in P6; defer drag-drop/hotspot |
| Player.html becomes unwieldy | LOW | MED | Extract quiz JS into separate file if >200 lines added |
| Mastery not reflected after quiz | LOW | MED | Explicit re-fetch + re-render after submission; verify in E2E |
| Scope creep | MED | HIGH | Strict non-scope enforcement; P6 = frontend UI only |
| Mypy errors grow | LOW | MED | Enforce Δ=0 at every gate |

---

## 20. Dependencies

| Dependency | Status | Risk |
|------------|--------|------|
| P5 (persistent progress, checkpoint, mastery) | COMPLETE | None |
| Quiz backend (QuizAttemptService, endpoints) | COMPLETE | None |
| Educational memory + recommendation engine | COMPLETE | None |
| Player HTML/CSS patterns | COMPLETE | None |
| authFetch() pattern | COMPLETE | None |
| Playwright E2E infrastructure | COMPLETE | None |

**No external dependencies required.** P6 depends only on existing, verified components.

---

*End of POST-P5 next phase scope. Documentation only; no application changes.*
