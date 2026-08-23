"""Visual Knowledge Graph Persistence Layer (Phase 4I.3)

Revision ID: 0016_visual_knowledge_graph
Revises: 0015_production_indexes
Create Date: 2026-08-05 00:00:00.000000

Creates tables and indexes for storing visual learning graphs, nodes, edges,
component metadata, learning objectives, relationships, layouts, simulation candidates,
and visual quiz blueprints.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0016_visual_knowledge_graph"
down_revision = "0015_production_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. visual_canvases
    op.create_table(
        "visual_canvases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("public_id", sa.String(40), nullable=False, unique=True),
        sa.Column("presentation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("presentations.id", ondelete="CASCADE"), nullable=True),
        sa.Column("slide_id", sa.String(64), nullable=True),
        sa.Column("content_unit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("content_units.id", ondelete="SET NULL"), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("pattern_type", sa.String(64), nullable=False),
        sa.Column("dimensions", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
        sa.Column("layout_config", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
        sa.Column("examples", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=True),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_visual_canvases_public_id", "visual_canvases", ["public_id"])
    op.create_index("ix_visual_canvases_presentation_id", "visual_canvases", ["presentation_id"])
    op.create_index("ix_visual_canvases_content_unit_id", "visual_canvases", ["content_unit_id"])
    op.create_index("ix_visual_canvases_user_id", "visual_canvases", ["user_id"])
    op.create_index("ix_visual_canvases_category", "visual_canvases", ["category"])
    op.create_index("ix_visual_canvases_user_category", "visual_canvases", ["user_id", "category"])
    op.create_index("ix_visual_canvases_presentation_slide", "visual_canvases", ["presentation_id", "slide_id"])

    # 2. visual_nodes
    op.create_table(
        "visual_nodes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("public_id", sa.String(40), nullable=False, unique=True),
        sa.Column("canvas_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("visual_canvases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("component_key", sa.String(100), nullable=False),
        sa.Column("node_type", sa.String(64), nullable=False, server_default="default"),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("category", sa.String(64), nullable=False, server_default="core"),
        sa.Column("position", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
        sa.Column("dimensions", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
        sa.Column("style", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
        sa.Column("importance_weight", sa.Float(), nullable=False, server_default=sa.text("0.5")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_visual_nodes_public_id", "visual_nodes", ["public_id"])
    op.create_index("ix_visual_nodes_canvas_id", "visual_nodes", ["canvas_id"])
    op.create_index("ix_visual_nodes_component_key", "visual_nodes", ["component_key"])
    op.create_index("ix_visual_nodes_canvas_comp_key", "visual_nodes", ["canvas_id", "component_key"])

    # 3. visual_edges
    op.create_table(
        "visual_edges",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("canvas_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("visual_canvases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("edge_key", sa.String(120), nullable=False),
        sa.Column("source_node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("visual_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("visual_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label", sa.String(255), nullable=True),
        sa.Column("relationship_type", sa.String(64), nullable=False),
        sa.Column("is_bidirectional", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("style", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_visual_edges_canvas_id", "visual_edges", ["canvas_id"])
    op.create_index("ix_visual_edges_source_target", "visual_edges", ["source_node_id", "target_node_id"])

    # 4. component_metadata
    op.create_table(
        "component_metadata",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("visual_nodes.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("overview", sa.Text(), nullable=False),
        sa.Column("detailed_working", sa.Text(), nullable=False),
        sa.Column("how_it_works", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=True),
        sa.Column("inputs", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=True),
        sa.Column("outputs", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=True),
        sa.Column("dependencies", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=True),
        sa.Column("real_world_analogy", sa.Text(), nullable=True),
        sa.Column("difficulty_level", sa.String(32), nullable=False, server_default="Intermediate"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_component_metadata_node_id", "component_metadata", ["node_id"])

    # 5. learning_objectives
    op.create_table(
        "learning_objectives",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("canvas_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("visual_canvases.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("main_goal", sa.Text(), nullable=False),
        sa.Column("learning_objectives", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
        sa.Column("important_ideas", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=True),
        sa.Column("prerequisites", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=True),
        sa.Column("expected_outcomes", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_learning_objectives_canvas_id", "learning_objectives", ["canvas_id"])

    # 6. visual_relationships
    op.create_table(
        "visual_relationships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("canvas_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("visual_canvases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_key", sa.String(100), nullable=False),
        sa.Column("target_key", sa.String(100), nullable=False),
        sa.Column("relationship_type", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("is_bidirectional", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_visual_relationships_canvas_id", "visual_relationships", ["canvas_id"])

    # 7. visual_layouts
    op.create_table(
        "visual_layouts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("canvas_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("visual_canvases.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("canvas_width", sa.Float(), nullable=False, server_default=sa.text("1200.0")),
        sa.Column("canvas_height", sa.Float(), nullable=False, server_default=sa.text("800.0")),
        sa.Column("node_spacing", sa.Float(), nullable=False, server_default=sa.text("180.0")),
        sa.Column("layout_direction", sa.String(32), nullable=False, server_default="horizontal"),
        sa.Column("layout_settings", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_visual_layouts_canvas_id", "visual_layouts", ["canvas_id"])

    # 8. simulation_candidates
    op.create_table(
        "simulation_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("canvas_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("visual_canvases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("simulation_type", sa.String(64), nullable=False),
        sa.Column("default_parameters", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_simulation_candidates_canvas_id", "simulation_candidates", ["canvas_id"])

    # 9. visual_quiz_blueprints
    op.create_table(
        "visual_quiz_blueprints",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("canvas_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("visual_canvases.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("quiz_focus_areas", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
        sa.Column("suggested_question_types", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=True),
        sa.Column("question_items", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_visual_quiz_blueprints_canvas_id", "visual_quiz_blueprints", ["canvas_id"])


def downgrade() -> None:
    op.drop_table("visual_quiz_blueprints")
    op.drop_table("simulation_candidates")
    op.drop_table("visual_layouts")
    op.drop_table("visual_relationships")
    op.drop_table("learning_objectives")
    op.drop_table("component_metadata")
    op.drop_table("visual_edges")
    op.drop_table("visual_nodes")
    op.drop_table("visual_canvases")
