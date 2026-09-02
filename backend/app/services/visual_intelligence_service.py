"""Visual Intelligence Service Facade & Orchestrator (Phase 4I.2).

Unified service orchestrating topic classification, learning objective extraction,
component discovery, relationship detection, visualization selection, and visual graph layout.
"""

from __future__ import annotations

import hashlib
from typing import Any

from app.core.logging import get_logger
from app.schemas.visual_intelligence import (
    VisualLearningModel,
    VisualValidationError,
)
from app.services.component_discovery_service import ComponentDiscoveryService
from app.services.learning_objective_service import LearningObjectiveService
from app.services.relationship_engine_service import RelationshipEngineService
from app.services.visual_classifier_service import VisualClassifierService
from app.services.visual_validation_service import VisualValidationService
from app.services.visualization_decision_service import VisualizationDecisionService
from app.utils.bounded_cache import BoundedCache

logger = get_logger(__name__)


class VisualIntelligenceService:

    def __init__(
        self,
        classifier: VisualClassifierService | None = None,
        objective_detector: LearningObjectiveService | None = None,
        component_discoverer: ComponentDiscoveryService | None = None,
        relationship_engine: RelationshipEngineService | None = None,
        visualization_decider: VisualizationDecisionService | None = None,
        validator: VisualValidationService | None = None,
    ) -> None:
        self.classifier = classifier or VisualClassifierService()
        self.objective_detector = objective_detector or LearningObjectiveService()
        self.component_discoverer = component_discoverer or ComponentDiscoveryService()
        self.relationship_engine = relationship_engine or RelationshipEngineService()
        self.visualization_decider = visualization_decider or VisualizationDecisionService()
        self.validator = validator or VisualValidationService()
        self._cache: BoundedCache[str, VisualLearningModel] = BoundedCache(
            max_size=200, ttl=1800,
        )

    async def generate_visual_learning_model(
        self,
        content: str,
        title: str | None = None,
        use_cache: bool = True,
    ) -> VisualLearningModel:
        """Analyze educational text content and produce a structured VisualLearningModel."""
        # Step 1: Input Validation
        val_res = self.validator.validate_content(content, title)
        if not val_res.is_valid:
            err = val_res.errors[0] if val_res.errors else VisualValidationError(code="INVALID_INPUT", message="Invalid input")
            raise ValueError(f"Visual Intelligence validation failed: [{err.code}] {err.message}")

        # Step 2: Content Hashing & Cache Lookup
        cache_key = self._generate_cache_key(content, title)
        if use_cache and cache_key in self._cache:
            logger.info("visual_intelligence_cache_hit", cache_key=cache_key)
            return self._cache[cache_key]

        logger.info("visual_intelligence_pipeline_started", title=title or "Untitled")

        # Step 3: Topic Classification
        classification = await self.classifier.classify_topic(content, title)

        # Step 4: Learning Objective Detection
        objectives = await self.objective_detector.detect_objectives(content, title)

        # Step 5: Component Discovery
        components = await self.component_discoverer.discover_components(content, title)

        # Step 6: Relationship Engine
        relationships = await self.relationship_engine.detect_relationships(components, content)

        # Step 7: Visualization Decision Engine
        decision = await self.visualization_decider.decide_visualization(classification, components, title)

        # Step 8: Visual Graph Node/Edge Layout Construction
        layout_direction = self._determine_layout_direction(decision.visualization_type)
        visual_nodes, visual_edges, suggested_layout = self.relationship_engine.build_graph_layout(
            components, relationships, layout_direction=layout_direction
        )

        # Step 9: Simulation Candidate & Quiz Focus Identification
        sim_candidates = self._identify_simulation_candidates(classification, components)
        quiz_focus = self._identify_quiz_focus_areas(components, relationships)
        examples = self._extract_examples(content, components)

        # Step 10: Model Assembly
        model = VisualLearningModel(
            topic=title or (components[0].name if components else "Educational Topic"),
            classification=classification,
            learning_objectives=objectives,
            visualization_decision=decision,
            components=components,
            relationships=relationships,
            visual_nodes=visual_nodes,
            visual_edges=visual_edges,
            suggested_layout=suggested_layout,
            examples=examples,
            future_simulation_candidates=sim_candidates,
            quiz_focus_areas=quiz_focus,
        )

        # Step 11: Validate Model Completeness
        model_val = self.validator.validate_model(model)
        if not model_val.is_valid:
            logger.warning("visual_learning_model_has_validation_warnings", warnings=model_val.warnings)

        # Cache Result
        if use_cache:
            self._cache.set(cache_key, model)

        logger.info("visual_intelligence_pipeline_completed", topic=model.topic, node_count=len(visual_nodes))
        return model

    @staticmethod
    def _generate_cache_key(content: str, title: str | None) -> str:
        raw = f"{title or ''}:{content}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _determine_layout_direction(vis_type: Any) -> str:
        val = getattr(vis_type, "value", str(vis_type)).lower()
        if "timeline" in val or "steps" in val or "flow" in val:
            return "horizontal"
        if "hierarchy" in val or "tree" in val:
            return "vertical"
        if "mind" in val or "network" in val or "cycle" in val:
            return "radial"
        return "horizontal"

    @staticmethod
    def _identify_simulation_candidates(classification: Any, components: list[Any]) -> list[str]:
        candidates: list[str] = []
        cat = getattr(classification.primary_category, "value", str(classification.primary_category)).lower()

        if "algorithm" in cat or "sort" in cat:
            candidates.append("Sorting Algorithm Step Simulator")
        if "system architecture" in cat or "cpu" in cat:
            candidates.append("CPU Instruction Execution Simulator")
        if "network" in cat or "data flow" in cat:
            candidates.append("HTTP Packet Routing Simulator")
        if "scientific cycle" in cat or "cycle" in cat:
            candidates.append("Natural Cycle Parameter Simulator")
        if "biology" in cat or "heart" in cat:
            candidates.append("Physiological Flow Simulator")

        if not candidates:
            candidates.append("Interactive Component Step Simulator")

        return candidates

    @staticmethod
    def _identify_quiz_focus_areas(components: list[Any], relationships: list[Any]) -> list[str]:
        focus: list[str] = []
        if components:
            focus.append(f"Component Identification: {components[0].name}")
        if len(components) > 1:
            focus.append(f"Component Roles: {components[1].name}")
        if relationships:
            focus.append(f"Relationship Dynamics: {relationships[0].description}")
        return focus if focus else ["General Component Structure"]

    @staticmethod
    def _extract_examples(content: str, components: list[Any]) -> list[str]:
        examples: list[str] = []
        for comp in components:
            if comp.real_world_analogy:
                examples.append(f"{comp.name}: {comp.real_world_analogy}")
        return examples if examples else ["Real-world application of system components."]
