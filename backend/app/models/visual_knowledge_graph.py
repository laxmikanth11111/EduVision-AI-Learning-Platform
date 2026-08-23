"""SQLAlchemy 2.0 Models for Phase 4I.3 Visual Knowledge Graph Persistence Layer.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.database.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin

PUBLIC_CANVAS_PREFIX = "canvas_"
PUBLIC_NODE_PREFIX = "vnode_"


def generate_canvas_public_id() -> str:
    return f"{PUBLIC_CANVAS_PREFIX}{uuid.uuid4().hex[:16]}"


def generate_node_public_id() -> str:
    return f"{PUBLIC_NODE_PREFIX}{uuid.uuid4().hex[:16]}"


class VisualCanvas(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    """Top-level Visual Learning Graph Canvas."""

    __tablename__ = "visual_canvases"

    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        nullable=False,
        index=True,
        default=generate_canvas_public_id,
    )
    presentation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("presentations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    slide_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lesson_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("generated_lessons.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    content_unit_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("content_units.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    pattern_type: Mapped[str] = mapped_column(String(64), nullable=False)
    dimensions: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
        default=lambda: {"width": 1200.0, "height": 800.0},
    )
    layout_config: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
        default=dict,
    )
    examples: Mapped[list[Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
        default=list,
    )
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    nodes: Mapped[list[VisualNode]] = relationship(
        "VisualNode", back_populates="canvas", cascade="all, delete-orphan"
    )
    edges: Mapped[list[VisualEdge]] = relationship(
        "VisualEdge", back_populates="canvas", cascade="all, delete-orphan"
    )
    learning_objective: Mapped[LearningObjective | None] = relationship(
        "LearningObjective", back_populates="canvas", uselist=False, cascade="all, delete-orphan"
    )
    relationships: Mapped[list[VisualRelationship]] = relationship(
        "VisualRelationship", back_populates="canvas", cascade="all, delete-orphan"
    )
    layout: Mapped[VisualLayout | None] = relationship(
        "VisualLayout", back_populates="canvas", uselist=False, cascade="all, delete-orphan"
    )
    simulation_candidates: Mapped[list[SimulationCandidate]] = relationship(
        "SimulationCandidate", back_populates="canvas", cascade="all, delete-orphan"
    )
    quiz_blueprint: Mapped[VisualQuizBlueprint | None] = relationship(
        "VisualQuizBlueprint", back_populates="canvas", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_visual_canvases_user_category", "user_id", "category"),
        Index("ix_visual_canvases_presentation_slide", "presentation_id", "slide_id"),
    )


class VisualNode(Base, UUIDMixin, TimestampMixin):
    """Discrete visual component node on the graph canvas."""

    __tablename__ = "visual_nodes"

    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        nullable=False,
        index=True,
        default=generate_node_public_id,
    )
    canvas_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("visual_canvases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    component_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    node_type: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="core")
    position: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
        default=lambda: {"x": 0.0, "y": 0.0},
    )
    dimensions: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
        default=lambda: {"width": 160.0, "height": 90.0},
    )
    style: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
        default=dict,
    )
    importance_weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    canvas: Mapped[VisualCanvas] = relationship("VisualCanvas", back_populates="nodes")
    component_metadata: Mapped[ComponentMetadata | None] = relationship(
        "ComponentMetadata", back_populates="node", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_visual_nodes_canvas_comp_key", "canvas_id", "component_key"),
    )


class VisualEdge(Base, UUIDMixin, TimestampMixin):
    """Directional or bidirectional graph link between visual nodes."""

    __tablename__ = "visual_edges"

    canvas_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("visual_canvases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    edge_key: Mapped[str] = mapped_column(String(120), nullable=False)
    source_node_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("visual_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_node_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("visual_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    relationship_type: Mapped[str] = mapped_column(String(64), nullable=False)
    is_bidirectional: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    style: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
        default=dict,
    )

    canvas: Mapped[VisualCanvas] = relationship("VisualCanvas", back_populates="edges")
    source_node: Mapped[VisualNode] = relationship("VisualNode", foreign_keys=[source_node_id])
    target_node: Mapped[VisualNode] = relationship("VisualNode", foreign_keys=[target_node_id])

    __table_args__ = (
        Index("ix_visual_edges_source_target", "source_node_id", "target_node_id"),
    )


class ComponentMetadata(Base, UUIDMixin, TimestampMixin):
    """Deep pedagogical metadata for a visual component node."""

    __tablename__ = "component_metadata"

    node_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("visual_nodes.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    overview: Mapped[str] = mapped_column(Text, nullable=False)
    detailed_working: Mapped[str] = mapped_column(Text, nullable=False)
    how_it_works: Mapped[list[Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
        default=list,
    )
    inputs: Mapped[list[Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
        default=list,
    )
    outputs: Mapped[list[Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
        default=list,
    )
    dependencies: Mapped[list[Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
        default=list,
    )
    real_world_analogy: Mapped[str | None] = mapped_column(Text, nullable=True)
    difficulty_level: Mapped[str] = mapped_column(String(32), nullable=False, default="Intermediate")

    node: Mapped[VisualNode] = relationship("VisualNode", back_populates="component_metadata")


class LearningObjective(Base, UUIDMixin, TimestampMixin):
    """Learning goals and target outcomes for a visual canvas."""

    __tablename__ = "learning_objectives"

    canvas_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("visual_canvases.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    main_goal: Mapped[str] = mapped_column(Text, nullable=False)
    learning_objectives: Mapped[list[Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
        default=list,
    )
    important_ideas: Mapped[list[Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
        default=list,
    )
    prerequisites: Mapped[list[Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
        default=list,
    )
    expected_outcomes: Mapped[list[Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
        default=list,
    )

    canvas: Mapped[VisualCanvas] = relationship("VisualCanvas", back_populates="learning_objective")


class VisualRelationship(Base, UUIDMixin, TimestampMixin):
    """Conceptual graph relationship record."""

    __tablename__ = "visual_relationships"

    canvas_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("visual_canvases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_key: Mapped[str] = mapped_column(String(100), nullable=False)
    target_key: Mapped[str] = mapped_column(String(100), nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    is_bidirectional: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    canvas: Mapped[VisualCanvas] = relationship("VisualCanvas", back_populates="relationships")


class VisualLayout(Base, UUIDMixin, TimestampMixin):
    """Graph layout configuration settings for canvas rendering."""

    __tablename__ = "visual_layouts"

    canvas_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("visual_canvases.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    canvas_width: Mapped[float] = mapped_column(Float, nullable=False, default=1200.0)
    canvas_height: Mapped[float] = mapped_column(Float, nullable=False, default=800.0)
    node_spacing: Mapped[float] = mapped_column(Float, nullable=False, default=180.0)
    layout_direction: Mapped[str] = mapped_column(String(32), nullable=False, default="horizontal")
    layout_settings: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
        default=dict,
    )

    canvas: Mapped[VisualCanvas] = relationship("VisualCanvas", back_populates="layout")


class SimulationCandidate(Base, UUIDMixin, TimestampMixin):
    """Potential interactive simulation configurations for a canvas."""

    __tablename__ = "simulation_candidates"

    canvas_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("visual_canvases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    simulation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    default_parameters: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
        default=dict,
    )

    canvas: Mapped[VisualCanvas] = relationship("VisualCanvas", back_populates="simulation_candidates")


class VisualQuizBlueprint(Base, UUIDMixin, TimestampMixin):
    """Quiz focus areas and assessment blueprints for a visual graph."""

    __tablename__ = "visual_quiz_blueprints"

    canvas_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("visual_canvases.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    quiz_focus_areas: Mapped[list[Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
        default=list,
    )
    suggested_question_types: Mapped[list[Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
        default=list,
    )
    question_items: Mapped[list[Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
        default=list,
    )

    canvas: Mapped[VisualCanvas] = relationship("VisualCanvas", back_populates="quiz_blueprint")
