"""API Router for Dynamic Simulation Engine & Runtime (Phase 4I.5).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel

from app.core.dependencies import get_current_user
from app.core.exceptions import NotFoundError
from app.models.user import User
from app.schemas.simulation_runtime import PlaybackState
from app.services.simulation_engine_service import simulation_engine
from app.services.simulation_registry_service import simulation_registry

simulation_router = APIRouter(prefix="/simulations", tags=["Simulation Runtime"])


class StartSimulationRequest(BaseModel):
    simulation_id: str
    initial_parameters: dict[str, Any] | None = None


class StepActionRequest(BaseModel):
    action: str  # "next", "prev", "jump"
    step_index: int | None = None


class ParameterUpdateRequest(BaseModel):
    parameters: dict[str, Any]


class PlaybackControlRequest(BaseModel):
    playback_state: PlaybackState | None = None
    speed: float | None = None


@simulation_router.get(
    "/definitions",
    summary="List available simulation definitions",
)
async def list_simulation_definitions(
    category: str | None = Query(default=None),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    definitions = simulation_registry.list_simulations(category=category)
    return {
        "success": True,
        "data": [d.model_dump() for d in definitions],
    }


@simulation_router.get(
    "/definitions/{simulation_id}",
    summary="Fetch a specific simulation definition by ID",
)
async def get_simulation_definition(
    simulation_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    definition = simulation_registry.get_simulation(simulation_id)
    if not definition:
        raise NotFoundError(message="Definition not found")
    return {"success": True, "data": definition.model_dump()}


@simulation_router.post(
    "/sessions/start",
    status_code=status.HTTP_201_CREATED,
    summary="Start a new interactive simulation runtime session",
)
async def start_simulation_session(
    req: StartSimulationRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    definition, state = simulation_engine.start_session(
        req.simulation_id, initial_parameters=req.initial_parameters, owner_id=str(user.id)
    )
    return {
        "success": True,
        "data": {
            "session_id": state.session_id,
            "definition": definition.model_dump(),
            "state": state.model_dump(),
        },
    }


@simulation_router.get(
    "/sessions/{session_id}",
    summary="Get current state of a simulation runtime session",
)
async def get_simulation_session(
    session_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    definition, state = simulation_engine.get_session_state(session_id, owner_id=str(user.id))
    return {
        "success": True,
        "data": {
            "definition": definition.model_dump(),
            "state": state.model_dump(),
        },
    }


@simulation_router.post(
    "/sessions/{session_id}/step",
    summary="Step forward, backward, or jump to specific step index",
)
async def step_simulation(
    session_id: str,
    req: StepActionRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    if req.action == "next":
        definition, state = simulation_engine.step_next(session_id, owner_id=str(user.id))
    elif req.action == "prev":
        definition, state = simulation_engine.step_prev(session_id, owner_id=str(user.id))
    elif req.action == "jump" and req.step_index is not None:
        definition, state = simulation_engine.jump_to_step(session_id, req.step_index, owner_id=str(user.id))
    else:
        return {"success": False, "error": "Invalid step action"}

    return {
        "success": True,
        "data": {
            "definition": definition.model_dump(),
            "state": state.model_dump(),
        },
    }


@simulation_router.post(
    "/sessions/{session_id}/parameters",
    summary="Update live simulation parameters",
)
async def update_simulation_parameters(
    session_id: str,
    req: ParameterUpdateRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    definition, state = simulation_engine.update_parameters(session_id, req.parameters, owner_id=str(user.id))
    return {
        "success": True,
        "data": {
            "definition": definition.model_dump(),
            "state": state.model_dump(),
        },
    }


@simulation_router.post(
    "/sessions/{session_id}/playback",
    summary="Update playback state (play/pause) or speed",
)
async def control_simulation_playback(
    session_id: str,
    req: PlaybackControlRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    definition, state = simulation_engine.set_playback_controls(
        session_id, playback_state=req.playback_state, speed=req.speed, owner_id=str(user.id)
    )
    return {
        "success": True,
        "data": {
            "definition": definition.model_dump(),
            "state": state.model_dump(),
        },
    }


@simulation_router.post(
    "/sessions/{session_id}/reset",
    summary="Reset simulation runtime session to step 0",
)
async def reset_simulation_session(
    session_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    definition, state = simulation_engine.reset_session(session_id, owner_id=str(user.id))
    return {
        "success": True,
        "data": {
            "definition": definition.model_dump(),
            "state": state.model_dump(),
        },
    }
