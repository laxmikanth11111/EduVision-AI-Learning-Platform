# EduVision AI — AI-Powered Interactive Learning Platform

> **Status:** audited, hardened, and tested — see [Engineering Readiness Report](docs/audits/FINAL_ENGINEERING_READINESS_REPORT.md)
> and [Requirements / Evidence Matrix](docs/audits/REQUIREMENTS_EVIDENCE_MATRIX.md).

EduVision AI turns uploaded presentations and documents into interactive
learning experiences: extracted content → hierarchical topic outline → AI
generated lessons → quizzes → mastery tracking → adaptive recommendations,
with a mastery tutor and multi-step visual learning (analogies, C3 canvas
visuals, C4 topic animations, simulations, video).

## Repository layout

```
backend/                    # FastAPI application (canonical backend)
  app/                      # api/v1 routers, ai providers, services, models, workers (Celery)
  frontend/                 # CANONICAL frontend (vanilla JS/HTML served at /frontend)
  tests/                    # unit/ integration/ postgres/ e2e
  docs/                     # phase reports + implementation notes
docs/                       # audit deliverables (baseline, matrix, readiness, command log)
EduVision_AI_Frontend/      # DEPRECATED static prototype — do not modify (see README)
.github/workflows/ci.yml    # CI: lint, unit, integration, migration, postgres, secret scan, mypy, docker
docker-compose.yml          # postgres + redis + minio + backend + celery-worker + celery-beat
```

## Quick start

```bash
cd backend
python -m venv .venv && .venv\Scripts\activate   # Windows; source .venv/bin/activate elsewhere
pip install -r requirements.txt
cp .env.example .env                             # then fill in real values
alembic upgrade head
uvicorn app.main:app --reload
```

The canonical web UI is served at `http://localhost:8000/frontend/` (aliases:
`/`, `/login`, `/dashboard`, `/player`, `/tutor`, `/upload`, `/processing`,
`/videos`).

## Pipeline at a glance

1. **Upload & extraction** — PDF/PPTX/DOCX/TXT parsed into content units.
2. **Chunking + embeddings** — structure-aware chunking; vectors persisted as
   JSONB `ChunkEmbedding` rows; async via Celery workers.
3. **Topic outline (C2)** — deep hierarchical learning structure with exact
   source references; deterministic fallback if AI unavailable.
4. **Lesson generation** — RAG-grounded AI lessons validated against a JSON
   schema; grounded safety validator; prompt-injection defense.
5. **Quiz → Mastery → Recommendation** — deterministic scoring engine.
6. **Mastery tutor** — semantic RAG over learner's own chunks, deterministic
   refusal of injection attempts, deterministic fallback when RAG is cold.
7. **Visual learning** — C3 visual canvases, C4 topic animations, simulations,
   video renders.

## Engineering guardrails

- **Grounding** — every AI lesson records a deterministic source-coverage
  estimate; tutor answers carry attribution + confidence.
- **Prompt-injection defense** — uploaded documents and learner messages are
  treated as data; a lexical scanner gates the blocking path
  (`AI_PROMPT_INJECTION_ENABLED`, `AI_PROMPT_INJECTION_THRESHOLD`).
- **Auth hardening** — Argon2-ID hashing, JWT with aud/iss/jti, per-account
  login lockout (`MAX_LOGIN_ATTEMPTS`/`LOGIN_LOCKOUT_MINUTES`), refresh-token
  rotation + reuse detection.
- **Async everything** — long pipelines run on Celery with `task_acks_late`,
  idempotency, DLQ option, and in-memory/Redis fallbacks so the product
  survives a Redis outage.

## Verification

```bash
cd backend
.venv\Scripts\python.exe -m ruff check app tests scripts --no-fix
.venv\Scripts\python.exe -m mypy app                 # budget 86 (no growth)
.venv\Scripts\python.exe -m pytest tests/unit -q
.venv\Scripts\python.exe -m pytest tests/integration -q
alembic heads                                        # exactly one head
```

PostgreSQL and Playwright e2e suites require Docker (blocked on this machine —
see the readiness report).

## Documentation

- [Baseline audit](docs/audits/BASELINE.md)
- [Requirements / Evidence matrix](docs/audits/REQUIREMENTS_EVIDENCE_MATRIX.md)
- [Final engineering readiness report](docs/audits/FINAL_ENGINEERING_READINESS_REPORT.md)
- [Command log](docs/audits/FINAL_COMMAND_LOG.md)
- [Architecture](docs/architecture/ARCHITECTURE.md)
- [Evaluation](docs/evaluation/README.md)

> Security note: `backend/.env` (gitignored) may contain live provider keys.
> Rotate them before shipping; never commit secrets.