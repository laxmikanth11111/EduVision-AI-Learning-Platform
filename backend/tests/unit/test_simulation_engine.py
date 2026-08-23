"""Unit Tests for Phase 4I.5 Dynamic Simulation Engine & Interactive Learning Runtime.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.simulation_runtime import PlaybackState
from app.services.simulation_engine_service import SimulationEngineService
from app.services.simulation_registry_service import simulation_registry


def test_simulation_registry_definitions():
    """Verify registry contains standard registered definitions."""
    sims = simulation_registry.list_simulations()
    assert len(sims) >= 2
    cpu_sim = simulation_registry.get_simulation("sim_cpu_fetch_execute")
    assert cpu_sim is not None
    assert cpu_sim.topic == "CPU Von Neumann Fetch-Execute Cycle"
    assert len(cpu_sim.steps) == 4
    assert len(cpu_sim.checkpoints) == 2


def test_simulation_engine_state_transitions():
    """Verify simulation engine state machine step transitions and checkpoints."""
    engine = SimulationEngineService()
    def_obj, state = engine.start_session("sim_cpu_fetch_execute")
    sess_id = list(engine._sessions.keys())[-1]

    assert state.current_step_index == 0
    assert state.playback_state == PlaybackState.PAUSED

    # Step forward
    def_obj, state = engine.step_next(sess_id)
    assert state.current_step_index == 1
    assert len(state.completed_checkpoints) == 1
    assert "chk_fetch" in state.completed_checkpoints

    # Update Parameters
    def_obj, state = engine.update_parameters(sess_id, {"clock_frequency_mhz": 2.5})
    assert state.parameters["clock_frequency_mhz"] == 2.5

    # Jump to Step 2
    def_obj, state = engine.jump_to_step(sess_id, 2)
    assert state.current_step_index == 2

    # Step to completion
    def_obj, state = engine.step_next(sess_id)
    assert state.current_step_index == 3
    assert state.playback_state == PlaybackState.COMPLETED
    assert "chk_alu" in state.completed_checkpoints

    # Reset
    def_obj, state = engine.reset_session(sess_id)
    assert state.current_step_index == 0
    assert len(state.completed_checkpoints) == 0


@pytest.mark.asyncio
async def test_simulation_api_endpoints(
    client: AsyncClient,
    db_session: AsyncSession,
):
    # 1. List Definitions
    list_res = await client.get("/api/v1/simulations/definitions")
    assert list_res.status_code == 200
    assert len(list_res.json()["data"]) >= 2

    # 2. Get Definition Details
    get_res = await client.get("/api/v1/simulations/definitions/sim_cpu_fetch_execute")
    assert get_res.status_code == 200
    assert get_res.json()["data"]["topic"] == "CPU Von Neumann Fetch-Execute Cycle"

    # 3. Start Session
    start_res = await client.post(
        "/api/v1/simulations/sessions/start",
        json={"simulation_id": "sim_cpu_fetch_execute"},
    )
    assert start_res.status_code == 201
    sess_data = start_res.json()["data"]
    assert sess_data["state"]["current_step_index"] == 0
