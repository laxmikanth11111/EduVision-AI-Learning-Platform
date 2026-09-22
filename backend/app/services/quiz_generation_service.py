"""Quiz Generation Service.

Generates quiz questions from lesson content using the AI provider.
Parses the AI response into the QuizPayload contract and persists
questions, answer keys, and explanations to the database.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.database.unit_of_work import UnitOfWork
from app.models.answer_key import AnswerKey
from app.models.generated_block import GeneratedBlock
from app.models.generated_lesson import GeneratedLesson
from app.models.generated_lesson_version import GeneratedLessonVersion
from app.models.question_explanation import QuestionExplanation
from app.models.quiz import Quiz
from app.models.quiz_content import Question, QuestionOption
from app.models.quiz_version import QuizVersion
from app.repositories.concept_repository import ConceptRepository
from app.schemas.quiz_payload import QuizPayload

logger = get_logger(__name__)

QUIZ_GENERATION_PROMPT = """\
You are an expert educational assessment designer. Generate a knowledge-check quiz based on the lesson content below.

LESSON TITLE: {title}
DIFFICULTY: {difficulty}

LESSON CONTENT:
{content}

REQUIREMENTS:
- Generate exactly {num_questions} questions
- Use a mix of question types: multiple_choice, true_false, multiple_select
- Each multiple_choice question needs 4 options with exactly 1 correct
- Each true_false question needs 2 options (True/False)
- Each multiple_select question needs 4 options with 2-3 correct
- Include a brief explanation for each question
- Questions should test understanding, not just recall
- Vary difficulty: some easy, some medium, some hard
- Reference the specific concept each question tests

Return a valid JSON object matching this exact structure:
{{
  "title": "Quiz: {title}",
  "description": "Knowledge check for the lesson on {title}",
  "difficulty": "{difficulty}",
  "passing_score": 70.0,
  "shuffle_questions": true,
  "shuffle_options": true,
  "show_feedback_after": true,
  "max_attempts_per_user": 3,
  "questions": [
    {{
      "id": "q1",
      "type": "multiple_choice",
      "stem": "Question text here?",
      "difficulty": "beginner",
      "bloom_level": "understanding",
      "points": 1,
      "options": [
        {{"id": "opt1", "text": "Option A", "is_correct": false}},
        {{"id": "opt2", "text": "Option B", "is_correct": true}},
        {{"id": "opt3", "text": "Option C", "is_correct": false}},
        {{"id": "opt4", "text": "Option D", "is_correct": false}}
      ],
      "answer_key": {{
        "answer_type": "multiple_choice",
        "correct_option_idxs": [1]
      }},
      "explanation": "Explanation of the correct answer."
    }}
  ]
}}

