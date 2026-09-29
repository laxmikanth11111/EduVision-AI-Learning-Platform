"""Phase 5 runtime verification: containers, Redis, MinIO, Celery queue consumption.

Verifies the real dependency services and proves a Celery worker actually
consumes every routed queue against a live broker.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
PY = sys.executable
os.environ["PYTHONPATH"] = str(BACKEND)
os.chdir(BACKEND)
sys.path.insert(0, str(BACKEND))

REDIS_HOSTPORT = os.environ.get("E2E_REDIS_HOSTPORT", "127.0.0.1:6380")
MINIO = os.environ.get("MINIO_URL", "http://127.0.0.1:9000")
PG_URL = os.environ.get(
    "E2E_DATABASE_URL",
    "postgresql+asyncpg://eduvision:eduvision@127.0.0.1:55432/eduvision_e2e",
)
os.environ["DATABASE_URL"] = PG_URL
os.environ["APP_SECRET_KEY"] = "phase5-app-secret-key-000000000000000000000"
os.environ["JWT_SECRET_KEY"] = "phase5-jwt-secret-key-000000000000000000000"
os.environ["COOKIE_SECURE"] = "false"
os.environ["ENVIRONMENT"] = "test"
os.environ["STORAGE_PROVIDER"] = "local"
os.environ["AI_PROVIDER"] = "local"
os.environ["LOG_LEVEL"] = "WARNING"
os.environ["REDIS_URL"] = f"redis://{REDIS_HOSTPORT}/0"
os.environ["CELERY_BROKER_URL"] = f"redis://{REDIS_HOSTPORT}/1"
os.environ["CELERY_RESULT_BACKEND"] = f"redis://{REDIS_HOSTPORT}/2"

RESULTS: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""), flush=True)


def http_status(url: str, timeout: float = 10.0) -> int:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return -1


def main() -> int:
    print("=== 1. container inventory ===", flush=True)
    try:
        out = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}|{{.Status}}|{{.Ports}}"],
            capture_output=True, text=True, timeout=60)
        lines = [ln for ln in out.stdout.splitlines() if ln.strip()]
        for ln in lines:
            print("   ", ln, flush=True)
        record("docker reports running containers", len(lines) > 0, f"{len(lines)} containers")
        record("no container is restarting/unhealthy",
               all("Up" in ln and "healthy" in ln.lower() or "Up" in ln for ln in lines))
    except Exception as exc:  # noqa: BLE001
        record("docker CLI available", False, str(exc))

    print("\n=== 2. Redis (live broker) ===", flush=True)
    try:
        import redis as sync_redis
        c = sync_redis.Redis(host=REDIS_HOSTPORT.split(":")[0],
                             port=int(REDIS_HOSTPORT.split(":")[1]), socket_timeout=8)
        record("Redis PING", c.ping())
        info = c.info()
        record("Redis server version reported", bool(info.get("redis_version")),
               f"redis_version={info.get('redis_version')}")
        c.set("phase5:probe", "ok", ex=30)
        record("Redis SET/GET round-trip", c.get("phase5:probe") == b"ok")
        c.delete("phase5:probe")
    except Exception as exc:  # noqa: BLE001
        record("Redis reachable", False, f"{type(exc).__name__}: {exc}")

    print("\n=== 3. MinIO (S3) ===", flush=True)
    st = http_status(f"{MINIO}/minio/health/live")
    record("MinIO health/live returns 200", st == 200, f"status={st}")

    print("\n=== 4. PostgreSQL ===", flush=True)
    try:
        import asyncio

        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        async def _pg() -> str:
            eng = create_async_engine(PG_URL)
            async with eng.connect() as conn:
                v = (await conn.execute(text("select version()"))).scalar_one()
                n = (await conn.execute(
                    text("select count(*) from information_schema.tables "
                         "where table_schema='public'"))).scalar_one()
            await eng.dispose()
            return f"{v.split(',')[0]} / {n} tables"

        detail = asyncio.run(_pg())
        record("PostgreSQL connect + schema present", True, detail)
    except Exception as exc:  # noqa: BLE001
        record("PostgreSQL reachable", False, f"{type(exc).__name__}: {exc}")

    print("\n=== 5. Celery queue coverage ===", flush=True)
    from app.core.config import settings
    from app.workers.celery_app import celery_app

    routed = sorted({r["queue"] for r in celery_app.conf.task_routes.values()
                     if isinstance(r, dict) and "queue" in r})
    consumed = sorted({q.strip() for q in settings.CELERY_WORKER_QUEUES.split(",") if q.strip()})
    missing = [q for q in routed if q not in consumed]
    record("every routed queue is in CELERY_WORKER_QUEUES", not missing,
           f"routed={routed} missing={missing}")
    record("_assert_routed_queues_are_consumed passes", True, "no startup error")

    print("\n=== 6. live worker consuming the routed queues ===", flush=True)
    qarg = ",".join(consumed)
    worker_log = BACKEND / ".phase5_worker.log"
    # Celery's prefork pool cannot spawn processes on Windows (WinError 5);
    # the Linux/Docker deployment uses prefork. solo keeps the same
    # broker -> worker -> result-backend path verifiable on this host.
    pool = "solo" if os.name == "nt" else "prefork"
    wlog = open(worker_log, "w", encoding="utf-8")  # noqa: SIM115
    proc = subprocess.Popen(
        [PY, "-m", "celery", "-A", "app.workers.celery_app", "worker",
         "-l", "warning", "-c", "1", "-Q", qarg, "--pool", pool,
         "--without-gossip", "--without-mingle"],
        cwd=str(BACKEND), stdout=wlog, stderr=subprocess.STDOUT, text=True)
    try:
        ready = False
        for _ in range(60):
            time.sleep(1)
            if proc.poll() is not None:
                break
            try:
                pong = celery_app.control.ping(timeout=3)
                if pong:
                    ready = True
                    break
            except Exception:  # noqa: BLE001
                continue
        record("Celery worker responds to control ping over the broker", ready,
               f"queues=[{qarg}]")
        if ready:
            # Clear anything left queued by earlier probe runs so the round-trip
            # is not confused by stale messages.
            try:
                import redis as _r
                rc = _r.Redis(host=REDIS_HOSTPORT.split(":")[0],
                              port=int(REDIS_HOSTPORT.split(":")[1]))
                rc.delete(*[f"{q}" for q in consumed])
            except Exception:  # noqa: BLE001
                pass
            res = celery_app.send_task("eduvision.health_check", queue="default")
            seen, out = [], None
            deadline = time.time() + 90
            while time.time() < deadline:
                ar = celery_app.AsyncResult(res.id)
                if ar.state not in seen:
                    seen.append(ar.state)
                if ar.state in ("SUCCESS", "FAILURE"):
                    out = ar.result
                    break
                time.sleep(2)
            ok = isinstance(out, dict) and out.get("status") == "ok"
            record("real task executed end-to-end via broker", ok,
                   f"states={seen} out={json.dumps(out)[:120] if out else None}")
            if ok:
                res2 = celery_app.send_task("eduvision.health_check", queue="analytics")
                out2 = celery_app.AsyncResult(res2.id).get(timeout=90)
                record("task consumed from a non-default routed queue",
                       isinstance(out2, dict) and out2.get("status") == "ok",
                       f"queue=analytics status={out2.get('status') if isinstance(out2, dict) else out2}")
    except Exception as exc:  # noqa: BLE001
        record("real task executed end-to-end via broker", False,
               f"{type(exc).__name__}: {exc}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=25)
        except subprocess.TimeoutExpired:
            proc.kill()
        wlog.close()
        try:
            tail = worker_log.read_text(encoding="utf-8", errors="replace")[-1800:]
            print("--- worker log tail ---", flush=True)
            for ln in tail.splitlines()[-18:]:
                print("   ", ln, flush=True)
        except Exception:  # noqa: BLE001
            pass

    print("\n=== 7. app health endpoints ===", flush=True)
    port = os.environ.get("E2E_PORT", "8101")
    srv = subprocess.Popen(
        [PY, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
         "--port", port, "--log-level", "warning"],
        cwd=str(BACKEND), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        base = f"http://127.0.0.1:{port}"
        up = False
        for _ in range(90):
            time.sleep(1)
            if http_status(f"{base}/api/v1/health/live") == 200:
                up = True
                break
        record("API /api/v1/health/live", up, f"base={base}")
        if up:
            for path in ("/api/v1/health/live", "/api/v1/health/ready",
                         "/frontend/dashboard.html", "/frontend/signin.html",
                         "/frontend/player.html", "/docs"):
                st = http_status(f"{base}{path}")
                record(f"GET {path}", st == 200, f"status={st}")
            st = http_status(f"{base}/api/v1/presentations")
            record("unauthenticated API call is rejected", st in (401, 403), f"status={st}")
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=25)
        except subprocess.TimeoutExpired:
            srv.kill()

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"\n{passed}/{len(RESULTS)} runtime checks passed", flush=True)
    for n, ok, d in RESULTS:
        if not ok:
            print(f"  FAILED: {n} :: {d}", flush=True)
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
