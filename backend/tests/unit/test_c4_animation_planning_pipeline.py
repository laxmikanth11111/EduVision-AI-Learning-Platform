"""Unit tests for EduVision 2.0 Checkpoint C4 â€” animation planning pipeline."""

import uuid
from types import SimpleNamespace

import pytest

from app.schemas.c4_animation_intelligence import (
    AnimationAsset,
    AnimationStatus,
    C4AnimationType,
    compute_animation_fingerprint,
)
from app.schemas.topic_outline import OutlineTopic, Subtopic
from app.services.c4_animation_planning_pipeline import C4AnimationPlanningPipeline

UUID = uuid.uuid4()
PRESENTATION_ID = str(uuid.uuid4())


def _concept(name: str, description: str = "concept description") -> dict:
    return {"name": name, "description": description}


def _flowchart_base_spec() -> dict:
    return {
        "visual_type": "flowchart",
        "title": "TCP handshake",
        "nodes": [
            {"id": "start", "label": "Start", "node_type": "start"},
            {"id": "step_0", "label": "SYN sent", "node_type": "process"},
            {"id": "step_1", "label": "SYN-ACK", "node_type": "process"},
            {"id": "step_2", "label": "ACK", "node_type": "process"},
        ],
        "edges": [
            {"id": "e_0", "source_id": "start", "target_id": "step_0"},
            {"id": "e_1", "source_id": "step_0", "target_id": "step_1"},
            {"id": "e_2", "source_id": "step_1", "target_id": "step_2"},
        ],
    }


