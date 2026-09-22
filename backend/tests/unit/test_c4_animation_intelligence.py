"""Unit tests for EduVision 2.0 Checkpoint C4 — Animation Intelligence
Specification (bounded deterministic schema)."""

import pytest

from app.schemas.c3_visual_intelligence import VisualEdge, VisualNode
from app.schemas.c4_animation_intelligence import (
    AnimationInteraction,
    AnimationInteractionKind,
    AnimationScene,
    AnimationSpecification,
    AnimationStep,
    AnimationStepKind,
    C4AnimationType,
    allowed_step_kinds,
    compute_animation_fingerprint,
)


def _node(nid: str, label: str) -> VisualNode:
    return VisualNode(id=nid, label=label)


def _edge(eid: str, src: str, tgt: str) -> VisualEdge:
    return VisualEdge(id=eid, source_id=src, target_id=tgt)


def _step(
    index: int,
    kind: AnimationStepKind,
    node_ids=None,
    edge_ids=None,
    duration_ms=None,
) -> AnimationStep:
    return AnimationStep(
        step_index=index,
        kind=kind,
        node_ids=node_ids or [],
        edge_ids=edge_ids or [],
        caption=f"step {index}",
        duration_ms=duration_ms,
    )


def _valid_process_spec() -> AnimationSpecification:
    return AnimationSpecification(
        animation_type=C4AnimationType.PROCESS_SEQUENCE,
        title="TCP handshake animation",
        purpose="Show why connection establishment needs three ordered messages",
        learning_objective="Describe the order of the TCP three-way handshake",
        base_visual_type="sequence_diagram",
        nodes=[_node("n1", "Client"), _node("n2", "Server")],
        edges=[_edge("e1", "n1", "n2")],
        scenes=[
            AnimationScene(
                scene_index=1,
                title="Handshake steps",
                steps=[
                    _step(1, AnimationStepKind.REVEAL, node_ids=["n1"]),
                    _step(2, AnimationStepKind.REVEAL, node_ids=["n2"]),
                    _step(3, AnimationStepKind.HIGHLIGHT, edge_ids=["e1"]),
                    _step(4, AnimationStepKind.ANNOTATE),
                ],
            )
        ],
        interactions=[
            AnimationInteraction(
                interaction_index=1,
                kind=AnimationInteractionKind.SELF_CHECK,
                anchor_step_index=4,
                prompt="Why does the SYN-ACK step matter?",
                answer="It acknowledges the SYN and proposes the server's own sequence start.",
                guide_hint="Count how many messages have been exchanged by this step.",
            )
        ],
        pedagogical_rationale="Ordering of the three messages cannot be expressed in a static diagram.",
        concept_ids=["tcp", "handshake"],
        source_references=[{"slide_number": 3}],
    )


