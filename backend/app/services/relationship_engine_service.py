"""Relationship Engine (Phase 4I.2).

Detects directional and relational graph links (parent-child, sequential flow,
bidirectional, dependency, data flow, communication, cause-effect) and builds
graph-ready visual node and edge schemas.
"""

from __future__ import annotations

import json
import math
from typing import Any

from app.ai.models import AIRequest
from app.ai.service import get_ai_content_service
from app.core.logging import get_logger
from app.schemas.visual_intelligence import (
    ComponentRelationship,
    Dimensions,
    DiscoveredComponent,
    LayoutSuggestion,
    Position,
    RelationshipType,
    VisualEdgeSchema,
    VisualNodeSchema,
)
from app.services.visual_prompts import RELATIONSHIP_SYSTEM_PROMPT

logger = get_logger(__name__)


class RelationshipEngineService:

    async def detect_relationships(
        self,
        components: list[DiscoveredComponent],
        content: str,
    ) -> list[ComponentRelationship]:
        """Detect graph relationships between components."""
        if not components or len(components) < 2:
            return []

        try:
            ai_service = get_ai_content_service()
            comps_json = json.dumps([{"id": c.component_id, "name": c.name} for c in components])
            prompt = f"Components:\n{comps_json}\n\nContent Context:\n{content[:3000]}"
            req = AIRequest(system_prompt=RELATIONSHIP_SYSTEM_PROMPT, user_prompt=prompt, temperature=0.2, scan_for_injection=True)
            res = await ai_service.generate(req)

            data = json.loads(res.text)
            raw_rels = data.get("relationships", [])
            relationships: list[ComponentRelationship] = []

            for rel in raw_rels:
                relationships.append(
                    ComponentRelationship(
                        source_id=rel.get("source_id", components[0].component_id),
                        target_id=rel.get("target_id", components[1].component_id),
                        relationship_type=self._match_rel_type(rel.get("relationship_type")),
                        description=rel.get("description", "Connected in topic graph"),
                        is_bidirectional=bool(rel.get("is_bidirectional", False)),
                    )
                )

            if relationships:
                return relationships
        except Exception as exc:
            logger.warning("relationship_engine_llm_failed_using_heuristic", error=str(exc))

        return self._heuristic_relationships(components)

    def _heuristic_relationships(self, components: list[DiscoveredComponent]) -> list[ComponentRelationship]:
        """Heuristic fallback relationship builder using dependency analysis.

        - Core→core components get sequential_flow
        - Core→supporting get parent_child (core depends on supporting)
        - Supporting→supporting get dependency
        """
        relationships: list[ComponentRelationship] = []

        for idx, comp in enumerate(components):
            for target_idx in range(idx + 1, len(components)):
                target = components[target_idx]

                if comp.category == "core" and target.category == "core":
                    rel_type = RelationshipType.SEQUENTIAL_FLOW
                    desc = f"{comp.name} leads into {target.name}"
                elif comp.category == "core" and target.category in ("supporting", "peripheral"):
                    rel_type = RelationshipType.PARENT_CHILD
                    desc = f"{comp.name} depends on {target.name}"
                elif comp.category == "supporting" and target.category == "core":
                    rel_type = RelationshipType.DEPENDENCY
                    desc = f"{target.name} builds upon {comp.name}"
                else:
                    rel_type = RelationshipType.DEPENDENCY
                    desc = f"{comp.name} relates to {target.name}"

                relationships.append(
                    ComponentRelationship(
                        source_id=comp.component_id,
                        target_id=target.component_id,
                        relationship_type=rel_type,
                        description=desc,
                        is_bidirectional=False,
                    )
                )

        return relationships

    def build_graph_layout(
        self,
        components: list[DiscoveredComponent],
        relationships: list[ComponentRelationship],
        layout_direction: str = "horizontal",
    ) -> tuple[list[VisualNodeSchema], list[VisualEdgeSchema], LayoutSuggestion]:
        """Build initial visual node positions (x, y) and visual edge schemas."""
        nodes: list[VisualNodeSchema] = []
        edges: list[VisualEdgeSchema] = []

        total = len(components)
        spacing = 220.0
        start_x = 100.0
        start_y = 200.0

        for idx, comp in enumerate(components):
            if layout_direction == "vertical":
                pos = Position(x=start_x, y=start_y + (idx * spacing))
            elif layout_direction == "radial":
                angle = (2 * math.pi * idx) / max(1, total)
                radius = 250.0
                pos = Position(x=500.0 + (radius * math.cos(angle)), y=350.0 + (radius * math.sin(angle)))
            elif layout_direction == "grid":
                cols = 3
                row = idx // cols
                col = idx % cols
                pos = Position(x=start_x + (col * spacing), y=start_y + (row * spacing))
            else:  # horizontal (default)
                pos = Position(x=start_x + (idx * spacing), y=start_y)

            nodes.append(
                VisualNodeSchema(
                    node_id=comp.component_id,
                    label=comp.name,
                    category=comp.category,
                    position=pos,
                    dimensions=Dimensions(width=160.0, height=90.0),
                    importance_weight=comp.importance_weight,
                )
            )

        for idx, rel in enumerate(relationships, start=1):
            edges.append(
                VisualEdgeSchema(
                    edge_id=f"edge_{idx}_{rel.source_id}_to_{rel.target_id}",
                    source_node_id=rel.source_id,
                    target_node_id=rel.target_id,
                    label=rel.description,
                    relationship_type=rel.relationship_type,
                    is_bidirectional=rel.is_bidirectional,
                )
            )

        layout = LayoutSuggestion(
            canvas_dimensions=Dimensions(width=max(1200.0, start_x + (total * spacing)), height=800.0),
            node_spacing=spacing,
            layout_direction=layout_direction,
        )

        return nodes, edges, layout

    @staticmethod
    def _match_rel_type(val: Any) -> RelationshipType:
        if not val or not isinstance(val, str):
            return RelationshipType.SEQUENTIAL_FLOW
        v = val.lower()
        if "parent" in v or "hierarch" in v:
            return RelationshipType.PARENT_CHILD
        if "data" in v:
            return RelationshipType.DATA_FLOW
        if "depend" in v:
            return RelationshipType.DEPENDENCY
        if "comm" in v or "msg" in v:
            return RelationshipType.COMMUNICATION
        if "cause" in v or "effect" in v:
            return RelationshipType.CAUSE_EFFECT
        if "bi" in v or "two" in v:
            return RelationshipType.BIDIRECTIONAL
        return RelationshipType.SEQUENTIAL_FLOW
