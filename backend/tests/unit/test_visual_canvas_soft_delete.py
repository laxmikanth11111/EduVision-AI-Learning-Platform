"""WS10: soft-delete isolation for the visual knowledge-graph repositories.

Soft-deleted canvases keep their sub-graph rows (nodes/edges/layout/...) in the
database so a canvas can be restored later, but those rows must never be
reachable through any repository query path. This locks in that invariant.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.visual_knowledge_graph import (
    VisualCanvas,
    VisualEdge,
    VisualLayout,
    VisualNode,
    VisualQuizBlueprint,
    VisualRelationship,
)
from app.repositories.visual_knowledge_graph_repository import (
    VisualCanvasRepository,
    VisualEdgeRepository,
    VisualLayoutRepository,
    VisualNodeRepository,
    VisualQuizBlueprintRepository,
    VisualRelationshipRepository,
)


async def _make_canvas(db_session: AsyncSession, *, deleted: bool = False) -> uuid.UUID:
    canvas = VisualCanvas(
        public_id=f"canvas_{uuid.uuid4().hex[:16]}",
        title="WS10 Canvas",
        category="architecture",
        pattern_type="block_diagram",
        dimensions={"width": 1200.0, "height": 800.0},
        layout_config={},
    )
    db_session.add(canvas)
    await db_session.flush()
    if deleted:
        canvas.soft_delete()
        await db_session.flush()
    return canvas.id  # type: ignore[no-any-return]


async def _seed_subgraph(db_session: AsyncSession, canvas_id: uuid.UUID) -> None:
    node_a = VisualNode(
        canvas_id=canvas_id,
        component_key="comp_a",
        label="CPU",
        sort_order=1,
    )
    node_b = VisualNode(
        canvas_id=canvas_id,
        component_key="comp_b",
        label="RAM",
        sort_order=2,
    )
    db_session.add_all([node_a, node_b])
    await db_session.flush()
    db_session.add(
        VisualEdge(
            canvas_id=canvas_id,
            edge_key="e1",
            source_node_id=node_a.id,
            target_node_id=node_b.id,
            relationship_type="depends_on",
        )
    )
    db_session.add(
        VisualRelationship(
            canvas_id=canvas_id,
            source_key="comp_a",
            target_key="comp_b",
            relationship_type="depends_on",
            description="CPU depends on RAM",
        )
    )
    db_session.add(
        VisualLayout(
            canvas_id=canvas_id,
            canvas_width=1200.0,
            canvas_height=800.0,
            node_spacing=180.0,
            layout_direction="horizontal",
        )
    )
    db_session.add(
        VisualQuizBlueprint(
            canvas_id=canvas_id,
            quiz_focus_areas=["cpu"],
        )
    )
    await db_session.flush()


@pytest.mark.asyncio
async def test_subgraph_queries_blocked_for_soft_deleted_canvas(
    db_session: AsyncSession,
) -> None:
    canvas_id = await _make_canvas(db_session, deleted=True)
    await _seed_subgraph(db_session, canvas_id)

    node_repo = VisualNodeRepository(db_session)
    edge_repo = VisualEdgeRepository(db_session)
    rel_repo = VisualRelationshipRepository(db_session)
    layout_repo = VisualLayoutRepository(db_session)
    quiz_repo = VisualQuizBlueprintRepository(db_session)

    for query in (
        node_repo.get_nodes_by_canvas(canvas_id),
        edge_repo.get_edges_by_canvas(canvas_id),
        rel_repo.get_by_canvas_id(canvas_id),
        layout_repo.get_by_canvas_id(canvas_id),
        quiz_repo.get_by_canvas_id(canvas_id),
    ):
        with pytest.raises(NotFoundError):
            await query


@pytest.mark.asyncio
async def test_subgraph_queries_work_for_active_canvas(
    db_session: AsyncSession,
) -> None:
    canvas_id = await _make_canvas(db_session)
    await _seed_subgraph(db_session, canvas_id)

    nodes = await VisualNodeRepository(db_session).get_nodes_by_canvas(canvas_id)
    assert len(nodes) == 2

    edges = await VisualEdgeRepository(db_session).get_edges_by_canvas(canvas_id)
    assert len(edges) == 1

    rels = await VisualRelationshipRepository(db_session).get_by_canvas_id(canvas_id)
    assert len(rels) == 1

    layout = await VisualLayoutRepository(db_session).get_by_canvas_id(canvas_id)
    assert layout is not None

    quiz = await VisualQuizBlueprintRepository(db_session).get_by_canvas_id(canvas_id)
    assert quiz is not None


@pytest.mark.asyncio
async def test_canvas_repository_excludes_soft_deleted(
    db_session: AsyncSession,
) -> None:
    owner_id = uuid.uuid4()
    deleted_id = await _make_canvas(db_session, deleted=True)
    active_id = await _make_canvas(db_session)
    from sqlalchemy import update

    await db_session.execute(
        update(VisualCanvas)
        .where(VisualCanvas.id.in_([deleted_id, active_id]))
        .values(user_id=owner_id)
    )
    await db_session.flush()
    repo = VisualCanvasRepository(db_session)

    public_id_deleted = (await repo.get_or_raise(deleted_id)).public_id
    assert await repo.get_by_public_id(public_id_deleted) is None
    assert await repo.get_canvas_with_full_graph(deleted_id) is None

    canvases, total = await repo.list_user_canvases(owner_id, page=1, page_size=20)
    assert total == 1
    assert active_id in {c.id for c in canvases}
    assert deleted_id not in {c.id for c in canvases}
