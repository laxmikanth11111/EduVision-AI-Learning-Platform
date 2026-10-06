# EduVision AI — Production Deployment

Operational runbook for deploying the release candidate
`bb1b87b7e393b1edd128cbc6b85125752e9d896f` (branch `feature/individual-user-foundation`)
to a public HTTPS URL.

Read-only audit references: `docs/audits/FINAL_ENGINEERING_READINESS_REPORT.md`.

---

## 1. Topology

```text
                    INTERNET
                       │
                  HTTPS (TLS terminated by the platform
                       │   or a reverse proxy)
                       ▼
        ┌──────────────────────────────┐
        │  backend  (FastAPI :8000)    │   ← the only public service
        │  serves /frontend/* AND      │
        │        /api/v1/*             │
        └───────────┬──────────────────┘
                    │
     ┌──────────────┼──────────────┬────────────────┐
     ▼              ▼              ▼                ▼
 PostgreSQL      Redis         storage_data     MinIO
 PRIVATE         PRIVATE       PERSISTENT       PRIVATE, off by default
 no host port    no host port  named volume     (profile: minio)
 requirepass                    STORAGE_PROVIDER=local
     │              │
     │              └──────────────┬──────────────────────┐
     │                             ▼                      ▼
     └──────────────────────► celery-worker          celery-beat
                    PRIVATE, no host port       PRIVATE, no host port

   migrate  —  one-shot container, runs `alembic upgrade head` once, exits 0
```

There is deliberately **no separate frontend service and no frontend build**.
`backend/app/main.py` mounts `backend/frontend/` at `/frontend` and redirects `/`
to `/frontend/dashboard.html`. Every page calls the API through the relative path
`const API = '/api/v1'`, so the browser makes same-origin requests only: no CORS
preflight, no absolute API URL to inject, no nginx in front.

---

## 2. Files in this deployment path

| File | Purpose |
| ---- | ------- |
| `.env.production.example` | Template for `.env.production`. Contains **no real secrets**; every secret is a `CHANGE-ME` sentinel that `config.py` rejects at import, so an incomplete file fails loudly instead of starting with a guessable key. |
| `docker-compose.prod.yml` | Production topology. Separate project name (`eduvision-prod`), private infrastructure, persistent volumes, single migration step. |
| `deploy/README.md` | This runbook. |

`docker-compose.yml` is **unchanged** and remains the development stack.

---

## 3. Exposure contract

| Service | Public? | Notes |
| ------- | ------- | ----- |
| `backend` | yes | Only entry point. `127.0.0.1:${APP_PORT}:8000` locally; on a PaaS delete `ports:` and let ingress target container port 8000. |
| `postgres` | no | No `ports:` block. |
| `redis` | no | No `ports:` block, plus `requirepass`. |
| `celery-worker` | no | No `ports:` — the Celery broadcast control interface is never network-reachable. |
| `celery-beat` | no | No `ports:`. |
| `migrate` | n/a | One-shot. |
| `minio` | no | Profile-gated, no `ports:`. Console on 9001 is a full admin surface and is never published. |

The `migrate` service depends on postgres+redis; `backend`, `celery-worker` and
`celery-beat` depend on `migrate: service_completed_successfully`. That ordering
is the "migration step, then application starts" guarantee.

---

## 4. Prerequisites

- Docker Engine + Compose v2 (`docker compose`, not `docker-compose`).
- A real HTTPS origin (custom domain or platform `*.onrender.com` / `*.fly.dev` style hostname).
- A reachable PostgreSQL and Redis. Either the compose services below, or managed
  equivalents — in which case point `DATABASE_URL` / `REDIS_URL` /
  `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` at those and drop the `postgres`
  and `redis` services.
