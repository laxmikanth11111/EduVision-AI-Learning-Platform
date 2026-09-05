# Post-P11 Capability Matrix — EduVision AI

**Phase:** Post-P11 audit (HEAD `30e3bbd`)
**Companion:** `POST_P11_PRODUCT_ARCHITECTURE_AUDIT.md`, `P12_SCOPE_AND_FOUNDATION.md`
**Convention:** VERIFIED (live + tested) · LIVE (wired, light/no direct tests) · PARTIAL (wired but incomplete) · BACKEND-ONLY (API+service, no frontend call) · SCHEMA-ONLY (tables/schemas present, no wire) · NOT IMPLEMENTED · OUT OF SCOPE

| Capability | Backend | API | Frontend | Browser E2E | Persistence | Status | Evidence | Gap |
|---|---|---|---|---|---|---|---|---|
| Auth / registration | `auth.py` | POST /api/v1/auth/* | `signin.html`, `signup.html` | smoke | users, redis JTI | VERIFIED | `test_security.py` 22 | refresh rotation (MEDIUM) |
| Presentation ingestion | `presentations.py`, `_read_upload_bounded` | upload/source/thumbnail | `upload.html` | smoke | presentations, files | VERIFIED | `test_upload_validation.py` 23 | — |
| Content extraction | `content_extraction_service.py` | via processing | processing | processing page | content_units/blocks | VERIFIED | presentation pipeline tests | AI retry |
| Lesson generation | `lesson_generation_service.py` + Celery | build/source flows | processing | — | generated_lessons(+versions) | VERIFIED | `test_lesson_generation_worker.py` | — |
| Topic outline | `topic_outline_service.py` | via build | — | — | topic_outlines | VERIFIED | P4 pipeline tests | — |
| Lesson player / slides | `player.py`, `player.html` | /player/* | player | learner_journey ×2 | learning_sessions | VERIFIED | E2E | mobile/responsive deferred |
| Visual canvases / SVG strategies | `visual_canvases.py` | /visual/* | player | P6 full loop | visual_* tables | VERIFIED | E2E | — |
| Animation generation + runtime | `animation_router`, `animation_runtime_router` | /animation/* | player (4 of 15 routes) | — | animation assets | PARTIAL | subagent frontend walk | narrow wiring |
| Simulation runtime | `simulation_router` | /simulation/* | player | — | simulation state | PARTIAL | subagent walk | narrow wiring |
| Video generation | `video_router`, `video_composition_service.py` | /video/* | player (generate) | — | videos, jobs | PARTIAL | subagent walk | render in request path |
| Video runtime (bookmark/assessment/tutor-context) | `video_runtime_router.py` | /video/runtime/* | **none** | — | video runtime state | BACKEND-ONLY | router not imported by frontend | G5 |
| Learning session / resume | `player.py`, `learner_progress_service` | /player/start, /me/progress | player | learner_journey | learning_sessions | VERIFIED | E2E | — |
| Interactive quiz delivery | `quiz_repository.py` (order_by position :151) | /quiz/attempts | player overlay | P6 full loop | quizzes, versions | VERIFIED **on SQLite only** | E2E | fixed order; shuffle ignored |
| Attempt persistence (PG) | `quiz_attempt_service.start_attempt` | POST /quiz/.../attempt | player | — | quiz_attempts, question_attempts | **BROKEN ON PG** (CRITICAL, empirically verified) | §12.2 audit + scratch PG probe | drift fix is P12 C0/C1 |
| Question grading / scoring | `quiz_attempt_service` `_evaluate_answer`, `score_summary` | submit answer, submit quiz | player overlay | P6 full loop | score_summary | VERIFIED (**SQLite**) | `test_p6_*`, `test_quiz_routes.py` | PG persist leg blocked |
| Mastery model | `educational_memory_service.py` | drives many | chips | P10 NG-3 | educational_memories | VERIFIED | NG-3 E2E (public-ID keyed) | decay not persisted |
| Recommendations | `recommendation_engine.py` | /me/progress | dashboard `recoAction` | P10 NG-2 | derived | VERIFIED | E2E | — |
| RAG tutor | `mastery_tutor_service.py`, `app.ai.retrieval` | /tutor/*, /assistant/* | `tutor.html` | P8 (asserts `rag`) | tutor_sessions/messages, chunks | VERIFIED | E2E; `test_rag_semantic_retrieval.py` | RRF/MMR inert |
| Review scheduler | `review_scheduler.py` + `review_schedule_service.py` | /me/review | dashboard review panel | P10 NG-3 ×3 | review_schedules | VERIFIED | E2E | ladder fixed 1/3/7/14 |
| Today Plan (P11) | `study_plan_service.py` | /me/plan/today, complete | dashboard `#todayPlanBody` | P11 E2E | study_plans.days JSONB | VERIFIED | E2E P11 | practice-selection simplification (documented) |
| Learning Goals (P11) | `learning_goal_service.py` | /me/goals/* | dashboard `#goalsBody` | P11 E2E | learning_goals | VERIFIED | E2E P11 | O(n) refresh at small n |
| Learning Path (P11) | `learning_path_service.py` | /me/path | dashboard `#pathBody` | P11 E2E | learning_paths | VERIFIED | E2E P11 | single active path by design |
| Genuine adaptive assessment (NG-4) | `adaptive_assessment_engine.py` (dead, VisualQuestion-based) | — | — | — | (tables exist) | NOT IMPLEMENTED | dead engine; fixed-order quiz | **P12 A2** |
| Learner analytics / insights | — | — | dashboard trend only | — | analytics_* tables (registered, unused) | PARTIAL | schema-only | G3 (post-P12 candidate) |
| Player → review queue entry | — | — | missing in `player.html` | — | — | NOT CONNECTED | subagent walk | G7 (LOW) |
| Assessment → immediate scheduling | — | — | — | — | — | PARTIAL | `_ensure_schedules` lazy | G6 (LOW) |
| Retention (scheduled/global) | `enforce_retention` in list_sessions only | — | — | — | tutor rows | PARTIAL | audit | G8 (MEDIUM) |
| User isolation / ownership | repos, routers, UoW | all /me/* + CRUD | authorization header flows | — | — | VERIFIED | two_user 22, p11 security 5, p6 14 | — |
| AIContentService abstraction | `app/ai/service.py`, providers registry | n/a | n/a | — | ai_usage | VERIFIED | ws4 tests; zero SDK in app/ | `get_ai` dep dead |
| Semantic RAG | `app.ai.retrieval` | n/a | rag badges | P8 `rag` | chunk_embeddings | VERIFIED | P8 E2E | semantic-only |
| Embeddings pipeline | Celery `embedding.*` tasks | n/a | n/a | — | chunk_embeddings, jobs | VERIFIED | `test_embedding_worker_tasks.py` 29 | no live broker test |
| Redis / Celery infra | `redis_client`, `celery_app`, `safe_dispatch`/DLQ | n/a | n/a | — | redis | PARTIAL (mocked in tests) | ws4 | no functional integration test |
| Rate limiting | `RateLimitMiddleware` (Lua) | all | n/a | — | redis | VERIFIED | `test_rate_limit.py` 15 | — |
| Storage / exports | `storage.py`, `export_service` | /storage, /exports | export UI | in pipeline | export files, objects | VERIFIED | exports e2e | — |
| Observability | `observability/metrics.py` incl. `p11_*` counters | GET /api/v1/metrics | — | — | redis/in-memory | VERIFIED | P11 report §9 | — |
| Study plans/goals/paths (0011) | P11 models/repos/services | /me/plan, /me/goals, /me/path | dashboard panels | P11 | 0011 tables | VERIFIED | E2E P11 | — |
| Teacher/classroom/collab/mobile/2D-editor/framework-migration | — | — | — | — | — | OUT OF SCOPE | audit AG list | unchanged |

**Legend note:** "VERIFIED on SQLite only" = green under the SQLite `create_all` test path but NOT under migrated PostgreSQL (see CRITICAL §12 in the audit); entries not marked are dual-dialect safe on the tested paths.

**Summary:** 2 CRITICAL-blocked rows (attempt persistence and anything consuming it), 1 NOT IMPLEMENTED product gap (NG-4), 4 PARTIAL infrastructure rows, 1 SCHEMA-ONLY domain, 1 NOT CONNECTED LOW, and a fully VERIFIED core spine (learn → assess → mastery → recommend → review → plan/goal/path → dashboard).