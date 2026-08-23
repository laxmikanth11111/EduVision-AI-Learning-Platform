"""AI Teaching Script Generator Service for Phase 4K.1 + 4K.2 AI Video Learning Engine.

Generates structured educational lesson scripts broken down into clear pedagogical sections
(introduction, concept explanation, guided walkthrough, reflection questions, key takeaways,
summary, transition narration, next-topic bridge).
"""

from __future__ import annotations

import uuid

from app.schemas.video_engine import ScriptSection, VideoScript
from app.schemas.visual_intelligence import VisualLearningModel


class VideoScriptService:

    def generate_script(
        self,
        topic: str,
        model: VisualLearningModel | None = None,
    ) -> VideoScript:
        sections: list[ScriptSection] = []

        comp_name = model.components[0].name if model and model.components else "Core Processing Engine"

        # 1. Introduction Section
        sections.append(
            ScriptSection(
                section_id=f"sec_intro_{uuid.uuid4().hex[:6]}",
                section_name="introduction",
                heading=f"Introduction to {topic}",
                narration_text=f"Welcome to this educational lesson on {topic}. In this session, we will explore the fundamental mechanics, data flows, and structural relationships that govern how this system operates.",
                bullets=[
                    f"Overview of {topic}",
                    "Key components and role breakdown",
                    "Real-world application context",
                ],
                estimated_duration_ms=6000.0,
            )
        )

        # 2. Concept Explanation
        sections.append(
            ScriptSection(
                section_id=f"sec_concept_{uuid.uuid4().hex[:6]}",
                section_name="concept_explanation",
                heading="Fundamental Theoretical Principles",
                narration_text=f"At its core, {topic} relies on clear inputs, processing stages, and output state updates. Each component operates deterministically to fulfill the system's learning objectives.",
                bullets=[
                    "Deterministic state transitions",
                    "Input-output data contracts",
                    "Control signal propagation",
                ],
                estimated_duration_ms=8000.0,
            )
        )

        # 3. Guided Walkthrough
        sections.append(
            ScriptSection(
                section_id=f"sec_walkthrough_{uuid.uuid4().hex[:6]}",
                section_name="guided_walkthrough",
                heading=f"Guided Walkthrough: {comp_name}",
                narration_text=f"Let's walk step-by-step through {comp_name}. Notice how incoming signals trigger local transformations before forwarding results downstream.",
                bullets=[
                    f"Step 1: Signal arrival at {comp_name}",
                    "Step 2: Processing and flag updates",
                    "Step 3: Forwarding outputs to target nodes",
                ],
                estimated_duration_ms=10000.0,
            )
        )

        # 4. Reflection Questions
        sections.append(
            ScriptSection(
                section_id=f"sec_reflection_{uuid.uuid4().hex[:6]}",
                section_name="reflection_questions",
                heading="Interactive Reflection & Hypotheses",
                narration_text="Before we move forward, consider this: What happens if input data arrives with unexpected delay? How does the architecture maintain consistency?",
                bullets=[
                    "Analyze potential edge cases",
                    "Evaluate synchronization mechanisms",
                    "Test your hypothesis on the interactive canvas",
                ],
                estimated_duration_ms=6000.0,
            )
        )

        # 5. Key Takeaways
        sections.append(
            ScriptSection(
                section_id=f"sec_takeaways_{uuid.uuid4().hex[:6]}",
                section_name="key_takeaways",
                heading="Key Pedagogical Takeaways",
                narration_text="Let's review the main takeaways. First, modular separation ensures reliability. Second, visual feedback clarifies internal execution details.",
                bullets=[
                    "Modular system separation",
                    "Visual inspection aids debugging",
                    "Sequential signal flow controls outcome",
                ],
                estimated_duration_ms=7000.0,
            )
        )

        # 6. Summary & Transition
        sections.append(
            ScriptSection(
                section_id=f"sec_summary_{uuid.uuid4().hex[:6]}",
                section_name="summary",
                heading="Lesson Summary & Next Topic Bridge",
                narration_text=f"You have successfully completed the video lesson on {topic}! In our next lesson, we will build directly upon this foundation to examine complex multi-stage architectures.",
                bullets=[
                    f"Mastered core concepts of {topic}",
                    "Prepared for advanced simulations",
                    "Recommended Next Topic: Advanced Pipeline Synchronization",
                ],
                estimated_duration_ms=7000.0,
            )
        )

        total_words = sum(len(sec.narration_text.split()) for sec in sections)
        est_minutes = round(total_words / 130.0, 2)  # Avg 130 wpm speaking pace

        return VideoScript(
            script_id=f"script_{uuid.uuid4().hex[:8]}",
            topic=topic,
            sections=sections,
            word_count=total_words,
            estimated_total_spoken_minutes=est_minutes,
        )


video_script_service = VideoScriptService()
