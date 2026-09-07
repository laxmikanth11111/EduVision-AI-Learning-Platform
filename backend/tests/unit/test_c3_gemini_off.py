"""C3.6 Gemini-off audit — proves the C3 visual stack is fully deterministic.

Three guarantees are exercised:
1. No C3 module imports any LLM/Gemini/GenAI provider code (AST import-graph scan).
2. Identical topic/subtopic inputs produce identical specifications and identical
   rendered SVG (no non-deterministic calls anywhere in the chain).
3. Persisted assets carry deterministic provider metadata (`deterministic_svg`)
   and never reference an AI model.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.presentation import Presentation
from app.models.topic_outline import TopicOutline
from app.models.topic_visual_asset import TopicVisualAsset
from app.schemas.c3_visual_intelligence import C3VisualType
from app.schemas.topic_outline import Concept, OutlineTopic, Subtopic
from app.services.c3_svg_renderer import render_visual
from app.services.c3_visual_planning_pipeline import C3VisualPlanningPipeline
from app.services.c3_visual_spec_generator import generate_visual_specification
from app.workers.c3_visual_tasks import _generate_visuals_async
from tests.conftest import TEST_USER_ID

APP_DIR = Path(__file__).resolve().parents[2] / "app"

C3_SOURCE_FILES = [
    "schemas/c3_visual_intelligence.py",
    "repositories/topic_visual_asset_repository.py",
    "services/c3_visual_need_analyzer.py",
    "services/c3_visual_spec_generator.py",
    "services/c3_svg_renderer.py",
    "services/c3_visual_planning_pipeline.py",
    "api/v1/c3_visual_router.py",
    "workers/c3_visual_tasks.py",
]

BANNED_IMPORT_ROOT = (
    "google",
    "openai",
    "anthropic",
    "vertexai",
    "langchain",
    "genai",
)

BANNED_APP_PREFIXES = (
    "app.core.ai_provider",
    "app.services.gemini",
    "app.services.ai_",
    "app.core.llm",
)


def _import_names(tree: ast.Module) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.append(node.module)
    return names


def test_c3_gemini_off_01_no_llm_imports_in_source_graph():
    violations: list[str] = []
    for rel in C3_SOURCE_FILES:
        path = APP_DIR / rel
        assert path.is_file(), f"missing C3 source: {path}"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for full_name in _import_names(tree):
            base = full_name.split(".")[0]
            if base in BANNED_IMPORT_ROOT or any(
                full_name.startswith(p) for p in BANNED_APP_PREFIXES
            ):
                violations.append(f"{rel} imports {full_name}")
    assert not violations, "\n".join(violations)


def _topic(title: str, concepts: list[str], subtopics: list[dict] | None = None) -> OutlineTopic:
    return OutlineTopic(
        title=title,
        slide_ranges=[1, 2],
        concepts=[
            Concept(name=n, description=f"{n} participates in the process stages.")
            for n in concepts
        ],
        subtopics=[
            Subtopic(
                title=s["title"],
                concepts=[
                    Concept(name=n, description=f"{n} is part of {s['title']}.")
                    for n in s["concepts"]
                ],
            )
            for s in (subtopics or [])
        ],
    )


FIXED_TOPIC = lambda: _topic(  # noqa: E731
    "TCP Handshake Process",
    ["SYN", "SYN-ACK", "ACK", "Sequence"],
    [
        {
            "title": "Three-Way Handshake",
            "concepts": ["SYN", "SYN-ACK", "ACK", "Sequence", "Window"],
        }
    ],
)


def test_c3_gemini_off_02_spec_generation_is_deterministic():
    spec_a = generate_visual_specification(
        topic=FIXED_TOPIC(),
        subtopic=FIXED_TOPIC().subtopics[0],
        visual_type=C3VisualType.FLOWCHART,
    )
    spec_b = generate_visual_specification(
        topic=FIXED_TOPIC(),
        subtopic=FIXED_TOPIC().subtopics[0],
        visual_type=C3VisualType.FLOWCHART,
    )
    assert spec_a.model_dump(mode="json") == spec_b.model_dump(mode="json")
    assert isinstance(spec_a.visual_type, C3VisualType)


def test_c3_gemini_off_03_rendering_is_deterministic_and_input_sensitive():
    spec = generate_visual_specification(
        topic=FIXED_TOPIC(),
        subtopic=FIXED_TOPIC().subtopics[0],
        visual_type=C3VisualType.FLOWCHART,
    )

    svg_1 = render_visual(spec)
    svg_2 = render_visual(spec)
    assert svg_1 == svg_2
    assert "<svg" in svg_1

    other_spec = spec.model_copy(deep=True)
    other_spec.title = "A completely different diagram title"
    other_spec.purpose = "A completely different instructional purpose"
    svg_3 = render_visual(other_spec)
    assert svg_3 != svg_1


@pytest.mark.asyncio
async def test_c3_gemini_off_04_pipeline_plan_is_deterministic():
    pipeline = C3VisualPlanningPipeline()
    plan_a = await pipeline.plan_presentation_visuals(
        presentation_id="pres-gemini-a",
        user_id=TEST_USER_ID,
        topics=[FIXED_TOPIC()],
    )
    plan_b = await pipeline.plan_presentation_visuals(
        presentation_id="pres-gemini-b",
        user_id=TEST_USER_ID,
        topics=[FIXED_TOPIC()],
    )

    for pa, pb in zip(plan_a.topic_plans, plan_b.topic_plans, strict=True):
        assert pa.specification.model_dump(mode="json") == pb.specification.model_dump(mode="json")
        assert pa.concept_ids == pb.concept_ids
        assert pa.visual_type == pb.visual_type


@pytest.mark.asyncio
async def test_c3_gemini_off_05_persisted_assets_are_deterministic_provider(
    db_session: AsyncSession,
):
    pres = Presentation(title="Gemini Off Deck", owner_id=TEST_USER_ID, slide_count=4)
    db_session.add(pres)
    await db_session.flush()
    db_session.add(
        TopicOutline(
            presentation_id=pres.id,
            title="Gemini Off Deck",
            status="succeeded",
            topics=[FIXED_TOPIC().model_dump(mode="json")],
        )
    )
    await db_session.commit()

    result = await _generate_visuals_async(
        presentation_id=pres.public_id,
        user_id=TEST_USER_ID,
    )
    assert result["success"] is True
    assert result["visuals_generated"] >= 1

    rows = (
        (
            await db_session.execute(
                select(TopicVisualAsset).where(TopicVisualAsset.presentation_id == pres.id)
            )
        )
        .scalars()
        .all()
    )
    assert rows, "expected at least one persisted visual asset"
    row = rows[0]
    meta = row.generation_metadata or {}
    assert meta.get("provider") == "deterministic_svg"
    assert "model" not in meta
    assert row.provenance == "ai_explained"
    assert row.asset_format == "svg"
    assert row.asset_content.strip().startswith("<svg")
