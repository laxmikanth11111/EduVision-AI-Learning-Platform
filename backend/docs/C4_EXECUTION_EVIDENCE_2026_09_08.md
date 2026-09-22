# C4 execution evidence — 2026-09-08

This record supersedes unsupported completion claims in the pre-existing C4 reports.
Starting branch: feature/individual-user-foundation. Starting HEAD: d873d99.
The worktree already contained 17 modified tracked files and substantial untracked
C1/C2/C4 source, tests and documentation. None was deleted or staged in this run.
Authoritative frontend: backend/frontend, served by FastAPI. PostgreSQL remains
production storage. Alembic heads and current both returned
0036_c4_topic_animation_assets (one applied head).

## C4.0 forensic audit — VERIFIED
Inspected source extraction, outline hierarchy, C3 integration, all C4 layers,
player wiring, test configuration, browser/quality scripts, models, migration,
Git status, recent commits, deployment configuration and prior evidence reports.
Baseline targeted regression: 212 passed, 1120 deselected, 1 warning in 46.32s.
The selection covered C4, C2, C3, parser and lesson-player tests; this is not a
claim that the complete C1 integration suite ran (the -k filter also applied there).

Initial checkpoint classification:
| Checkpoint | Status | Remaining evidence/work |
| --- | --- | --- |
| C4.1 | PARTIAL | Graph integrity and scene-specific interaction validation |
| C4.2 | IMPLEMENTED_UNVERIFIED | Semantics and representative generated content |
| C4.3 | PARTIAL | Concurrent deduplication, versions, persistent failures |
| C4.4 | PARTIAL | Reveal timing, scene continuity, controls |
| C4.5 | PARTIAL | Failure lifecycle and stale output |
| C4.6 | PARTIAL | Real retries, broker failure, worker execution |
| C4.7 | PARTIAL | Browser acceptance and isolated iframe bridge |
| C4.8 | PARTIAL | Playback, timeline, accessible controls |
| C4.9 | PARTIAL | Actual feedback and useful interaction |
| C4.10 | PARTIAL | Visual state and explanation synchronization |
| C4.11 | PARTIAL | Preserve complete source references |
| C4.12 | IMPLEMENTED_UNVERIFIED | Ownership, Unicode filenames, player download |
| C4.13 | PARTIAL | Private caching, iframe isolation, IDOR and injection |
| C4.14 | PARTIAL | Real user interactions and runtime evidence |
| C4.15 | PARTIAL | Assess actual educational correctness |
| C4.16 | NOT_STARTED | Full regression |
| C4.17 | NOT_STARTED | Final security/change audit |
| C4.18 | NOT_STARTED | Final corrected documentation |
| C4.19 | NOT_STARTED | All acceptance gates |

## EDUVISION CHECKPOINT RESULT — C4.1
Status: VERIFIED (schema acceptance; browser playback belongs to later gates).
What existed: bounded typed animation specifications and 21 schema tests.
Changed: reject duplicate/overlapping graph IDs, missing edge endpoints and invalid
initial scene nodes; add an optional explicit interaction scene, preserving the
legacy final-scene default; validate anchors in that scene and reject duplicate
interaction IDs. Renderer mapping follows the explicit scene.
Root cause: schema used a union of local step numbers across scenes, whereas the
renderer always anchored interactions in the last scene.
Tests: 47 passed in 16.69s across schema, generator and renderer modules.
Ruff: check passed; new test formatting corrected after format check.
Mypy: no issues in 2 source files, with --follow-imports=silent. This is scoped
verification and does not establish global Mypy success.
Integration: existing generator/renderer contracts passed; no HTTP contract removed.
Browser: not required for this schema gate; later browser gates remain open.
Security: graph identity/target validation strengthened; no secrets added.
Database: no migration change; existing JSON accepts the additive field.
Student quality: interaction prompts can now target their intended scene.
Limitations: renderer behavior, lifecycle, and broader phase acceptance remain open.
Commit: none; preserve the interleaved starting worktree until a coherent change
set and dependency boundary can be established.
Next checkpoint: C4.2 planning.
