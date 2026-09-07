"""Checkpoint C3.4 - Real-mode auto-trigger verification.

Proves that upload -> extraction -> C2 topic regeneration automatically
dispatches and completes C3 visual generation WITHOUT any manual call to the
C3 generation endpoint (``POST /api/v1/c3/visuals/generate``).

The script only performs the standard user flow:
  1. register/login
  2. create presentation
  3. upload source PPTX
  4. wait for extraction
  5. POST /topics/regenerate  (the C2 user action)

It NEVER calls the C3 endpoint. It then polls the C3 read-only list endpoint,
expecting assets to appear and reach ``ready`` purely via the auto-trigger,
and finally collects worker-log evidence of the dispatcher line and task
start/completion lines.
"""

import asyncio
import os
import sys
import uuid

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import httpx

BASE_URL = "http://127.0.0.1:8000"
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PPTX_PATH = os.path.join(BACKEND_DIR, "tests", "fixtures", "computer_networks_sample.pptx")
LOG_DIR = os.path.join(BACKEND_DIR, "logs")
C3_ENDPOINT = "/api/v1/c3/visuals/generate"


async def _poll_until(pred, timeout: float, desc: str, interval: float = 2.0):
    import time

    start = time.monotonic()
    while time.monotonic() - start < timeout:
        value = await pred()
        if value:
            return value
        await asyncio.sleep(interval)
    raise TimeoutError(f"Timed out waiting for: {desc}")


