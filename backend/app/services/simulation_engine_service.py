"""Dynamic Simulation Runtime Engine (Phase 4I.5).

Generic, stateful runtime managing simulation execution, state transitions, parameter inputs,
checkpoints, events, and hooks for Quiz/Tutor subsystems.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from app.core.exceptions import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.schemas.simulation_runtime import (
    PlaybackState,
    SimulationDefinition,
    SimulationState,
)
from app.services.simulation_registry_service import simulation_registry

logger = get_logger(__name__)


class SimulationEngineService:

    def __init__(self) -> None:
        self._sessions: dict[str, SimulationState] = {}
        self._definitions: dict[str, SimulationDefinition] = {}
        self._session_owners: dict[str, str] = {}

    def _assert_owner(self, session_id: str, owner_id: str) -> None:
        stored = self._session_owners.get(session_id)
        if stored is None:
            raise NotFoundError(message="Simulation session not found", details={"session_id": session_id})
        if stored != owner_id:
            raise NotFoundError(message="Simulation session not found", details={"session_id": session_id})

    def start_session(
        self,
        simulation_id: str,
        initial_parameters: dict[str, Any] | None = None,
        *,
        owner_id: str | None = None,
    ) -> tuple[SimulationDefinition, SimulationState]:
        definition = simulation_registry.get_simulation(simulation_id)
        if not definition:
            raise NotFoundError(
                message="Simulation definition not found",
                details={"simulation_id": simulation_id},
            )

        session_id = f"simsess_{uuid.uuid4().hex[:16]}"
        param_dict: dict[str, Any] = {
            p.parameter_id: p.current_value if p.current_value is not None else p.default_value
            for p in definition.parameters
        }
        if initial_parameters:
            param_dict.update(initial_parameters)

        state = SimulationState(
            session_id=session_id,
            simulation_id=simulation_id,
            current_step_index=0,
            playback_state=PlaybackState.PAUSED,
            playback_speed=1.0,
            parameters=param_dict,
            completed_checkpoints=[],
            event_logs=[
                {
                    "event_type": "sim_started",
                    "timestamp": time.time(),
                    "step_index": 0,
                    "details": {"topic": definition.topic},
                }
            ],
        )

        self._sessions[session_id] = state
        self._definitions[session_id] = definition
        if owner_id is not None:
            self._session_owners[session_id] = owner_id

        logger.info("simulation_session_started", session_id=session_id, simulation_id=simulation_id)
        return definition, state

    def get_session_state(self, session_id: str, *, owner_id: str | None = None) -> tuple[SimulationDefinition, SimulationState]:
        if owner_id is not None:
            self._assert_owner(session_id, owner_id)
        if session_id not in self._sessions:
            raise NotFoundError(message="Simulation session not found", details={"session_id": session_id})
        return self._definitions[session_id], self._sessions[session_id]

    def step_next(self, session_id: str, *, owner_id: str | None = None) -> tuple[SimulationDefinition, SimulationState]:
        definition, state = self.get_session_state(session_id, owner_id=owner_id)
        if state.current_step_index < len(definition.steps) - 1:
            state.current_step_index += 1
            self._evaluate_checkpoints(definition, state)
            state.event_logs.append(
                {
                    "event_type": "step_changed",
                    "timestamp": time.time(),
                    "step_index": state.current_step_index,
                    "step_id": definition.steps[state.current_step_index].step_id,
                }
            )

        if state.current_step_index == len(definition.steps) - 1:
            state.playback_state = PlaybackState.COMPLETED
            state.event_logs.append(
                {
                    "event_type": "sim_completed",
                    "timestamp": time.time(),
                    "step_index": state.current_step_index,
                }
            )

        return definition, state

    def step_prev(self, session_id: str, *, owner_id: str | None = None) -> tuple[SimulationDefinition, SimulationState]:
        definition, state = self.get_session_state(session_id, owner_id=owner_id)
        if state.current_step_index > 0:
            state.current_step_index -= 1
            state.event_logs.append(
                {
                    "event_type": "step_changed",
                    "timestamp": time.time(),
                    "step_index": state.current_step_index,
                    "step_id": definition.steps[state.current_step_index].step_id,
                }
            )
        return definition, state

    def jump_to_step(self, session_id: str, step_index: int, *, owner_id: str | None = None) -> tuple[SimulationDefinition, SimulationState]:
        definition, state = self.get_session_state(session_id, owner_id=owner_id)
        if step_index < 0 or step_index >= len(definition.steps):
            raise ValidationError(
                message="Invalid step index",
                details={"step_index": step_index, "max": len(definition.steps) - 1},
            )

        state.current_step_index = step_index
        self._evaluate_checkpoints(definition, state)
        state.event_logs.append(
            {
                "event_type": "step_jumped",
                "timestamp": time.time(),
                "step_index": step_index,
            }
        )
        return definition, state

    def update_parameters(
        self, session_id: str, new_parameters: dict[str, Any], *, owner_id: str | None = None,
    ) -> tuple[SimulationDefinition, SimulationState]:
        definition, state = self.get_session_state(session_id, owner_id=owner_id)
        state.parameters.update(new_parameters)
        state.event_logs.append(
            {
                "event_type": "parameter_changed",
                "timestamp": time.time(),
                "step_index": state.current_step_index,
                "parameters": new_parameters,
            }
        )
        return definition, state

    def set_playback_controls(
        self,
        session_id: str,
        playback_state: PlaybackState | None = None,
        speed: float | None = None,
        *,
        owner_id: str | None = None,
    ) -> tuple[SimulationDefinition, SimulationState]:
        definition, state = self.get_session_state(session_id, owner_id=owner_id)
        if playback_state is not None:
            state.playback_state = playback_state
        if speed is not None:
            state.playback_speed = max(0.25, min(4.0, speed))

        state.event_logs.append(
            {
                "event_type": "playback_updated",
                "timestamp": time.time(),
                "playback_state": state.playback_state.value,
                "speed": state.playback_speed,
            }
        )
        return definition, state

    def reset_session(self, session_id: str, *, owner_id: str | None = None) -> tuple[SimulationDefinition, SimulationState]:
        definition, state = self.get_session_state(session_id, owner_id=owner_id)
        state.current_step_index = 0
        state.playback_state = PlaybackState.PAUSED
        state.completed_checkpoints.clear()
        state.event_logs.append(
            {
                "event_type": "sim_reset",
                "timestamp": time.time(),
                "step_index": 0,
            }
        )
        return definition, state

    def _evaluate_checkpoints(
        self, definition: SimulationDefinition, state: SimulationState
    ) -> None:
        current_step_num = state.current_step_index + 1
        for chk in definition.checkpoints:
            if chk.step_number <= current_step_num and chk.checkpoint_id not in state.completed_checkpoints:
                state.completed_checkpoints.append(chk.checkpoint_id)
                state.event_logs.append(
                    {
                        "event_type": "checkpoint_completed",
                        "timestamp": time.time(),
                        "checkpoint_id": chk.checkpoint_id,
                        "title": chk.title,
                    }
                )


simulation_engine = SimulationEngineService()
