"""Visualization Decision Engine (Phase 4I.2).

Selects the optimal visual canvas representation (Flowchart, Timeline, Block Diagram,
Mind Map, Comparison Layout, Decision Tree, Network Graph, Hierarchy, Scientific Cycle,
Algorithm Steps) based on category classification and topic characteristics.
"""

from __future__ import annotations

import json

from app.ai.factory import get_ai_provider
from app.ai.models import AIRequest
from app.core.logging import get_logger
from app.schemas.visual_intelligence import (
    CategoryClassification,
    DiscoveredComponent,
    TopicCategory,
    VisualizationDecision,
    VisualizationType,
)
from app.services.visual_prompts import VISUALIZATION_SELECTION_SYSTEM_PROMPT

logger = get_logger(__name__)

# Rule Matrix Mapping Categories to Optimal Visualization Types
CATEGORY_VISUALIZATION_MATRIX: dict[TopicCategory, tuple[VisualizationType, VisualizationType, str]] = {
    TopicCategory.PROCESS: (VisualizationType.FLOWCHART, VisualizationType.BLOCK_DIAGRAM, "Sequential process stages are clearest in a linear flowchart."),
    TopicCategory.WORKFLOW: (VisualizationType.FLOWCHART, VisualizationType.BLOCK_DIAGRAM, "Task handoffs and roles align best with a flowchart workflow."),
    TopicCategory.ALGORITHM: (VisualizationType.ALGORITHM_STEPS, VisualizationType.FLOWCHART, "Iterative algorithmic execution steps require an animated step view."),
    TopicCategory.SYSTEM_ARCHITECTURE: (VisualizationType.BLOCK_DIAGRAM, VisualizationType.NETWORK_GRAPH, "Module boundaries and hardware/software layers are best shown in a block diagram."),
    TopicCategory.TIMELINE: (VisualizationType.TIMELINE, VisualizationType.FLOWCHART, "Chronological milestones require a horizontal/vertical timeline canvas."),
    TopicCategory.COMPARISON: (VisualizationType.COMPARISON_LAYOUT, VisualizationType.BLOCK_DIAGRAM, "Direct feature matrix contrast is best rendered in a side-by-side comparison layout."),
    TopicCategory.HIERARCHY: (VisualizationType.HIERARCHY, VisualizationType.MIND_MAP, "Parent-child taxonomies map directly to a tree hierarchy."),
    TopicCategory.MIND_MAP: (VisualizationType.MIND_MAP, VisualizationType.NETWORK_GRAPH, "Radiating subtopics from a core idea are best represented as a radial mind map."),
    TopicCategory.NETWORK: (VisualizationType.NETWORK_GRAPH, VisualizationType.BLOCK_DIAGRAM, "Connected nodes and topologies require an interactive network graph."),
    TopicCategory.LIFECYCLE: (VisualizationType.SCIENTIFIC_CYCLE, VisualizationType.FLOWCHART, "State transitions across a lifecycle are best visualized as a cyclic diagram."),
    TopicCategory.CAUSE_AND_EFFECT: (VisualizationType.NETWORK_GRAPH, VisualizationType.FLOWCHART, "Cascading triggers and root causes require a cause-chain network graph."),
    TopicCategory.PROGRAMMING_CONCEPT: (VisualizationType.ALGORITHM_STEPS, VisualizationType.BLOCK_DIAGRAM, "Code structures and memory stack/heap steps require an execution step animation."),
    TopicCategory.MATHEMATICAL_CONCEPT: (VisualizationType.ALGORITHM_STEPS, VisualizationType.MIND_MAP, "Mathematical proofs and formula derivations follow step-by-step logic."),
    TopicCategory.SCIENTIFIC_CYCLE: (VisualizationType.SCIENTIFIC_CYCLE, VisualizationType.FLOWCHART, "Natural feedback loops and ecological/biological cycles require a circular cycle diagram."),
    TopicCategory.BIOLOGY: (VisualizationType.BLOCK_DIAGRAM, VisualizationType.NETWORK_GRAPH, "Anatomical and cellular systems are best represented as interactive block diagrams."),
    TopicCategory.CHEMISTRY: (VisualizationType.BLOCK_DIAGRAM, VisualizationType.FLOWCHART, "Molecular pathways and chemical reactions map to interactive block diagrams."),
    TopicCategory.PHYSICS: (VisualizationType.BLOCK_DIAGRAM, VisualizationType.ALGORITHM_STEPS, "Physical forces and energy transfers are best shown in dynamic block diagrams."),
    TopicCategory.ECONOMICS: (VisualizationType.COMPARISON_LAYOUT, VisualizationType.MIND_MAP, "Market shifts and supply/demand dynamics align with comparison and curve layouts."),
    TopicCategory.BUSINESS_PROCESS: (VisualizationType.FLOWCHART, VisualizationType.BLOCK_DIAGRAM, "Value chains and business funnels map to step flowcharts."),
    TopicCategory.DECISION_TREE: (VisualizationType.DECISION_TREE, VisualizationType.HIERARCHY, "Conditional branching paths map directly to an interactive decision tree."),
    TopicCategory.DATA_FLOW: (VisualizationType.NETWORK_GRAPH, VisualizationType.FLOWCHART, "Data sources, pipelines, and sinks require a data flow network diagram."),
    TopicCategory.CONCEPT_RELATIONSHIP: (VisualizationType.MIND_MAP, VisualizationType.NETWORK_GRAPH, "Semantic concept webs are best explored in a radial mind map."),
}


