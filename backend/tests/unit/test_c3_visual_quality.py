"""C3.7 visual quality gate — validity, safe metadata, and failure handling.

Covers:
- Every C3VisualType renders to a validation-passing, well-formed SVG.
- User-derived text (titles, concept names) is HTML-escaped in rendered output
  (no script/attribute injection) while raw strings remain structured metadata.
- Validation and rendering failure paths record FAILED status without persisting
  a broken asset.
- Need-analysis rules are deterministic.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.presentation import Presentation
from app.models.topic_outline import TopicOutline
from app.models.topic_visual_asset import TopicVisualAsset
from app.repositories.topic_visual_asset_repository import TopicVisualAssetRepository
from app.schemas.c3_visual_intelligence import C3VisualType, VisualStatus
from app.schemas.topic_outline import Concept, OutlineTopic, Subtopic
from app.services.c3_svg_renderer import render_visual
from app.services.c3_visual_need_analyzer import analyze_visual_need
from app.services.c3_visual_planning_pipeline import C3VisualPlanningPipeline
from app.services.c3_visual_spec_generator import generate_visual_specification
from tests.conftest import TEST_USER_ID

INJECTION_TITLE = 'Three-Way Handshake<script>alert("xss")</script>'
INJECTION_CONCEPT = 'SYN" onload="evil'


def _visual_topic() -> OutlineTopic:
    return OutlineTopic(
        title="TCP Handshake Process",
        slide_ranges=[1, 3],
        subtopics=[
            Subtopic(
                title=INJECTION_TITLE,
                concepts=[
                    Concept(name=n, description=f"{n} participates in the process stages.")
                    for n in [INJECTION_CONCEPT, "SYN-ACK", "ACK"]
                ],
            )
        ],
    )


def _numeric_topic() -> OutlineTopic:
    return OutlineTopic(
        title="TCP Handshake Process",
        slide_ranges=[1, 3],
        subtopics=[
            Subtopic(
                title="Three-Way Handshake",
                concepts=[
                    Concept(name=n, description=f"{n} participates in the process stages.")
                    for n in ["SYN", "SYN-ACK", "ACK", "Sequence", "Window"]
                ],
            )
        ],
    )


@pytest.mark.parametrize(
    "visual_type",
    list(C3VisualType),
    ids=[t.value for t in C3VisualType],
)
def test_c3_quality_01_all_types_pass_render_and_validation(visual_type: C3VisualType):
    spec = generate_visual_specification(
        topic=_numeric_topic(),
        subtopic=_numeric_topic().subtopics[0],
        visual_type=visual_type,
    )
    svg = render_visual(spec)
    assert svg.startswith("<svg"), f"type {visual_type.value} did not render an SVG"
    assert "</svg>" in svg

    validation = C3VisualPlanningPipeline._validate_rendered_output(svg, spec)
    assert validation["valid"], (
        f"type {visual_type.value} failed validation: {validation['errors']}"
    )

    ET.fromstring(svg)  # XML must be well-formed


def test_c3_quality_02_escapes_user_text_in_rendered_svg():
    spec = generate_visual_specification(
        topic=_visual_topic(),
        subtopic=_visual_topic().subtopics[0],
        visual_type=C3VisualType.FLOWCHART,
    )
    svg = render_visual(spec)

    assert "<script>" not in svg
    assert 'onload="' not in svg
    assert "&lt;script&gt;" in svg
    assert "&quot; onload=&quot;evil" in svg or "SYN&quot; onload=&quot;evil" in svg

    ET.fromstring(svg)


@pytest.mark.asyncio
async def test_c3_quality_03_persisted_asset_is_escaped_but_metadata_is_raw(
    db_session: AsyncSession,
):
    pres = Presentation(title="C3 Quality Deck", owner_id=TEST_USER_ID, slide_count=4)
    db_session.add(pres)
    await db_session.flush()
    db_session.add(
        TopicOutline(
            presentation_id=pres.id,
            title="C3 Quality Deck",
            status="succeeded",
            topics=[_visual_topic().model_dump(mode="json")],
        )
    )
    await db_session.commit()

    repo = TopicVisualAssetRepository(db_session)
    pipeline = C3VisualPlanningPipeline(asset_repo=repo)
    plan = await pipeline.plan_presentation_visuals(
        presentation_id=str(pres.id),
        user_id=TEST_USER_ID,
        topics=[_visual_topic()],
    )
    assert any(p.visual_needed for p in plan.topic_plans)

    saved = None
    for topic_plan in plan.topic_plans:
        if topic_plan.visual_needed and topic_plan.specification:
            saved = await pipeline.generate_and_persist_visual(
                plan=topic_plan,
                presentation_id=str(pres.id),
                user_id=TEST_USER_ID,
            )
    assert saved is not None
    await db_session.commit()

    row = (
        (
            await db_session.execute(
                select(TopicVisualAsset).where(TopicVisualAsset.presentation_id == pres.id)
            )
        )
        .scalars()
        .all()
    )[0]

    assert "<script>" not in row.asset_content
    assert "&lt;script&gt;" in row.asset_content
    assert row.subtopic_title == INJECTION_TITLE
    assert row.concept_ids
    assert all(raw.startswith("TCP Handshake Process:") for raw in row.concept_ids)
    assert row.status == VisualStatus.READY.value


def test_c3_quality_04_validation_gate_rejects_malformed_output():
    base = generate_visual_specification(
        topic=_numeric_topic(),
        subtopic=_numeric_topic().subtopics[0],
        visual_type=C3VisualType.FLOWCHART,
    )

    bad_short = "<svg>hi</svg>"
    check = C3VisualPlanningPipeline._validate_rendered_output(bad_short, base)
    assert check["valid"] is False
    assert any("too short" in e for e in check["errors"])

    not_svg = "<html><body>not a diagram</body></html>" * 5
    check2 = C3VisualPlanningPipeline._validate_rendered_output(not_svg, base)
    assert check2["valid"] is False
    assert any("not valid SVG" in e for e in check2["errors"])


@pytest.mark.asyncio
async def test_c3_quality_05_render_failure_marks_plan_failed(
    db_session: AsyncSession,
    monkeypatch,
):
    pres = Presentation(title="C3 Render Fail", owner_id=TEST_USER_ID, slide_count=4)
    db_session.add(pres)
    await db_session.commit()

    def _boom(*_args, **_kwargs):
        raise RuntimeError("renderer exploded")

    monkeypatch.setattr("app.services.c3_visual_planning_pipeline.render_visual", _boom)

    pipeline = C3VisualPlanningPipeline()
    plan = await pipeline.plan_presentation_visuals(
        presentation_id=str(pres.id),
        user_id=TEST_USER_ID,
        topics=[_numeric_topic()],
    )
    target = next(p for p in plan.topic_plans if p.visual_needed)
    assert target.specification is not None

    asset = await pipeline.generate_and_persist_visual(
        plan=target,
        presentation_id=str(pres.id),
        user_id=TEST_USER_ID,
    )
    assert asset is None
    assert target.status == VisualStatus.FAILED
    assert "renderer exploded" in target.error_message

    monkeypatch.undo()


def test_c3_quality_06_need_analysis_rules_are_deterministic():
    topic = _numeric_topic()
    subtopic = topic.subtopics[0]
    kwargs = {
        "topic_title": topic.title,
        "topic_content": f"{subtopic.title} " + " ".join(c.description for c in subtopic.concepts),
        "subtopic_title": subtopic.title,
        "subtopic_content": f"{subtopic.title} "
        + " ".join(c.description for c in subtopic.concepts),
        "concepts": [{"name": c.name, "description": c.description} for c in subtopic.concepts],
    }
    d1 = analyze_visual_need(**kwargs)
    d2 = analyze_visual_need(**kwargs)
    assert d1.model_dump() == d2.model_dump()
    assert d1.visual_needed is True
    assert d1.suggested_type is not None