class TestC4AnimationSpecValidation:
    def test_c4_spec_01_valid_with_derived_visual_base(self):
        spec = _valid_process_spec()
        assert spec.total_duration_ms == 4 * 1200
        assert all(s.duration_ms == 1200 for s in spec.scenes[0].steps)

    def test_c4_spec_02_no_scenes_rejected(self):
        spec = _valid_process_spec().model_dump()
        spec["scenes"] = []
        with pytest.raises(ValueError, match="at least one scene"):
            AnimationSpecification.model_validate(spec)

    def test_c4_spec_03_disallowed_step_kind_rejected(self):
        spec = _valid_process_spec().model_dump()
        spec["scenes"][0]["steps"] = [
            _step(1, AnimationStepKind.TRAVERSE, edge_ids=["e1"]).model_dump()
        ]
        with pytest.raises(ValueError, match="not allowed"):
            AnimationSpecification.model_validate(spec)

    def test_c4_spec_04_unknown_node_reference_rejected(self):
        spec = _valid_process_spec().model_dump()
        spec["scenes"][0]["steps"][0] = _step(
            1, AnimationStepKind.REVEAL, node_ids=["ghost"]
        ).model_dump()
        with pytest.raises(ValueError, match="unknown node"):
            AnimationSpecification.model_validate(spec)

    def test_c4_spec_05_traverse_requires_edge(self):
        spec = _valid_process_spec().model_dump()
        spec["animation_type"] = C4AnimationType.NETWORK_FLOW.value
        spec["scenes"][0]["steps"] = [_step(1, AnimationStepKind.TRAVERSE).model_dump()]
        with pytest.raises(ValueError, match="must target an edge"):
            AnimationSpecification.model_validate(spec)

    def test_c4_spec_06_reveal_requires_target(self):
        spec = _valid_process_spec().model_dump()
        spec["scenes"][0]["steps"] = [_step(1, AnimationStepKind.REVEAL).model_dump()]
        with pytest.raises(ValueError, match="must target at least one node or edge"):
            AnimationSpecification.model_validate(spec)

    def test_c4_spec_07_non_sequential_scene_indices_rejected(self):
        spec = _valid_process_spec()
        second = spec.scenes[0].model_copy(deep=True)
        second.scene_index = 3
        with pytest.raises(ValueError, match="sequential"):
            AnimationSpecification(
                animation_type=spec.animation_type,
                title=spec.title,
                nodes=spec.nodes,
                edges=spec.edges,
                scenes=[spec.scenes[0], second],
            )

    def test_c4_spec_08_non_sequential_step_indices_rejected(self):
        spec = _valid_process_spec().model_dump()
        spec["scenes"][0]["steps"] = [
            _step(1, AnimationStepKind.REVEAL, node_ids=["n1"]).model_dump(),
            _step(3, AnimationStepKind.REVEAL, node_ids=["n2"]).model_dump(),
        ]
        with pytest.raises(ValueError, match="sequential"):
            AnimationSpecification.model_validate(spec)

    def test_c4_spec_09_empty_scene_rejected(self):
        spec = _valid_process_spec().model_dump()
        spec["scenes"][0]["steps"] = []
        with pytest.raises(ValueError, match="at least one step"):
            AnimationSpecification.model_validate(spec)

    def test_c4_spec_10_too_many_scenes_rejected(self):
        spec = _valid_process_spec()
        scenes = []
        for i in range(1, 6):
            s = spec.scenes[0].model_copy(deep=True)
            s.scene_index = i
            scenes.append(s)
        with pytest.raises(ValueError, match="exceeds max"):
            AnimationSpecification(
                animation_type=spec.animation_type,
                title=spec.title,
                nodes=spec.nodes,
                edges=spec.edges,
                scenes=scenes,
            )

    def test_c4_spec_11_total_duration_budget_enforced(self):
        spec = _valid_process_spec().model_dump()
        spec["scenes"] = [
            AnimationScene(
                scene_index=i,
                steps=[
                    AnimationStep(
                        step_index=j,
                        kind=AnimationStepKind.REVEAL,
                        node_ids=["n1"],
                        duration_ms=4000,
                    )
                    for j in range(1, 6)
                ],
            )
            for i in range(1, 4)
        ]
        with pytest.raises(ValueError, match="exceeds max"):
            AnimationSpecification.model_validate(spec)

    def test_c4_spec_12_step_duration_out_of_bounds_rejected(self):
        spec = _valid_process_spec().model_dump()
        spec["scenes"][0]["steps"][0] = _step(
            1, AnimationStepKind.REVEAL, node_ids=["n1"], duration_ms=100
        ).model_dump()
        with pytest.raises(ValueError, match="out of bounds"):
            AnimationSpecification.model_validate(spec)

    def test_c4_spec_13_interaction_requires_visible_step(self):
        spec = _valid_process_spec().model_dump()
        spec["interactions"] = [
            AnimationInteraction(
                interaction_index=1,
                kind=AnimationInteractionKind.PAUSE_REFLECT,
                anchor_step_index=99,
                prompt="p",
                answer="a",
            ).model_dump()
        ]
        with pytest.raises(ValueError, match="non-pause step"):
            AnimationSpecification.model_validate(spec)

    def test_c4_spec_14_pause_keep_step_visible(self):
        spec = _valid_process_spec().model_dump()
        spec["interactions"] = []
        spec["scenes"][0]["steps"] = [
            _step(1, AnimationStepKind.REVEAL, node_ids=["n1"]).model_dump(),
            _step(2, AnimationStepKind.PAUSE).model_dump(),
            _step(3, AnimationStepKind.ANNOTATE).model_dump(),
        ]
        rebuilt = AnimationSpecification.model_validate(spec)
        assert rebuilt.scenes[0].steps[1].duration_ms == 1200

    def test_c4_spec_15_node_override_default_duration_plus_total(self):
        spec = _valid_process_spec()
        step = spec.scenes[0].steps[0]
        step.duration_ms = 2000
        spec.total_duration_ms = 0
        rebuilt = AnimationSpecification.model_validate(spec.model_dump())
        assert rebuilt.total_duration_ms == (2000 + 3 * 1200)

    def test_c4_spec_16_state_transition_transform_allowed(self):
        spec = _valid_process_spec().model_dump()
        spec["interactions"] = []
        spec["animation_type"] = C4AnimationType.STATE_TRANSITION.value
        spec["scenes"][0]["steps"] = [
            _step(1, AnimationStepKind.REVEAL, node_ids=["n1"]).model_dump(),
            _step(
                2,
                AnimationStepKind.TRANSFORM,
                node_ids=["n1"],
                duration_ms=1500,
            ).model_dump(),
        ]
        rebuilt = AnimationSpecification.model_validate(spec)
        assert rebuilt.scenes[0].steps[1].duration_ms == 1500