class VisualizationDecisionService:

    async def decide_visualization(
        self,
        classification: CategoryClassification,
        components: list[DiscoveredComponent],
        topic_title: str | None = None,
    ) -> VisualizationDecision:
        """Select the optimal visualization canvas pattern for a given topic."""
        primary_cat = classification.primary_category

        # Step 1: Rule-based decision matrix
        if primary_cat in CATEGORY_VISUALIZATION_MATRIX:
            vis_type, fallback_type, reason = CATEGORY_VISUALIZATION_MATRIX[primary_cat]
            logger.info("visualization_decided_by_matrix", primary_category=primary_cat.value, vis_type=vis_type.value)
            return VisualizationDecision(
                visualization_type=vis_type,
                reason=reason,
                confidence=round(classification.confidence_score, 2),
                fallback_type=fallback_type,
            )

        # Step 2: Fallback to LLM decision
        try:
            ai_provider = get_ai_provider()
            prompt = f"Topic: {topic_title or 'Educational Topic'}\nCategory: {primary_cat.value}\nComponent Count: {len(components)}"
            req = AIRequest(system_prompt=VISUALIZATION_SELECTION_SYSTEM_PROMPT, user_prompt=prompt, temperature=0.2)
            res = await ai_provider.generate(req)

            data = json.loads(res.text)
            vis_str = data.get("visualization_type", "Block Diagram")
            fallback_str = data.get("fallback_type", "Block Diagram")

            return VisualizationDecision(
                visualization_type=self._match_vis_type(vis_str, VisualizationType.BLOCK_DIAGRAM),
                reason=data.get("reason", "Selected based on structural complexity"),
                confidence=float(data.get("confidence", 0.85)),
                fallback_type=self._match_vis_type(fallback_str, VisualizationType.BLOCK_DIAGRAM),
            )
        except Exception as exc:
            logger.warning("visualization_decision_llm_failed_using_default", error=str(exc))
            return VisualizationDecision(
                visualization_type=VisualizationType.BLOCK_DIAGRAM,
                reason="Default fallback block diagram for multi-component educational topics.",
                confidence=0.50,
                fallback_type=VisualizationType.MIND_MAP,
            )

    @staticmethod
    def _match_vis_type(val: str, default: VisualizationType) -> VisualizationType:
        for vt in VisualizationType:
            if vt.value.lower() == val.lower() or vt.name.lower() == val.lower():
                return vt
        return default
