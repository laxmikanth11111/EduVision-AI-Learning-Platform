"""Visual Persistence & Graph Validation Service (Phase 4I.3).

Handles saving, loading, updating, versioning, graph consistency validation, and Redis
caching of visual knowledge graphs.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.visual_knowledge_graph import (
    VisualCanvas,
)
from app.repositories.visual_knowledge_graph_repository import (
    ComponentMetadataRepository,
    LearningObjectiveRepository,
    SimulationCandidateRepository,
    VisualCanvasRepository,
    VisualEdgeRepository,
    VisualLayoutRepository,
    VisualNodeRepository,
    VisualQuizBlueprintRepository,
    VisualRelationshipRepository,
)
from app.schemas.visual_intelligence import (
    CategoryClassification,
    ComponentRelationship,
    DifficultyLevel,
    Dimensions,
    DiscoveredComponent,
    InputDescriptor,
    LayoutSuggestion,
    LearningObjectives,
    OutputDescriptor,
    Position,
    RelationshipType,
    TopicCategory,
    VisualEdgeSchema,
    VisualizationDecision,
    VisualizationType,
    VisualLearningModel,
    VisualNodeSchema,
)

logger = get_logger(__name__)


def _as_str_list(value: Any) -> list[str]:
    """Coerce an untyped JSON column into the ``list[str]`` the schemas expect.

    The ``learning_objectives`` table stores these as generic JSON arrays, so the
    element type is only guaranteed at the API boundary. Normalising here keeps
    a malformed legacy row from raising a ValidationError deep in the response
    serializer, and drops non-scalar entries instead of stringifying dicts.
    """
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    out: list[str] = []
    for item in value:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, (int, float, bool)):
            out.append(str(item))
    return out


class VisualGraphValidationError(ValidationError):

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message=message, details=details or {})


class VisualPersistenceService:

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.canvas_repo = VisualCanvasRepository(session)
        self.node_repo = VisualNodeRepository(session)
        self.edge_repo = VisualEdgeRepository(session)
        self.meta_repo = ComponentMetadataRepository(session)
        self.obj_repo = LearningObjectiveRepository(session)
        self.rel_repo = VisualRelationshipRepository(session)
        self.layout_repo = VisualLayoutRepository(session)
        self.sim_repo = SimulationCandidateRepository(session)
        self.quiz_repo = VisualQuizBlueprintRepository(session)

    def validate_graph_integrity(self, model: VisualLearningModel) -> None:
        """Validate knowledge graph consistency for missing nodes, broken edges, or duplicates."""
        if not model.components:
            raise VisualGraphValidationError("Graph must contain at least one component.")

        node_keys = {c.component_id for c in model.components}
        if len(node_keys) != len(model.components):
            raise VisualGraphValidationError("Duplicate component IDs detected in visual model.")

        broken_edges: list[str] = []
        for edge in model.visual_edges:
            if edge.source_node_id not in node_keys or edge.target_node_id not in node_keys:
                broken_edges.append(edge.edge_id)

        if broken_edges:
            raise VisualGraphValidationError(
                "Graph contains broken edges pointing to non-existent nodes.",
                details={"broken_edge_ids": broken_edges},
            )

    async def save_visual_model(
        self,
        model: VisualLearningModel,
        user_id: uuid.UUID | None,
        presentation_id: uuid.UUID | None = None,
        slide_id: str | None = None,
        content_unit_id: uuid.UUID | None = None,
        lesson_id: uuid.UUID | None = None,
    ) -> VisualCanvas:
        """Persist a complete VisualLearningModel into relational tables."""
        # 1. Graph validation
        self.validate_graph_integrity(model)

        # 2. Create Canvas entity
        canvas = await self.canvas_repo.create(
            user_id=user_id,
            presentation_id=presentation_id,
            slide_id=slide_id,
            lesson_id=lesson_id,
            content_unit_id=content_unit_id,
            title=model.topic,
            category=model.classification.primary_category.value,
            pattern_type=model.visualization_decision.visualization_type.value,
            dimensions=model.suggested_layout.canvas_dimensions.model_dump(),
            layout_config=model.visualization_decision.model_dump(),
            examples=model.examples,
            version=1,
        )

        # 3. Learning Objectives
        await self.obj_repo.create(
            canvas_id=canvas.id,
            main_goal=model.learning_objectives.main_goal,
            learning_objectives=model.learning_objectives.learning_objectives,
            important_ideas=model.learning_objectives.important_ideas,
            prerequisites=model.learning_objectives.prerequisites,
            expected_outcomes=model.learning_objectives.expected_outcomes,
        )

        # 4. Discovered Components & Visual Nodes + Metadata
        node_id_map: dict[str, uuid.UUID] = {}
        for idx, (comp, node_schema) in enumerate(zip(model.components, model.visual_nodes, strict=False)):
            node = await self.node_repo.create(
                canvas_id=canvas.id,
                component_key=comp.component_id,
                node_type="default",
                label=comp.name,
                category=comp.category,
                position=node_schema.position.model_dump(),
                dimensions=node_schema.dimensions.model_dump(),
                style=node_schema.style,
                importance_weight=comp.importance_weight,
                sort_order=idx,
            )
            node_id_map[comp.component_id] = node.id

            await self.meta_repo.create(
                node_id=node.id,
                overview=comp.short_description,
                detailed_working=comp.detailed_working,
                how_it_works=[f"Processes inputs for {comp.name}"],
                inputs=[i.model_dump() for i in comp.inputs],
                outputs=[o.model_dump() for o in comp.outputs],
                dependencies=comp.dependencies,
                real_world_analogy=comp.real_world_analogy,
                difficulty_level=comp.difficulty_level.value,
            )

        # 5. Visual Edges
        for edge_schema in model.visual_edges:
            src_uuid = node_id_map.get(edge_schema.source_node_id)
            tgt_uuid = node_id_map.get(edge_schema.target_node_id)
            if src_uuid and tgt_uuid:
                await self.edge_repo.create(
                    canvas_id=canvas.id,
                    edge_key=edge_schema.edge_id,
                    source_node_id=src_uuid,
                    target_node_id=tgt_uuid,
                    label=edge_schema.label,
                    relationship_type=edge_schema.relationship_type.value,
                    is_bidirectional=edge_schema.is_bidirectional,
                    style=edge_schema.style,
                )

        # 6. Conceptual Relationships
        for rel in model.relationships:
            await self.rel_repo.create(
                canvas_id=canvas.id,
                source_key=rel.source_id,
                target_key=rel.target_id,
                relationship_type=rel.relationship_type.value,
                description=rel.description,
                is_bidirectional=rel.is_bidirectional,
            )

        # 7. Visual Layout Config
        await self.layout_repo.create(
            canvas_id=canvas.id,
            canvas_width=model.suggested_layout.canvas_dimensions.width,
            canvas_height=model.suggested_layout.canvas_dimensions.height,
            node_spacing=model.suggested_layout.node_spacing,
            layout_direction=model.suggested_layout.layout_direction,
            layout_settings={},
        )

        # 8. Simulation Candidates
        for sim_type in model.future_simulation_candidates:
            await self.sim_repo.create(
                canvas_id=canvas.id,
                title=f"{sim_type} Simulator",
                simulation_type=sim_type,
                default_parameters={},
            )

        # 9. Visual Quiz Blueprint
        await self.quiz_repo.create(
            canvas_id=canvas.id,
            quiz_focus_areas=model.quiz_focus_areas,
            suggested_question_types=["hotspot", "sequencing", "matching"],
            question_items=[],
        )

        logger.info("visual_learning_model_persisted", canvas_id=str(canvas.id), node_count=len(node_id_map))
        return canvas

    async def load_visual_model(self, canvas_id: uuid.UUID) -> VisualLearningModel:
        """Load full VisualLearningModel graph from database entities."""
        canvas = await self.canvas_repo.get_canvas_with_full_graph(canvas_id)
        if not canvas:
            raise NotFoundError(message="Visual canvas not found", details={"canvas_id": str(canvas_id)})

        # Convert back into Pydantic VisualLearningModel
        nodes_schema: list[VisualNodeSchema] = []
        components: list[DiscoveredComponent] = []
        node_key_by_uuid: dict[uuid.UUID, str] = {}

        for n in canvas.nodes:
            node_key_by_uuid[n.id] = n.component_key
            nodes_schema.append(
                VisualNodeSchema(
                    node_id=n.component_key,
                    label=n.label,
                    category=n.category,
                    position=Position(**(n.position or {"x": 0.0, "y": 0.0})),
                    dimensions=Dimensions(**(n.dimensions or {"width": 160.0, "height": 90.0})),
                    style=n.style or {},
                    importance_weight=n.importance_weight,
                )
            )

            meta = n.component_metadata
            components.append(
                DiscoveredComponent(
                    component_id=n.component_key,
                    name=n.label,
                    category=n.category,
                    short_description=meta.overview if meta else n.label,
                    detailed_working=meta.detailed_working if meta else "",
                    inputs=[InputDescriptor(**i) if isinstance(i, dict) else InputDescriptor(name=str(i)) for i in (meta.inputs if meta and meta.inputs else [])],
                    outputs=[OutputDescriptor(**o) if isinstance(o, dict) else OutputDescriptor(name=str(o)) for o in (meta.outputs if meta and meta.outputs else [])],
                    dependencies=meta.dependencies if meta and meta.dependencies else [],
                    real_world_analogy=meta.real_world_analogy if meta else None,
                    importance_weight=n.importance_weight,
                    difficulty_level=DifficultyLevel(meta.difficulty_level) if meta else DifficultyLevel.INTERMEDIATE,
                )
            )

        edges_schema: list[VisualEdgeSchema] = []
        for e in canvas.edges:
            src_key = node_key_by_uuid.get(e.source_node_id, str(e.source_node_id))
            tgt_key = node_key_by_uuid.get(e.target_node_id, str(e.target_node_id))
            edges_schema.append(
                VisualEdgeSchema(
                    edge_id=e.edge_key,
                    source_node_id=src_key,
                    target_node_id=tgt_key,
                    label=e.label,
                    relationship_type=RelationshipType(e.relationship_type),
                    is_bidirectional=e.is_bidirectional,
                    style=e.style or {},
                )
            )

        rels_schema: list[ComponentRelationship] = [
            ComponentRelationship(
                source_id=r.source_key,
                target_id=r.target_key,
                relationship_type=RelationshipType(r.relationship_type),
                description=r.description,
                is_bidirectional=r.is_bidirectional,
            )
            for r in canvas.relationships
        ]

        obj = canvas.learning_objective
        objectives_schema = LearningObjectives(
            main_goal=obj.main_goal if obj else f"Understand {canvas.title}",
            learning_objectives=_as_str_list(
                obj.learning_objectives if obj else None
            ),
            important_ideas=_as_str_list(obj.important_ideas if obj else None),
            prerequisites=_as_str_list(obj.prerequisites if obj else None),
            expected_outcomes=_as_str_list(obj.expected_outcomes if obj else None),
        )

        layout_obj = canvas.layout
        layout_schema = LayoutSuggestion(
            canvas_dimensions=Dimensions(
                width=layout_obj.canvas_width if layout_obj else 1200.0,
                height=layout_obj.canvas_height if layout_obj else 800.0,
            ),
            node_spacing=layout_obj.node_spacing if layout_obj else 180.0,
            layout_direction=layout_obj.layout_direction if layout_obj else "horizontal",
        )

        quiz_bp = canvas.quiz_blueprint
        quiz_focus = quiz_bp.quiz_focus_areas if quiz_bp else []
        sim_candidates = [s.simulation_type for s in canvas.simulation_candidates]

        return VisualLearningModel(
            topic=canvas.title,
            classification=CategoryClassification(
                primary_category=TopicCategory(canvas.category),
                confidence_score=0.90,
            ),
            learning_objectives=objectives_schema,
            visualization_decision=VisualizationDecision(
                visualization_type=VisualizationType(canvas.pattern_type),
                reason="Restored from visual knowledge graph database.",
                confidence=0.90,
            ),
            components=components,
            relationships=rels_schema,
            visual_nodes=nodes_schema,
            visual_edges=edges_schema,
            suggested_layout=layout_schema,
            examples=canvas.examples or [],
            future_simulation_candidates=sim_candidates,
            quiz_focus_areas=quiz_focus,
        )