class TestC4AnimationTypesRegistry:
    def test_c4_registry_01_every_type_has_non_empty_template(self):
        for atype in C4AnimationType:
            allowed = allowed_step_kinds(atype)
            assert len(allowed) > 0, f"animation type {atype.value} has no template"

    def test_c4_registry_02_traverse_limited_to_motion_types(self):
        motion_types = {
            C4AnimationType.CAUSE_EFFECT_CHAIN,
            C4AnimationType.TIMELINE_PROGRESS,
            C4AnimationType.CYCLE_LOOP,
            C4AnimationType.NETWORK_FLOW,
        }
        for atype in C4AnimationType:
            has_traverse = AnimationStepKind.TRAVERSE in allowed_step_kinds(atype)
            assert has_traverse == (atype in motion_types)

    def test_c4_registry_03_pause_always_available(self):
        for atype in C4AnimationType:
            assert AnimationStepKind.PAUSE in allowed_step_kinds(atype)


class TestC4Fingerprint:
    def test_c4_fingerprint_01_deterministic(self):
        fp1 = compute_animation_fingerprint("pres_1", "topic_a", "sub_1", ["c1", "c2"])
        fp2 = compute_animation_fingerprint("pres_1", "topic_a", "sub_1", ["c1", "c2"])
        assert fp1 == fp2
        assert len(fp1) == 32

    def test_c4_fingerprint_02_changes_with_inputs(self):
        fp1 = compute_animation_fingerprint("pres_1", "topic_a", "sub_1", ["c1", "c2"])
        fp2 = compute_animation_fingerprint("pres_1", "topic_a", "sub_1", ["c1", "c3"])
        assert fp1 != fp2


@pytest.mark.parametrize("target", ["nodes", "edges"])
def test_duplicate_graph_identity_rejected(target):
    data = _valid_process_spec().model_dump()
    data[target].append(data[target][0].copy())
    with pytest.raises(ValueError, match="identities must be unique"):
        AnimationSpecification.model_validate(data)


def test_edge_endpoint_must_exist():
    data = _valid_process_spec().model_dump()
    data["edges"][0]["target_id"] = "missing"
    with pytest.raises(ValueError, match="unknown node"):
        AnimationSpecification.model_validate(data)


def test_initial_scene_nodes_must_exist():
    data = _valid_process_spec().model_dump()
    data["scenes"][0]["initial_node_ids"] = ["missing"]
    with pytest.raises(ValueError, match="unknown initial node"):
        AnimationSpecification.model_validate(data)


def test_interaction_anchor_validated_in_its_actual_scene():
    data = _valid_process_spec().model_dump()
    data["scenes"].append(
        {"scene_index": 2, "steps": [_step(1, AnimationStepKind.PAUSE).model_dump()]}
    )
    # Legacy anchors target the final scene, not any same-numbered step.
    with pytest.raises(ValueError, match="non-pause step"):
        AnimationSpecification.model_validate(data)
    data["interactions"][0]["anchor_scene_index"] = 1
    spec = AnimationSpecification.model_validate(data)
    from app.services.c4_animation_renderer import _interaction_payload

    payload = _interaction_payload(spec)
    assert payload[0]["sceneIndex"] == 1
    assert payload[0]["globalStepIndex"] == 4
