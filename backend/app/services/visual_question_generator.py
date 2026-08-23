"""Visual Question Generator Service (Phase 4I.6).

Auto-generates interactive visual assessment questions from VisualLearningModel instances.
"""

from __future__ import annotations

import random
import uuid

from app.schemas.visual_assessment import (
    AssessmentDifficulty,
    VisualAssessmentBundle,
    VisualOption,
    VisualQuestion,
    VisualQuestionType,
)
from app.schemas.visual_intelligence import VisualLearningModel


class VisualQuestionGeneratorService:

    def generate_assessment_bundle(
        self,
        model: VisualLearningModel,
        difficulty: AssessmentDifficulty = AssessmentDifficulty.INTERMEDIATE,
        explored_component_ids: list[str] | None = None,
    ) -> VisualAssessmentBundle:
        questions: list[VisualQuestion] = []
        explored_set = set(explored_component_ids or [])

        # Priority focus on skipped components
        components = model.components
        if not components:
            return VisualAssessmentBundle(
                assessment_id=f"assess_{uuid.uuid4().hex[:16]}",
                topic=model.topic,
                difficulty=difficulty,
                questions=[],
            )

        # 1. Hotspot Question (Click Component)
        target_comp = components[0]
        hotspot_opts = [
            VisualOption(
                option_id=c.component_id,
                text=c.name,
                is_correct=(c.component_id == target_comp.component_id),
                target_node_id=c.component_id,
            )
            for c in components
        ]
        questions.append(
            VisualQuestion(
                question_id=f"q_hotspot_{uuid.uuid4().hex[:8]}",
                type=VisualQuestionType.HOTSPOT,
                prompt=f"Click the component responsible for: '{target_comp.short_description}'",
                target_component_id=target_comp.component_id,
                options=hotspot_opts,
                correct_answer=target_comp.component_id,
                explanation=f"{target_comp.name} is responsible for {target_comp.short_description}.",
                difficulty=difficulty,
                related_component_id=target_comp.component_id,
            )
        )

        # 2. Sequence Ordering Question
        if len(components) >= 2:
            correct_order = [c.component_id for c in components[:4]]
            shuffled_order = list(correct_order)
            random.shuffle(shuffled_order)

            seq_options = [
                VisualOption(
                    option_id=cid,
                    text=next((c.name for c in components if c.component_id == cid), cid),
                    target_node_id=cid,
                )
                for cid in shuffled_order
            ]

            questions.append(
                VisualQuestion(
                    question_id=f"q_seq_{uuid.uuid4().hex[:8]}",
                    type=VisualQuestionType.SEQUENCE_ORDERING,
                    prompt=f"Arrange the processing sequence for '{model.topic}' in correct logical order.",
                    options=seq_options,
                    correct_answer=correct_order,
                    explanation=f"The correct data processing sequence flows: {' -> '.join([c.name for c in components[:4]])}.",
                    difficulty=difficulty,
                )
            )

        # 3. Fill Missing Node Question
        if len(components) >= 3:
            missing_comp = components[1]
            distractors = [c for c in components if c.component_id != missing_comp.component_id]
            fill_opts = [
                VisualOption(
                    option_id=missing_comp.component_id,
                    text=missing_comp.name,
                    is_correct=True,
                )
            ]
            for dist in distractors[:3]:
                fill_opts.append(
                    VisualOption(
                        option_id=dist.component_id,
                        text=dist.name,
                        is_correct=False,
                    )
                )
            random.shuffle(fill_opts)

            questions.append(
                VisualQuestion(
                    question_id=f"q_missing_{uuid.uuid4().hex[:8]}",
                    type=VisualQuestionType.FILL_MISSING_NODE,
                    prompt=f"Which component connects between '{components[0].name}' and '{components[2].name}'?",
                    target_component_id=missing_comp.component_id,
                    options=fill_opts,
                    correct_answer=missing_comp.component_id,
                    explanation=f"{missing_comp.name} connects and processes data between {components[0].name} and {components[2].name}.",
                    difficulty=difficulty,
                    related_component_id=missing_comp.component_id,
                )
            )

        # 4. Multiple Choice Input/Output Question
        if components[0].inputs:
            input_name = components[0].inputs[0].name
            mc_opts = [
                VisualOption(
                    option_id=components[0].component_id,
                    text=components[0].name,
                    is_correct=True,
                )
            ]
            for dist in components[1:4]:
                mc_opts.append(
                    VisualOption(
                        option_id=dist.component_id,
                        text=dist.name,
                        is_correct=False,
                    )
                )
            random.shuffle(mc_opts)

            questions.append(
                VisualQuestion(
                    question_id=f"q_mc_{uuid.uuid4().hex[:8]}",
                    type=VisualQuestionType.MULTIPLE_CHOICE,
                    prompt=f"Which component receives the input data contract '{input_name}'?",
                    options=mc_opts,
                    correct_answer=components[0].component_id,
                    explanation=f"{components[0].name} accepts '{input_name}' as its primary input contract.",
                    difficulty=difficulty,
                    related_component_id=components[0].component_id,
                )
            )

        adaptive_reasoning = f"Generated {len(questions)} visual questions. Prioritized skipped components: {[c.name for c in components if c.component_id not in explored_set]}."

        return VisualAssessmentBundle(
            assessment_id=f"assess_{uuid.uuid4().hex[:16]}",
            topic=model.topic,
            difficulty=difficulty,
            questions=questions,
            adaptive_reasoning=adaptive_reasoning,
        )


visual_question_generator = VisualQuestionGeneratorService()