IMPORTANT: Return ONLY valid JSON. No markdown, no extra text."""


class QuizGenerationService:

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def generate_quiz(
        self,
        user_id: uuid.UUID,
        lesson_public_id: str,
        num_questions: int = 5,
        difficulty: str = "intermediate",
    ) -> dict[str, Any]:
        """Generate a quiz from lesson content using AI.

        Returns the created quiz metadata.
        """
        # 1. Load lesson and its content
        lesson_stmt = select(GeneratedLesson).where(
            GeneratedLesson.public_id == lesson_public_id
        )
        result = await self._uow.session.execute(lesson_stmt)
        lesson = result.scalar_one_or_none()
        if not lesson:
            raise ValidationError(
                message="Lesson not found",
                details={"lesson_id": lesson_public_id},
            )

        # 2. Load lesson blocks for content
        content_text = await self._load_lesson_content(lesson)

        # 3. Build prompt and call AI
        prompt = QUIZ_GENERATION_PROMPT.format(
            title=lesson.title or "Unknown Topic",
            difficulty=difficulty,
            content=content_text[:4000],
            num_questions=num_questions,
        )

        ai_response_text = await self._call_ai(prompt)

        # 4. Parse AI response into QuizPayload
        import json
        try:
            # Strip markdown code fences if present
            cleaned = ai_response_text.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                cleaned = "\n".join(lines[1:])
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

            payload_data = json.loads(cleaned)
            quiz_payload = QuizPayload.model_validate(payload_data)
        except Exception as exc:
            raise ValidationError(
                message=f"AI generated invalid quiz structure: {exc}",
                details={"raw_response": ai_response_text[:500]},
            )

        # 5. Persist to database
        quiz = await self._persist_quiz(
            user_id=user_id,
            lesson=lesson,
            payload=quiz_payload,
        )

        return {
            "quiz_id": quiz.public_id,
            "title": quiz.title,
            "question_count": quiz.question_count,
            "status": quiz.status,
        }

    async def _load_lesson_content(self, lesson: GeneratedLesson) -> str:
        """Load the actual content blocks from the latest lesson version."""
        ver_stmt = (
            select(GeneratedLessonVersion)
            .where(GeneratedLessonVersion.lesson_id == lesson.id)
            .order_by(GeneratedLessonVersion.version.desc())
            .limit(1)
        )
        ver_result = await self._uow.session.execute(ver_stmt)
        version = ver_result.scalar_one_or_none()
        if not version:
            return "(no lesson content available)"

        block_stmt = (
            select(GeneratedBlock)
            .where(GeneratedBlock.lesson_version_id == version.id)
            .order_by(GeneratedBlock.position)
        )
        block_result = await self._uow.session.execute(block_stmt)
        blocks = block_result.scalars().all()

        parts = []
        for b in blocks:
            heading = b.heading or ""
            content = b.content or ""
            parts.append(f"--- {heading} ---\n{content}")

        return "\n\n".join(parts) if parts else "(no lesson content available)"

    async def _call_ai(self, prompt: str) -> str:
        """Call the AI provider with the quiz generation prompt."""
        from app.ai.models import AIRequest, AIResponseFormat
        from app.ai.service import get_ai_content_service

        provider = get_ai_content_service()
        request = AIRequest(
            user_prompt=prompt,
            system_prompt="You are an expert quiz generator. Return valid JSON only.",
            response_format=AIResponseFormat.JSON,
            max_tokens=4096,
            metadata={"purpose": "quiz_generation"},
            scan_for_injection=True,
        )
        response = await provider.generate(request)
        if not response.success or not response.text:
            raise ValidationError(
                message="AI provider failed to generate quiz",
                details={"error": response.error if hasattr(response, "error") else "unknown"},
            )
        return response.text

    async def _persist_quiz(
        self,
        user_id: uuid.UUID,
        lesson: GeneratedLesson,
        payload: QuizPayload,
    ) -> Quiz:
        """Persist the generated quiz, version, questions, answer keys, and explanations."""
        # Create Quiz
        quiz = Quiz(
            presentation_id=lesson.presentation_id,
            user_id=user_id,
            lesson_id=lesson.id,
            status="draft",
            mode="practice",
            title=payload.title,
            description=payload.description,
            difficulty=payload.difficulty,
            language=payload.language,
            passing_score=payload.passing_score,
            time_limit_minutes=payload.time_limit_minutes,
            shuffle_questions=payload.shuffle_questions,
            shuffle_options=payload.shuffle_options,
            show_feedback_after=payload.show_feedback_after,
            max_attempts_per_user=payload.max_attempts_per_user,
            question_count=len(payload.questions),
        )
        self._uow.session.add(quiz)
        await self._uow.flush()

        # Create QuizVersion
        version = QuizVersion(
            quiz_id=quiz.id,
            version=1,
            status="ready",
            title=payload.title,
            description=payload.description,
            difficulty=payload.difficulty,
            provider="ai_generated",
            payload_hash=payload.payload_hash(),
        )
        self._uow.session.add(version)
        await self._uow.flush()

        # Update quiz version pointers
        quiz.latest_version = 1
        quiz.published_version = 1
        quiz.status = "ready"

        # Create Questions, Options, AnswerKeys, Explanations
        concept_repo = ConceptRepository(self._uow.session)
        for idx, qp in enumerate(payload.questions):
            # Resolve concept from meta topic/knowledge_area
            concept_id = await self._resolve_concept(
                concept_repo, qp, lesson
            )

            question = Question(
                quiz_version_id=version.id,
                position=idx + 1,
                question_type=qp.type,
                stem=qp.stem,
                bloom_level=qp.bloom_level,
                difficulty=qp.difficulty,
                points=qp.points,
                scenario_context=qp.scenario_context,
                source_ref=qp.source_ref,
                meta=qp.meta.model_dump() if qp.meta else None,
                concept_id=concept_id,
            )
            self._uow.session.add(question)
            await self._uow.flush()

            # Create options
            option_id_map: dict[str, str] = {}
            if qp.options:
                for opt_idx, opt in enumerate(qp.options):
                    qo = QuestionOption(
                        question_id=question.id,
                        position=opt_idx + 1,
                        text=opt.text,
                        is_correct=opt.is_correct,
                    )
                    self._uow.session.add(qo)
                    await self._uow.flush()
                    if opt.id:
                        option_id_map[opt.id] = qo.public_id

            # Create AnswerKey
            ak = qp.answer_key
            # Map correct_option_idxs to public_ids for the answer key
            correct_ids = None
            if ak.correct_option_idxs is not None and qp.options:
                correct_ids = [
                    option_id_map.get(qp.options[i].id, str(i))
                    for i in ak.correct_option_idxs
                    if i < len(qp.options)
                ]

            answer_key = AnswerKey(
                question_id=question.id,
                answer_type=ak.answer_type or qp.type,
                correct_option_ids=correct_ids,
                acceptable_answers=ak.acceptable_answers,
                scoring_rule=ak.scoring_rule or "exact",
                case_sensitive=ak.case_sensitive,
                matching_pairs=[p.model_dump() for p in ak.pairs] if ak.pairs else None,
                correct_order=ak.correct_order,
            )
            self._uow.session.add(answer_key)

            # Create QuestionExplanation
            if qp.explanation:
                explanation = QuestionExplanation(
                    question_id=question.id,
                    explanation=qp.explanation,
                    reference=qp.source_ref,
                )
                self._uow.session.add(explanation)

        await self._uow.flush()
        logger.info(
            "quiz_generated",
            quiz_id=quiz.public_id,
            question_count=len(payload.questions),
        )
        return quiz

    async def _resolve_concept(
        self,
        concept_repo: ConceptRepository,
        qp: Any,
        lesson: GeneratedLesson,
    ) -> uuid.UUID | None:
        """Resolve a concept for a question from meta topic/knowledge_area.

        Creates the concept if it doesn't exist. Returns concept UUID or None.
        """
        concept_name = None
        if qp.meta:
            concept_name = qp.meta.topic or qp.meta.knowledge_area
        if not concept_name:
            concept_name = lesson.title
        if not concept_name:
            return None

        try:
            concept = await concept_repo.get_or_create(
                concept_name,
                topic=concept_name,
                presentation_id=lesson.presentation_id,
                lesson_id=lesson.id,
            )
            return concept.id
        except Exception:
            return None