async def run_c3_autotrigger_verification():
    print("=== C3.4 REAL-MODE AUTO-TRIGGER VERIFICATION (no manual C3 call) ===")
    if not os.path.exists(PPTX_PATH):
        raise FileNotFoundError(f"PPTX fixture missing: {PPTX_PATH}")

    email = f"c3auto_{uuid.uuid4().hex[:6]}@example.com"
    password = "StudentPassword123!"

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=90.0) as client:
        # 1. Register + login
        await client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": password,
                "name": "C3 Auto-Trigger Student",
            },
        )
        login_res = await client.post(
            "/api/v1/auth/login",
            json={
                "email": email,
                "password": password,
            },
        )
        if login_res.status_code != 200:
            raise RuntimeError(f"Login failed: {login_res.text[:300]}")
        login_data = login_res.json()
        tokens = login_data.get("tokens") or login_data.get("data", {}).get("tokens")
        token = tokens["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print(f"[1] Registered + logged in as {email}")

        # 2. Create presentation
        pres_res = await client.post(
            "/api/v1/presentations",
            json={
                "title": "C3 Auto-Trigger Deck",
            },
            headers=headers,
        )
        if pres_res.status_code != 201:
            raise RuntimeError(f"Create presentation failed: {pres_res.text}")
        pres_id = pres_res.json()["data"]["id"]
        print(f"[2] Created presentation: {pres_id}")

        # 3. Upload source PPTX
        with open(PPTX_PATH, "rb") as f:
            file_bytes = f.read()
        upload_res = await client.post(
            f"/api/v1/presentations/{pres_id}/source",
            files={
                "source": (
                    "computer_networks_sample.pptx",
                    file_bytes,
                    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                )
            },
            headers=headers,
        )
        if upload_res.status_code != 200:
            raise RuntimeError(f"Source upload failed: {upload_res.text}")
        print("[3] Uploaded PPTX source file")

        # Baseline: no C3 assets may exist right after upload + extraction
        async def _list_assets():
            r = await client.get(f"/api/v1/c3/visuals/presentation/{pres_id}", headers=headers)
            if r.status_code == 200:
                return r.json().get("data", [])
            return None

        await _poll_until(
            lambda: _extraction_ready(client, pres_id, headers),
            timeout=180,
            desc="extraction ready",
        )
        print("[4] Extraction completed: ready")

        pre_assets = await _list_assets()
        assert pre_assets is not None, "expected a list response from C3 asset endpoint"
        assert len(pre_assets) == 0, (
            f"C3 assets must be absent before topic regeneration, got {len(pre_assets)}"
        )
        print("[5] Baseline: 0 C3 assets before C2 regeneration (upload alone does not generate)")

        # 4. The only user-facing C2 action: regenerate the topic outline.
        regen_res = await client.post(
            f"/api/v1/presentations/{pres_id}/topics/regenerate", headers=headers
        )
        if regen_res.status_code != 200:
            raise RuntimeError(f"Topics regenerate failed: {regen_res.text}")
        outline_status = regen_res.json().get("data", {}).get("status")
        print(f"[6] C2 topic outline regenerated (status={outline_status})")

        # 5. Poll the READ-ONLY list endpoint; the auto-trigger must create assets.
        await _poll_until(
            lambda: _assets_present(client, pres_id, headers),
            timeout=150,
            desc="auto-triggered C3 assets to appear",
        )
        print("[7] C3 assets appeared automatically after C2 regeneration (no manual C3 call)")

        # 6. Wait until at least one asset reaches 'ready'.
        ready = await _poll_until(
            lambda: _ready_assets(client, pres_id, headers),
            timeout=180,
            desc="at least one ready C3 visual",
        )
        print(f"[8] Ready C3 visuals: {len(ready)}")

        # 7. Verify SVG retrievable for a ready asset
        first = ready[0]
        asset_id = first.get("id") or first.get("asset_id")
        svg_res = await client.get(f"/api/v1/c3/visuals/{asset_id}/svg", headers=headers)
        if svg_res.status_code != 200 or "<svg" not in svg_res.text:
            raise RuntimeError(f"SVG endpoint failed: {svg_res.status_code}")
        print(f"[9] SVG endpoint returned valid SVG for asset {asset_id}: PASSED")

        dl_res = await client.get(f"/api/v1/c3/visuals/{asset_id}/download", headers=headers)
        if dl_res.status_code != 200 or "<svg" not in dl_res.text:
            raise RuntimeError(f"Download endpoint failed: {dl_res.status_code}")
        print(f"[10] Download endpoint returned {len(dl_res.text)} bytes of SVG: PASSED")

    # 8. Worker / API log evidence of the auto-trigger lifecycle
    log_evidence = _collect_log_evidence()
    for line in log_evidence:
        print(f"     LOG: {line}")

    assert any("c3_generate_visuals_task_started" in line for line in log_evidence), (
        "celery log must show c3_generate_visuals_task_started"
    )
    assert any("c3_generate_visuals_task_completed" in line for line in log_evidence), (
        "celery log must show c3_generate_visuals_task_completed"
    )
    assert any("c3_skipped_no_outline" in line for line in log_evidence), (
        "celery log must show the upload-time trigger correctly no-oping before C2"
    )

    # Correlation proof: the C3 task's request_id must match the request_id of the
    # /topics/regenerate API call, proving the task was dispatched from that request
    # (i.e. the auto-trigger), not from a manual C3 endpoint call.
    api_requests, regen_requests, c3_generate_requests = _correlation_evidence()
    print(f"     API request lines for presentation: {len(api_requests)}")
    for line in api_requests:
        print(f"     API: {line}")
    assert len(regen_requests) == 1, (
        f"expected exactly one /topics/regenerate request, got {len(regen_requests)}"
    )
    assert len(c3_generate_requests) == 0, (
        "no request to POST /api/v1/c3/visuals/generate may exist in the API log"
    )
    started_line = next(line for line in log_evidence if "c3_generate_visuals_task_started" in line)
    regen_line = regen_requests[0]
    task_request_id = _extract_request_id(started_line)
    regen_request_id = _extract_request_id(regen_line)
    print(f"     C3 task request_id: {task_request_id}")
    print(f"     /topics/regenerate request_id: {regen_request_id}")
    assert task_request_id, "C3 task started log must carry a request_id"
    assert task_request_id == regen_request_id, (
        "C3 task request_id must match the /topics/regenerate request_id"
    )

    print("[11] Worker lifecycle log evidence (started -> completed): PASSED")
    print("[12] Correlation: C3 task dispatched from /topics/regenerate request: PASSED")
    print("[13] No call to POST /api/v1/c3/visuals/generate observed in API logs: PASSED")

    print("\n====================================================================")
    print("=== C3.4 AUTO-TRIGGER VERIFICATION: ALL PASSED (100%) ===")
    print("====================================================================")


async def _extraction_ready(client, pres_id, headers):
    r = await client.get(f"/api/v1/presentations/{pres_id}/processing-status", headers=headers)
    return r.status_code == 200 and r.json()["data"]["extraction_status"] == "ready"


async def _assets_present(client, pres_id, headers):
    r = await client.get(f"/api/v1/c3/visuals/presentation/{pres_id}", headers=headers)
    if r.status_code == 200:
        data = r.json().get("data", []) or []
        return data if len(data) > 0 else None
    return None


async def _ready_assets(client, pres_id, headers):
    r = await client.get(f"/api/v1/c3/visuals/presentation/{pres_id}/ready", headers=headers)
    if r.status_code == 200:
        data = r.json().get("data", []) or []
        return data if len(data) > 0 else None
    return None


def _collect_log_evidence() -> list[str]:
    needles = [
        "c3_generate_visuals_task_started",
        "c3_generate_visuals_task_completed",
        "c3_skipped_no_outline",
    ]
    seen: list[str] = []
    files = [
        os.path.join(LOG_DIR, "celery.out.log"),
        os.path.join(LOG_DIR, "celery.err.log"),
    ]
    for path in files:
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                low = line.lower()
                for n in needles:
                    if n in low:
                        seen.append(line.rstrip())
    return seen[-12:]


def _correlation_evidence() -> tuple[list[str], list[str], list[str]]:
    """Return (api_request_lines, regenerate_lines, c3_generate_request_lines)."""
    api_lines: list[str] = []
    regen_lines: list[str] = []
    c3_manual_lines: list[str] = []
    files = [
        os.path.join(LOG_DIR, "uvicorn.err.log"),
        os.path.join(LOG_DIR, "uvicorn.out.log"),
    ]
    for path in files:
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if "topics/regenerate" not in line and "/api/v1/c3" not in line:
                    continue
                if "topics/regenerate" in line:
                    regen_lines.append(line.rstrip())
                    api_lines.append(line.rstrip())
                if '"/api/v1/c3/visuals/generate"' in line or "c3/visuals/generate" in line:
                    c3_manual_lines.append(line.rstrip())
                    api_lines.append(line.rstrip())
    return api_lines, regen_lines, c3_manual_lines


def _extract_request_id(line: str) -> str | None:
    import re

    m = re.search(r"request_id=([0-9a-f-]+)", line)
    if m:
        return m.group(1)
    m = re.search(r'"request_id":\s*"([0-9a-f-]+)"', line)
    if m:
        return m.group(1)
    return None


if __name__ == "__main__":
    asyncio.run(run_c3_autotrigger_verification())