def _c3_asset(**overrides) -> SimpleNamespace:
    base = {
        "id": uuid.uuid4(),
        "public_id": "c3v_test",
        "presentation_id": UUID,
        "user_id": UUID,
        "topic_id": "Networking Basics",
        "topic_title": "Networking Basics",
        "subtopic_id": "TCP Handshake",
        "subtopic_title": "TCP Handshake",
        "visual_type": "flowchart",
        "status": "ready",
        "version": 1,
        "fingerprint": "fp",
        "asset_format": "svg",
        "specification": _flowchart_base_spec(),
        "title": "TCP handshake",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class _FakeC3Repo:
    def __init__(self, assets: list) -> None:
        self.assets = assets

    async def list_by_presentation(self, presentation_id, *, status=None, page=1, page_size=50):
        return self.assets, len(self.assets)


class _FakeAnimationRepo:
    def __init__(self) -> None:
        self.created: list = []
        self.by_fingerprint: dict[str, SimpleNamespace] = {}

    async def lock_generation(self, presentation_id, user_id):
        pass

    async def next_version(self, fingerprint):
        return 1 + max((a.version for a in self.created if a.fingerprint == fingerprint), default=0)

    async def update(self, asset_id, **kwargs):
        obj = next(a for a in self.created if a.id == asset_id)
        for key, value in kwargs.items():
            setattr(obj, key, value)
        return obj

    async def create(self, **kwargs) -> SimpleNamespace:
        obj = SimpleNamespace(id=uuid.uuid4(), created_at=None, **kwargs)
        self.created.append(obj)
        return obj

    async def get_ready_by_fingerprint(self, fingerprint: str):
        return self.by_fingerprint.get(fingerprint)

    async def supersede_old_version(self, fingerprint: str, exclude_id: uuid.UUID) -> int:
        return 0


def _topics() -> list[OutlineTopic]:
    subtopic = Subtopic(
        title="TCP Handshake",
        learning_objectives=[
            "Explain the three-step handshake order",
        ],
        concepts=[_concept("SYN"), _concept("ACK", "acknowledgement")],
        source_references=[],
        examples=[],
    )
    topic = OutlineTopic(
        title="Networking Basics",
        slide_ranges=[1, 3],
        subtopics=[subtopic],
        learning_objectives=[
            "Describe the ordered steps of a TCP handshake and why ordering matters",
        ],
    )
    return [topic]


class TestC4PlanningPipeline:
    def test_c4_plan_01_plans_animation_from_ready_visual(self):
        pipeline = C4AnimationPlanningPipeline(c3_repo=_FakeC3Repo([_c3_asset()]))
        plan = _run(pipeline.plan_presentation_animations(PRESENTATION_ID, UUID, _topics()))
        assert plan.animations_planned == 1
        assert plan.animations_skipped == 0
        topic_plan = plan.topic_plans[0]
        assert topic_plan.animation_needed is True
        assert topic_plan.specification is not None
        assert topic_plan.specification.animation_type == C4AnimationType.PROCESS_SEQUENCE
        assert topic_plan.status == AnimationStatus.SPECIFYING

    def test_c4_plan_02_no_foundation_skipped(self):
        pipeline = C4AnimationPlanningPipeline(c3_repo=_FakeC3Repo([]))
        plan = _run(pipeline.plan_presentation_animations(PRESENTATION_ID, UUID, _topics()))
        assert plan.animations_planned == 0
        assert plan.animations_skipped == 1
        topic_plan = plan.topic_plans[0]
        assert topic_plan.animation_needed is False
        assert "foundation" in (topic_plan.error_message or "")

    def test_c4_plan_03_static_visual_type_skipped(self):
        static = _c3_asset(subtopic_id="Chart", subtopic_title="Chart", visual_type="chart")
        pipeline = C4AnimationPlanningPipeline(c3_repo=_FakeC3Repo([static]))
        topic = _topics()[0]
        topic.subtopics[0] = Subtopic(
            title="Chart", concepts=[_concept("KPI")], learning_objectives=["Read a chart"]
        )
        plan = _run(pipeline.plan_presentation_animations(PRESENTATION_ID, UUID, [topic]))
        assert plan.animations_planned == 0
        assert "static" in (plan.topic_plans[0].error_message or "").lower()

    def test_c4_plan_04_topic_without_subtopics_supported(self):
        topic = OutlineTopic(
            title="TCP Handshake",
            slide_ranges=[1, 2],
            learning_objectives=[
                "Show the ordered SYN/SYN-ACK/ACK sequence in detail with exact wording",
            ],
            concepts=[_concept("SYN"), _concept("ACK"), _concept("Handshake")],
        )
        asset = _c3_asset(subtopic_id="", subtopic_title="", topic_id="TCP Handshake", topic_title="TCP Handshake")
        pipeline = C4AnimationPlanningPipeline(c3_repo=_FakeC3Repo([asset]))
        plan = _run(pipeline.plan_presentation_animations(PRESENTATION_ID, UUID, [topic]))
        assert plan.animations_planned == 1
        assert plan.topic_plans[0].specification is not None

    def test_c4_gen_01_generates_and_persists_package(self):
        anim_repo = _FakeAnimationRepo()
        pipeline = C4AnimationPlanningPipeline(
            c3_repo=_FakeC3Repo([_c3_asset()]), asset_repo=anim_repo
        )
        plan = _run(pipeline.plan_presentation_animations(PRESENTATION_ID, UUID, _topics()))
        topic_plan = plan.topic_plans[0]
        asset = _run(pipeline.generate_and_persist_animation(topic_plan, PRESENTATION_ID, UUID))
        assert asset is not None
        assert asset.status == AnimationStatus.READY
        assert asset.asset_format == "html"
        assert "<svg" in asset.package_content or "c4-svg" in asset.package_content
        assert len(anim_repo.created) == 1
        created = anim_repo.created[0]
        assert created.animation_type == "process_sequence"
        expected_fp = compute_animation_fingerprint(
            PRESENTATION_ID, topic_plan.topic_id, topic_plan.subtopic_id, topic_plan.concept_ids
        )
        assert created.fingerprint == expected_fp

    def test_c4_gen_02_cache_hit_skips_persist(self):
        anim_repo = _FakeAnimationRepo()
        pipeline = C4AnimationPlanningPipeline(
            c3_repo=_FakeC3Repo([_c3_asset()]), asset_repo=anim_repo
        )
        plan = _run(pipeline.plan_presentation_animations(PRESENTATION_ID, UUID, _topics()))
        topic_plan = plan.topic_plans[0]
        fp = compute_animation_fingerprint(
            PRESENTATION_ID, topic_plan.topic_id, topic_plan.subtopic_id, topic_plan.concept_ids
        )
        cached = SimpleNamespace(
            id=uuid.uuid4(),
            animation_type="process_sequence",
            title="T",
            status="ready",
            asset_format="html",
            package_content="<p></p>",
            specification=topic_plan.specification.model_dump(mode="json"),
            pedagogical_rationale="",
            explanation={},
            provenance="ai_explained",
            source_references=[],
            concept_ids=[],
            presentation_id=None,
            topic_id=topic_plan.topic_id,
            subtopic_id=topic_plan.subtopic_id,
            version=1,
            fingerprint=fp,
            created_at=None,
            generation_metadata={},
        )
        anim_repo.by_fingerprint[fp] = cached
        asset = _run(pipeline.generate_and_persist_animation(topic_plan, PRESENTATION_ID, UUID))
        assert asset is not None
        assert len(anim_repo.created) == 0

    def test_c4_gen_03_no_spec_returns_none(self):
        pipeline = C4AnimationPlanningPipeline(asset_repo=_FakeAnimationRepo())
        from app.schemas.c4_animation_intelligence import TopicAnimationPlan

        plan_obj = TopicAnimationPlan(topic_id="x", topic_title="x", animation_needed=False)
        result = _run(pipeline.generate_and_persist_animation(plan_obj, PRESENTATION_ID, UUID))
        assert result is None

    def test_c4_gen_04_validation_failure_marks_failed(self, monkeypatch):
        anim_repo = _FakeAnimationRepo()
        pipeline = C4AnimationPlanningPipeline(
            c3_repo=_FakeC3Repo([_c3_asset()]), asset_repo=anim_repo
        )
        plan = _run(pipeline.plan_presentation_animations(PRESENTATION_ID, UUID, _topics()))
        topic_plan = plan.topic_plans[0]
        import app.services.c4_animation_planning_pipeline as mod

        monkeypatch.setattr(mod, "render_animation_package", lambda *a, **k: "<p>too short</p>")
        result = _run(pipeline.generate_and_persist_animation(topic_plan, PRESENTATION_ID, UUID))
        assert result is None
        assert topic_plan.status == AnimationStatus.FAILED
        assert topic_plan.error_message
        assert anim_repo.created[0].status == "failed"
        assert anim_repo.created[0].error_message == topic_plan.error_message

    def test_c4_gen_05_model_to_asset_roundtrip(self):
        model = SimpleNamespace(
            id=uuid.uuid4(),
            animation_type="network_flow",
            title="Learn: Traffic Flow",
            status="ready",
            asset_format="html",
            package_content="<html></html>",
            specification=None,
            pedagogical_rationale="rationale",
            explanation={},
            provenance="ai_explained",
            source_references=[],
            concept_ids=[],
            presentation_id=UUID,
            topic_id="t",
            subtopic_id=None,
            version=1,
            fingerprint="fp2",
            created_at=None,
            generation_metadata={"duration_ms": 12},
        )
        asset = C4AnimationPlanningPipeline._model_to_asset(model)
        assert isinstance(asset, AnimationAsset)
        assert asset.animation_type == C4AnimationType.NETWORK_FLOW
        assert asset.status == AnimationStatus.READY


def _run(coro):
    import asyncio

    return asyncio.run(coro)