- **Persistent storage for `LOCAL_STORAGE_PATH`.** With `STORAGE_PROVIDER=local`
  the volume `storage_data` is what makes uploads and exports survive a
  container replacement. On a platform with an ephemeral container filesystem,
  stop and switch to a real object store instead of silently accepting data loss:

  ```text
  STORAGE_PROVIDER=s3
  S3_ENDPOINT_URL=https://<public-s3-endpoint>     # public https, never an internal name
  S3_ACCESS_KEY_ID=...  S3_SECRET_ACCESS_KEY=...
  S3_USE_SSL=true
  ```

  A genuinely public https endpoint is required. Pointing `S3_ENDPOINT_URL` at an
  internal MinIO makes `generate_presigned_url()` return a URL containing an
  internal hostname that no public browser can resolve.

---

## 5. Deployment procedure

### Step 1 — Create the environment file

```bash
cp .env.production.example .env.production
```

Generate the secrets and paste them in (`openssl` shown; any CSPRNG is fine, but
keep the output hex-only so it needs no URL-encoding inside connection strings):

```bash
openssl rand -hex 32   # APP_SECRET_KEY
openssl rand -hex 32   # JWT_SECRET_KEY   (must DIFFER from APP_SECRET_KEY)
openssl rand -hex 32   # CSRF_SECRET
openssl rand -hex 16   # POSTGRES_PASSWORD  (and the same value in DATABASE_URL
                       #                   and DATABASE_SYNC_URL)
openssl rand -hex 16   # REDIS_PASSWORD    (and the same value in REDIS_URL,
                       #                   CELERY_BROKER_URL, CELERY_RESULT_BACKEND)
```

Then set the one deployment-specific value:

```dotenv
APP_URL=https://<your-public-host>
APP_CORS_ORIGINS=https://<your-public-host>
```

`APP_CORS_ORIGINS` drives **both** CORS and `TrustedHostMiddleware`. The hostname
is derived from it (`config.py:483-504`). If it does not match the real hostname,
every request returns `400 Invalid host header`. No trailing slash, no path.

`.env.production` is gitignored. Confirm before committing anything:

```bash
git check-ignore -v .env.production   # expect: matched by .gitignore
```

### Step 2 — Validate the configuration without deploying

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml config >/dev/null
```

This fails fast on any missing secret (`${VAR:?message}`) and on invalid YAML.
Then prove the application accepts the environment:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml run --rm --no-deps \
  migrate python -c "from app.core.config import settings; print('settings OK:', settings.APP_ENV)"
```

`ValueError` here means a production validator in `config.py` rejected the file.
Read the message; it names the setting.

### Step 3 — Build

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml build
```

### Step 4 — Deploy

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml up -d
```

Migrations run automatically as the one-shot `migrate` service before the
application starts. Verify:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml ps -a
```

Expect `migrate` to show `Exited (0)` and everything else `Up (healthy)`.

### Step 5 — Confirm the single migration step

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml \
  logs migrate | tail -20
docker compose --env-file .env.production -f docker-compose.prod.yml \
  run --rm --no-deps migrate alembic heads
```

`alembic heads` must print exactly one head. `AUTO_MIGRATE_ON_STARTUP=false` in
`.env.production` is what stops each gunicorn worker from racing its own
`alembic upgrade` on every boot.

### Step 6 — Verify

```bash
BASE=https://<your-public-host>
curl -fsS -o /dev/null -w '%{http_code}\n' "$BASE/"                    # 302
curl -fsS "$BASE/api/v1/health/ready"                                  # "status":"ready"
curl -s  -o /dev/null -w '%{http_code}\n' -H "Host: wrong.example" "$BASE/"   # 400
```

The last check is deliberate: a `400` proves `TrustedHostMiddleware` is actually
active rather than wide open.

Then prove a worker really consumes a task, rather than trusting that the
container is up:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml \
  exec celery-worker celery -A app.workers.celery_app inspect ping
