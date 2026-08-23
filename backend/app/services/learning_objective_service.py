"""Learning Objective Detector (Phase 4I.2).

Extracts pedagogical goals, learning objectives, important concepts, prerequisites,
and target learner competencies from educational text.
"""

from __future__ import annotations

import json
import re

from app.ai.factory import get_ai_provider
from app.ai.models import AIRequest
from app.core.logging import get_logger
from app.schemas.visual_intelligence import LearningObjectives
from app.services.visual_prompts import LEARNING_OBJECTIVE_SYSTEM_PROMPT

logger = get_logger(__name__)


class LearningObjectiveService:

    async def detect_objectives(
        self,
        content: str,
        title: str | None = None,
    ) -> LearningObjectives:
        """Extract structured learning objectives from text content."""
        if not content.strip():
            return LearningObjectives(
                main_goal="Understand topic concept",
                learning_objectives=["Understand core topic elements"],
            )

        try:
            ai_provider = get_ai_provider()
            prompt = f"Topic Title: {title or 'General Educational Topic'}\n\nContent:\n{content[:4000]}"
            req = AIRequest(system_prompt=LEARNING_OBJECTIVE_SYSTEM_PROMPT, user_prompt=prompt, temperature=0.3)
            res = await ai_provider.generate(req)

            data = json.loads(res.text)
            return LearningObjectives(
                main_goal=data.get("main_goal", f"Understand {title or 'topic'}"),
                learning_objectives=data.get("learning_objectives", []),
                important_ideas=data.get("important_ideas", []),
                prerequisites=data.get("prerequisites", []),
                expected_outcomes=data.get("expected_outcomes", []),
            )
        except Exception as exc:
            logger.warning("learning_objective_llm_failed_using_heuristic", error=str(exc))
            return self._heuristic_extraction(content, title)

    def _heuristic_extraction(self, content: str, title: str | None) -> LearningObjectives:
        """Deterministic heuristic fallback when LLM is unavailable or offline."""
        topic_name = title or "this topic"

        sentences = re.split(r"[.!?]\s+", content)
        meaningful = [s.strip() for s in sentences if len(s.strip()) > 20]

        # Extract key ideas from the longest sentences (most informative)
        key_ideas = sorted(meaningful, key=len, reverse=True)[:3]

        return LearningObjectives(
            main_goal=f"Understand the core concepts and mechanics of {topic_name}.",
            learning_objectives=[
                f"Identify the key components and definitions of {topic_name}.",
                f"Explain how {topic_name} works step-by-step.",
                f"Apply knowledge of {topic_name} to practical scenarios.",
            ],
            important_ideas=key_ideas if key_ideas else [f"Core principles of {topic_name}"],
            prerequisites=[f"Basic foundational knowledge related to {topic_name}"],
            expected_outcomes=[
                f"Describe the structure and purpose of {topic_name}.",
                f"Analyze relationships between components in {topic_name}.",
            ],
        )
