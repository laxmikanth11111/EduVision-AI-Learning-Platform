"""Unit & Integration Tests for Phase 4I.3 Visual Knowledge Graph REST Endpoints.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.unit_of_work import UnitOfWork, get_unit_of_work
from app.main import app


@pytest.mark.asyncio
async def test_visual_canvas_api_crud_flow(
    client: AsyncClient,
    db_session: AsyncSession,
):
    """Test POST, GET, PUT, DELETE, and nested resource endpoints on /api/v1/visual/canvases."""

    async def _get_uow_override():
        yield UnitOfWork(session=db_session)

    app.dependency_overrides[get_unit_of_work] = _get_uow_override

    try:
        # 1. Create Canvas
        create_payload = {
            "content": "Central Processing Unit CPU fetches instructions from RAM, decodes in Control Unit, and executes in ALU.",
            "title": "CPU Architecture Graph",
        }
        response = await client.post("/api/v1/visual/canvases", json=create_payload)
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        canvas_id = data["data"]["canvas_id"]
        assert canvas_id is not None

        # 2. Get Full Canvas Graph
        get_res = await client.get(f"/api/v1/visual/canvases/{canvas_id}")
        assert get_res.status_code == 200
        graph_data = get_res.json()["data"]
        assert graph_data["topic"] == "CPU Architecture Graph"
        assert len(graph_data["components"]) > 0
        assert len(graph_data["visual_nodes"]) > 0

        # 3. Get Nodes Endpoint
        nodes_res = await client.get(f"/api/v1/visual/canvases/{canvas_id}/nodes")
        assert nodes_res.status_code == 200
        assert len(nodes_res.json()["data"]) > 0

        # 4. Get Edges Endpoint
        edges_res = await client.get(f"/api/v1/visual/canvases/{canvas_id}/edges")
        assert edges_res.status_code == 200

        # 5. Get Components Metadata Endpoint
        comp_res = await client.get(f"/api/v1/visual/canvases/{canvas_id}/components")
        assert comp_res.status_code == 200
        assert len(comp_res.json()["data"]) > 0

        # 6. Get Relationships Endpoint
        rel_res = await client.get(f"/api/v1/visual/canvases/{canvas_id}/relationships")
        assert rel_res.status_code == 200

        # 7. Get Quiz Blueprint Endpoint
        quiz_res = await client.get(f"/api/v1/visual/canvases/{canvas_id}/quiz-blueprint")
        assert quiz_res.status_code == 200
        assert "quiz_focus_areas" in quiz_res.json()["data"]

        # 8. Update Canvas Endpoint
        update_res = await client.put(
            f"/api/v1/visual/canvases/{canvas_id}",
            json={"title": "Updated CPU Graph Title", "is_published": True},
        )
        assert update_res.status_code == 200
        assert update_res.json()["data"]["title"] == "Updated CPU Graph Title"

        # 9. Delete Canvas Endpoint
        del_res = await client.delete(f"/api/v1/visual/canvases/{canvas_id}")
        assert del_res.status_code == 204
    finally:
        app.dependency_overrides.pop(get_unit_of_work, None)


@pytest.mark.asyncio
async def test_visual_canvas_single_get_and_list_coexist(
    client: AsyncClient,
    db_session: AsyncSession,
):
    """The query-param list route must not shadow GET /visual/canvases/{canvas_id}."""

    async def _get_uow_override():
        yield UnitOfWork(session=db_session)

    app.dependency_overrides[get_unit_of_work] = _get_uow_override
    try:
        create_res = await client.post(
            "/api/v1/visual/canvases",
            json={"content": "Neural network layers: input, hidden, output.", "title": "NN Graph"},
        )
        assert create_res.status_code == 201
        canvas_id = create_res.json()["data"]["canvas_id"]

        single_res = await client.get(f"/api/v1/visual/canvases/{canvas_id}")
        assert single_res.status_code == 200
        assert single_res.json()["data"]["topic"] == "NN Graph"

        list_res = await client.get("/api/v1/visual/canvases")
        assert list_res.status_code == 200
        assert any(c["canvas_id"] == canvas_id for c in list_res.json()["data"])
    finally:
        app.dependency_overrides.pop(get_unit_of_work, None)


@pytest.mark.asyncio
async def test_visual_canvas_create_immediately_readable(
    client: AsyncClient,
    db_session: AsyncSession,
):
    """Regression: POST /visual/canvases must commit before responding so the
    immediate read-back of /nodes, /edges and /components can never observe a
    missing canvas. This protects the create→immediate-read transaction
    invariant (production teardown-commit race, same class as the auth
    register fix). The ASGI test transport does not reproduce the original
    production teardown timing; it locks the required application invariant.
    """

    async def _get_uow_override():
        yield UnitOfWork(session=db_session)

    app.dependency_overrides[get_unit_of_work] = _get_uow_override

    try:
        create_res = await client.post(
            "/api/v1/visual/canvases",
            json={
                "content": (
                    "Photosynthesis converts light energy into chemical "
                    "energy stored in glucose."
                ),
                "title": "Immediate Readback Graph",
            },
        )
        assert create_res.status_code == 201
        data = create_res.json()["data"]
        canvas_id = data["canvas_id"]
        assert canvas_id

        nodes_res = await client.get(f"/api/v1/visual/canvases/{canvas_id}/nodes")
        assert nodes_res.status_code == 200
        assert len(nodes_res.json()["data"]) > 0

        edges_res = await client.get(f"/api/v1/visual/canvases/{canvas_id}/edges")
        assert edges_res.status_code == 200

        comps_res = await client.get(f"/api/v1/visual/canvases/{canvas_id}/components")
        assert comps_res.status_code == 200
        assert len(comps_res.json()["data"]) > 0
    finally:
        app.dependency_overrides.pop(get_unit_of_work, None)