```

and exercise the full journey in a browser: register → login → upload → wait for
processing → dashboard → player → tutor → logout.

---

## 6. Rollback

| Situation | Action |
| --------- | ------ |
| Bad release | Redeploy the previous image/commit. Keep the database. |
| Schema problem | **Do not** run `alembic downgrade` or `DROP DATABASE` on a populated database. Restore from the provider's backup, or roll the application back to the commit matching the current schema. |
| Fresh, unwanted deploy (no real data yet) | `docker compose --env-file .env.production -f docker-compose.prod.yml down -v` — the `-v` is safe **only** while the volumes hold no data worth keeping. |
| Config mistake | Fix `.env.production`, then `up -d --force-recreate`. |

---

## 7. Operations

**Logs**

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml logs -f backend
```

`LOG_FORMAT=json`, `LOG_MASK_SENSITIVE=true`. `LOG_LEVEL=DEBUG` is rejected in
production by `config.py:579-580`.

**Scaling.** Add web or worker replicas freely. Do **not** raise `WEB_CONCURRENCY`
without re-checking the connection math:
`DATABASE_POOL_SIZE + DATABASE_MAX_OVERFLOW` is **per worker**, so total
connections are roughly `web_replicas x WEB_CONCURRENCY x (pool + overflow)`.
Stay well under the provider's connection ceiling.

**Backups.** The named volumes are local to one Docker host. Database backups
must come from `pg_dump`/`pg_dumpall` on a schedule (or a managed PostgreSQL with
snapshots); `storage_data` needs a file-level backup or object-store replication.
Neither is provided by this compose file.

**Reverse proxies.** `RATE_LIMIT_TRUSTED_PROXIES` must include the proxy's source
range. `rate_limit.py:234-247` honours `X-Forwarded-For` **only** when the direct
peer matches; otherwise every visitor is attributed to the proxy and shares one
rate-limit bucket (login is capped at 10/60s, so a demo can lock itself out).

---

## 8. Known limitation that deployment does not fix

**Gemini free-tier / provider availability remains an external limitation.**

With `AI_PROVIDER=gemini` and the default `AI_MODEL=gemini-3.5-flash`,
`POST /v1beta/models/gemini-3.5-flash:generateContent` intermittently returns
HTTP 503 "high demand"; Pro models returned 429 quota. `gemini-3.5-flash-lite`,
`gemini-flash-lite-latest` and `gemini-3-flash-preview` were observed succeeding.
There is **no cross-provider failover**. See
`backend/docs/EDUVISION_FINAL_ENGINEERING_REPORT.md` §13.1 and §C.

The consequence matters more than the outage: when generation fails, the lesson
path **downgrades to a deterministic heuristic payload and still returns `201`
with a persisted lesson** (`lesson_generation_ai_failed_using_heuristic`). A demo
can therefore look successful while showing non-AI content. Grounded lesson
persistence through live Gemini is **unverified**.

Deploying with `AI_PROVIDER=local` is **not** an option: it is
`LocalMockProvider`, a deterministic test double that never emits a
`LessonPayload`, so every lesson ends up `failed`. Configure a real provider —
`AI_PROVIDER=gemini` matches how the app was developed and tested. Switching
providers is configuration only, with no code change, but must be reported as
`EXTERNAL LIMITATION` until a real grounded lesson is observed persisting end to
end.

### Why not `AI_PROVIDER=local` for a "deterministic" demo?

Verified against the running production stack, not assumed. `local` is documented
in-source as *"Deterministic local mock provider (no external calls)"*
(`backend/app/ai/providers/local.py:41`). It returns a 13-token stub, so:

```text
LessonGenerationParseError: model returned an unparsable payload:
1 validation error for LessonPayload
title
  Field required [input_value={'digest': 'efa520e0...', 'provider': 'local'}]
```

The task retries three times at a 60s backoff and the lesson is marked
`failed`. Health endpoints still report `healthy` throughout, so this failure is
invisible from `/health` — it is only visible in the worker logs and in
`GET /api/v1/presentations/{id}/lessons/{lesson_id}/status`. That is precisely
why Step 6 requires creating a lesson, not just pinging health.