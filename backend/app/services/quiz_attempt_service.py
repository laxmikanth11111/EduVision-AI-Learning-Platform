"""Quiz delivery service — validates ownership, manages attempts, evaluates answers."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.database.unit_of_work import UnitOfWork
from app.models.answer_key import AnswerKey
from app.models.quiz import Quiz
from app.models.quiz_attempt import QuizAttempt
from app.models.quiz_content import Question
from app.models.quiz_version import QuizVersion
from app.models.user_answer import UserAnswer
from app.repositories.concept_repository import ConceptRepository
from app.repositories.quiz_repository import (
    AnswerKeyRepository,
    QuestionAttemptRepository,
    QuestionExplanationRepository,
    QuestionRepository,
    QuizAttemptRepository,
    QuizRepository,
    QuizVersionRepository,
    ScoreSummaryRepository,
    UserAnswerRepository,
)
from app.services.adaptive_assessment import (
    RATIONALE_START,
    AdaptiveCandidate,
    AnsweredQuestion,
    order_candidate_questions,
    select_next_question,
)
from shared.constants import QuestionAttemptStatus, ScoringRule

if TYPE_CHECKING:
    from app.schemas.educational_memory import EducationalMemory

logger = get_logger(__name__)

MIN_ADAPTIVE_QUESTIONS = 2


class QuizAttemptService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        self._quiz_repo = QuizRepository(uow.session)
        self._version_repo = QuizVersionRepository(uow.session)
        self._question_repo = QuestionRepository(uow.session)
        self._answer_key_repo = AnswerKeyRepository(uow.session)
        self._explanation_repo = QuestionExplanationRepository(uow.session)
        self._attempt_repo = QuizAttemptRepository(uow.session)
        self._qa_repo = QuestionAttemptRepository(uow.session)
        self._answer_repo = UserAnswerRepository(uow.session)
        self._score_repo = ScoreSummaryRepository(uow.session)

    # ── Ownership ─────────────────────────────────────────────────────────────

    async def assert_quiz_ownership(
        self, quiz_public_id: str, user_id: uuid.UUID
    ) -> Quiz:
        """Return quiz if the authenticated user owns it, else 404.

        Ownership is enforced through the parent presentation, which is the
        top-level ownership unit in the individual-first model: a quiz belongs
        to a presentation and only the presentation's owner may access it.
        A missing quiz, missing/orphaned presentation, or a non-owner are all
        reported identically as 404 so no information leaks about whether
        another user's resource exists.
        """
        from sqlalchemy import select

        from app.models.presentation import Presentation

        quiz = await self._quiz_repo.get_by_public_id(quiz_public_id)
        if quiz is None:
            raise NotFoundError(
                message="Quiz not found",
                details={"quiz_id": quiz_public_id},
            )

        stmt = select(Presentation).where(Presentation.id == quiz.presentation_id)
        result = await self._uow.session.execute(stmt)
        presentation = result.scalar_one_or_none()

        if (
            presentation is None
            or presentation.owner_id is None
            or str(presentation.owner_id) != str(user_id)
        ):
            raise NotFoundError(
                message="Quiz not found",
                details={"quiz_id": quiz_public_id},
            )

        return quiz

    async def _get_quiz_with_version(
        self, quiz_public_id: str
    ) -> tuple[Quiz, QuizVersion]:
        quiz = await self._quiz_repo.get_by_public_id_or_raise(quiz_public_id)
        version = await self._version_repo.get_by_quiz_id(quiz.id)
        if version is None:
            raise NotFoundError(
                message="No published quiz version found",
                details={"quiz_id": quiz_public_id},
            )
        return quiz, version

    # ── Retrieve Quiz ─────────────────────────────────────────────────────────

    async def get_quiz(self, quiz_public_id: str) -> dict[str, Any]:
        """Return quiz metadata."""
        quiz = await self._quiz_repo.get_by_public_id_or_raise(quiz_public_id)
        return {
            "id": quiz.public_id,
            "title": quiz.title,
            "description": quiz.description,
            "status": quiz.status,
            "mode": quiz.mode,
            "difficulty": quiz.difficulty,
            "language": quiz.language,
            "question_count": quiz.question_count,
            "attempt_count": quiz.attempt_count,
            "max_attempts_per_user": quiz.max_attempts_per_user,
            "time_limit_minutes": quiz.time_limit_minutes,
            "passing_score": float(quiz.passing_score) if quiz.passing_score else None,
            "shuffle_questions": quiz.shuffle_questions,
            "shuffle_options": quiz.shuffle_options,
            "show_feedback_after": quiz.show_feedback_after,
            "presentation_id": str(quiz.presentation_id),
            "lesson_id": str(quiz.lesson_id) if quiz.lesson_id else None,
            "created_at": quiz.created_at,
        }

    async def list_quizzes_for_presentation(
        self, presentation_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        quizzes = await self._quiz_repo.list_by_presentation(presentation_id)
        return [
            {
                "id": q.public_id,
                "title": q.title,
                "description": q.description,
                "status": q.status,
                "mode": q.mode,
                "difficulty": q.difficulty,
                "question_count": q.question_count,
                "attempt_count": q.attempt_count,
                "max_attempts_per_user": q.max_attempts_per_user,
                "time_limit_minutes": q.time_limit_minutes,
                "passing_score": float(q.passing_score) if q.passing_score else None,
                "presentation_id": str(q.presentation_id),
                "created_at": q.created_at,
            }
            for q in quizzes
        ]

    # ── Start Attempt ─────────────────────────────────────────────────────────

    async def start_attempt(
        self,
        quiz_public_id: str,
        user_id: uuid.UUID,
        *,
        adaptive: bool = False,
    ) -> dict[str, Any]:
        """Start a new quiz attempt (or resume existing in-progress one).

        ``adaptive=True`` requests deterministic adaptive delivery: the question
        order follows the learner's concept mastery (weak concepts first, at a
        difficulty matched to their band) and, once answered, the remaining
        sequence reacts to within-attempt correctness. The mode is persisted on
        the attempt so resume and per-question ``next`` continue adaptively.
        """
        quiz, version = await self._quiz_with_version_for_delivery(quiz_public_id)

        # Check max attempts
        attempt_count = await self._attempt_repo.count_user_attempts(quiz.id, user_id)
        if attempt_count >= quiz.max_attempts_per_user:
            raise ConflictError(
                message="Maximum attempts reached",
                details={
                    "attempt_count": attempt_count,
                    "max_attempts": quiz.max_attempts_per_user,
                },
            )

        # Check for existing active attempt
        active = await self._attempt_repo.find_one(
            quiz_id=quiz.id,
            user_id=user_id,
            status="in_progress",
        )
        if active:
            return await _resume_attempt(
                active, quiz, version, self._question_repo, self._qa_repo
            )

        # Load the question set before creating any attempt row so malformed
        # adaptive requests can be rejected without side effects.
        questions = await self._question_repo.list_by_version_with_options(version.id)
        if adaptive and len(questions) < MIN_ADAPTIVE_QUESTIONS:
            raise ValidationError(
                message="Adaptive assessment requires at least two questions",
                details={
                    "question_count": len(questions),
                    "quiz_id": quiz_public_id,
                },
            )

        # Deterministic adaptive ordering (no randomness) or fixed delivery order.
        adaptive_active = bool(adaptive)
        adaptive_rationale: str | None = None
        delivery_order = list(questions)
        if adaptive_active:
            ordered_public_ids = await self._adaptive_ordered_question_ids(
                version.id, questions, user_id
            )
            by_public = {q.public_id: q for q in questions}
            delivery_order = [by_public[pid] for pid in ordered_public_ids]
            adaptive_rationale = RATIONALE_START

        # Create new attempt. The production schema (0005) declares max_score
        # and time_spent_seconds NOT NULL, so both are populated at creation.
        attempt_number = attempt_count + 1
        max_score_total = sum(float(q.points) for q in questions)
        attempt = await self._attempt_repo.create(
            quiz_id=quiz.id,
            quiz_version_id=version.id,
            user_id=user_id,
            attempt_number=attempt_number,
            status="in_progress",
            is_practice=quiz.mode == "practice",
            adaptive=adaptive_active,
            max_score=max_score_total,
            time_spent_seconds=0,
            started_at=datetime.now(UTC),
        )

        # Create question attempts in delivery order; the attempt's position
        # column mirrors that order (fixed mode: canonical question position).
        question_responses = []
        for delivery_index, q in enumerate(delivery_order, start=1):
            await self._qa_repo.create(
                attempt_id=attempt.id,
                question_id=q.id,
                position=delivery_index,
                status=QuestionAttemptStatus.UNANSWERED.value,
                points_possible=float(q.points),
            )
            question_responses.append(_question_to_response(q))

        # Update quiz attempt count atomically on the database so concurrent
        # start_attempt calls cannot lose an increment (the denormalized
        # counter is separate from the per-user limit check above).
        from sqlalchemy import update

        await self._uow.session.execute(
            update(Quiz)
            .where(Quiz.id == quiz.id)
            .values(attempt_count=Quiz.attempt_count + 1)
        )

        return {
            "attempt_id": attempt.public_id,
            "quiz_id": quiz.public_id,
            "quiz_version_id": version.public_id,
            "attempt_number": attempt.attempt_number,
            "status": attempt.status,
            "started_at": attempt.started_at,
            "questions": question_responses,
            "adaptive": adaptive_active,
            "adaptive_rationale": adaptive_rationale,
        }

    async def _quiz_with_version_for_delivery(
        self, quiz_public_id: str
    ) -> tuple[Quiz, QuizVersion]:
        quiz, version = await self._get_quiz_with_version(quiz_public_id)
        if quiz.status == "archived":
            raise NotFoundError(
                message="Quiz is archived",
                details={"quiz_id": quiz_public_id},
            )
        return quiz, version

    # ── Submit Single Answer ──────────────────────────────────────────────────

    async def submit_answer(
        self,
        quiz_public_id: str,
        attempt_public_id: str,
        question_public_id: str,
        user_id: uuid.UUID,
        *,
        option_ids: list[str] | None = None,
        text_value: str | None = None,
        matching_pairs: list[dict[str, str]] | None = None,
        order_values: list[str] | None = None,
        time_spent_seconds: int | None = None,
    ) -> dict[str, Any]:
        """Submit or update the answer for a single question within an attempt."""
        attempt = await self._get_active_attempt(quiz_public_id, attempt_public_id, user_id)
        question = await self._get_question_in_version(
            question_public_id, attempt.quiz_version_id
        )

        # Find or create question attempt
        qa = await self._qa_repo.get_by_attempt_and_question(attempt.id, question.id)
        if qa is None:
            raise NotFoundError(
                message="Question not found in this attempt",
                details={"question_id": question_public_id},
            )

        # Persist elapsed time when the client provides it (schema 0005 keeps
        # question_attempts.time_spent_seconds NOT NULL; default 0 at creation).
        if time_spent_seconds is not None:
            qa.time_spent_seconds = max(0, time_spent_seconds)

        # Delete existing answer if re-answering
        existing_answer = await self._answer_repo.get_by_question_attempt(qa.id)
        if existing_answer:
            await self._uow.session.delete(existing_answer)
            await self._uow.session.flush()

        # Create user answer
        await self._answer_repo.create(
            attempt_id=attempt.id,
            question_attempt_id=qa.id,
            answer_type=question.question_type,
            option_ids=option_ids,
            text_value=text_value,
            matching_pairs=matching_pairs,
            order_values=order_values,
        )

        # Update question attempt status
        qa.status = QuestionAttemptStatus.ANSWERED.value

        return {
            "question_id": question.public_id,
            "status": qa.status,
            "saved": True,
        }

    # ── Submit Quiz ───────────────────────────────────────────────────────────

    async def submit_quiz(
        self,
        quiz_public_id: str,
        attempt_public_id: str,
        user_id: uuid.UUID,
        *,
        answers: list[dict[str, Any]] | None = None,
        time_spent_seconds: int | None = None,
    ) -> dict[str, Any]:
        """Submit all answers and finalize the quiz attempt."""
        attempt = await self._get_active_attempt(quiz_public_id, attempt_public_id, user_id)
        quiz = await self._quiz_repo.get_by_public_id_or_raise(quiz_public_id)

        # Process any bulk answers first
        if answers:
            for ans in answers:
                await self.submit_answer(
                    quiz_public_id,
                    attempt_public_id,
                    ans["question_id"],
                    user_id,
                    option_ids=ans.get("option_ids"),
                    text_value=ans.get("text_value"),
                    matching_pairs=ans.get("matching_pairs"),
                    order_values=ans.get("order_values"),
                )

        # Load all question attempts
        question_attempts = await self._qa_repo.list_by_attempt(attempt.id)
        if not question_attempts:
            raise ValidationError(message="No questions found in this attempt")

        # Load answer keys for all questions
        question_ids = [qa.question_id for qa in question_attempts]
        answer_keys = await self._answer_key_repo.get_by_question_ids(question_ids)
        answer_keys_map = {ak.question_id: ak for ak in answer_keys}

        # Load questions for point values
        questions = await self._question_repo.list_by_version_with_options(attempt.quiz_version_id)
        questions_map = {q.id: q for q in questions}

        # Bulk-load the per-question detail tables once instead of issuing a
        # separate query inside the evaluation loop (prevents N+1 growth as the
        # number of questions scales).
        qa_ids = [qa.id for qa in question_attempts]
        question_ids = list({qa.question_id for qa in question_attempts})
        user_answers_map = {
            ua.question_attempt_id: ua
            for ua in await self._answer_repo.list_by_question_attempts(qa_ids)
        }
        explanations_map = {
            exp.question_id: exp
            for exp in await self._explanation_repo.get_by_question_ids(question_ids)
        }
        concept_ids = {q.concept_id for q in questions if q.concept_id}
        concept_names: dict[uuid.UUID, str] = {}
        concept_public: dict[uuid.UUID, str] = {}
        if concept_ids:
            try:
                concepts = await ConceptRepository(self._uow.session).list_by_ids(
                    sorted(concept_ids)
                )
                concept_names = {c.id: c.name for c in concepts}
                # Map internal concept ids -> public ids so quiz-derived mastery is
                # recorded under the same public_id keys the review/recommendation
                # engine reads (NG-3 loop closure).
                concept_public = {c.id: str(c.public_id) for c in concepts}
            except Exception:
                logger.warning(
                    "quiz_concept_name_preload_failed",
                    quiz_id=quiz.public_id,
                )

        # Evaluate each question
        total_earned = 0.0
        total_possible = 0.0
        correct_count = 0
        incorrect_count = 0
        partially_correct_count = 0
        unanswered_count = 0
        feedback_list = []

        for qa in question_attempts:
            question = questions_map.get(qa.question_id)
            answer_key = answer_keys_map.get(qa.question_id)
            user_answer = user_answers_map.get(qa.id)

            points_possible = float(question.points) if question else 1.0
            total_possible += points_possible

            if user_answer is None or qa.status == QuestionAttemptStatus.UNANSWERED.value:
                unanswered_count += 1
                qa.status = QuestionAttemptStatus.UNANSWERED.value
                concept_id_str = str(question.concept_id) if question and question.concept_id else None
                feedback_list.append({
                    "question_id": question.public_id if question else str(qa.question_id),
                    "position": qa.position,
                    "is_correct": None,
                    "points_earned": 0,
                    "points_possible": points_possible,
                    "explanation": None,
                    "correct_answer": None,
                    "concept_id": concept_id_str,
                    "concept_name": None,
                })
                continue

            # Evaluate
            is_correct, points = _evaluate_answer(
                user_answer, answer_key, points_possible
            )
            qa.is_correct = is_correct
            qa.points_earned = points
            total_earned += points

            if is_correct:
                correct_count += 1
            elif points > 0:
                partially_correct_count += 1
            else:
                incorrect_count += 1

            # Load explanation
            explanation_text = None
            if answer_key:
                explanation_obj = explanations_map.get(qa.question_id)
                if explanation_obj is not None:
                    explanation_text = explanation_obj.explanation

            correct_answer = _extract_correct_answer(answer_key, question) if answer_key else None

            # Resolve concept name from Question model
            concept_id = question.concept_id if question else None
            concept_id_str = str(concept_id) if concept_id else None
            concept_name = concept_names.get(concept_id) if concept_id else None

            feedback_list.append({
                "question_id": question.public_id if question else str(qa.question_id),
                "position": qa.position,
                "is_correct": is_correct,
                "points_earned": points,
                "points_possible": points_possible,
                "explanation": explanation_text,
                "correct_answer": correct_answer,
                "concept_id": concept_id_str,
                "concept_name": concept_name,
            })

        # Calculate final score
        percent = (total_earned / total_possible * 100) if total_possible > 0 else 0.0
        passed = (
            quiz.passing_score is not None
            and percent >= float(quiz.passing_score)
        ) if quiz.passing_score else None

        # Update attempt
        attempt.status = "completed"
        attempt.score = total_earned
        attempt.max_score = total_possible
        attempt.percent_score = percent
        attempt.time_spent_seconds = max(0, time_spent_seconds or 0)
        attempt.completed_at = datetime.now(UTC)

        # Create score summary
        await self._score_repo.create(
            attempt_id=attempt.id,
            total_points=total_possible,
            earned_points=total_earned,
            percent=percent,
            correct_count=correct_count,
            incorrect_count=incorrect_count,
            partially_correct_count=partially_correct_count,
            unanswered_count=unanswered_count,
        )

        # Update educational memory with concept mastery from quiz results
        await self._update_concept_mastery(
            user_id=user_id,
            quiz=quiz,
            feedback_list=feedback_list,
            percent_score=percent,
            concept_public=concept_public,
        )

        # Generate recommendations based on updated mastery
        recommendations = None
        lesson_public_id: str | None = None
        try:
            from sqlalchemy import select as _sel

            from app.models.generated_lesson import GeneratedLesson
            from app.services.educational_memory_service import educational_memory_service
            from app.services.recommendation_engine import generate_recommendations

            user_str = str(user_id)
            memory = await educational_memory_service.load_from_db(self._uow.session, user_str)
            recommendation = generate_recommendations(user_str, memory)
            recommendations = recommendation.model_dump()

            # Resolve the quiz's bound lesson public id once (single round trip, no
            # N+1) so the UI can deep-link the next action to the real player.
            if quiz.lesson_id is not None:
                lesson_public_id = (
                    await self._uow.session.execute(
                        _sel(GeneratedLesson.public_id).where(
                            GeneratedLesson.id == quiz.lesson_id
                        )
                    )
                ).scalar_one_or_none()
            # Stain every serialized action with a usable lesson deep-link (NG-1).
            if recommendations and lesson_public_id:
                rec_actions = recommendations.get("actions") or []
                for action in rec_actions:
                    meta = dict(action.get("metadata") or {})
                    meta["lesson_id"] = lesson_public_id
                    action["metadata"] = meta
                next_act = recommendations.get("next_action")
                if isinstance(next_act, dict):
                    nmeta = dict(next_act.get("metadata") or {})
                    nmeta["lesson_id"] = lesson_public_id
                    next_act["metadata"] = nmeta
        except Exception:
            pass

        return {
            "attempt_id": attempt.public_id,
            "quiz_id": quiz.public_id,
            "lesson_id": lesson_public_id,
            "status": "completed",
            "attempt_number": attempt.attempt_number,
            "score": total_earned,
            "max_score": total_possible,
            "percent_score": percent,
            "time_spent_seconds": time_spent_seconds,
            "started_at": attempt.started_at,
            "completed_at": attempt.completed_at,
            "passed": passed,
            "score_breakdown": {
                "total_points": total_possible,
                "earned_points": total_earned,
                "percent": percent,
                "correct_count": correct_count,
                "incorrect_count": incorrect_count,
                "partially_correct_count": partially_correct_count,
                "unanswered_count": unanswered_count,
            },
            "question_feedback": feedback_list,
            "recommendations": recommendations,
        }

    # ── Next Question (adaptive delivery) ────────────────────────────────────

    async def get_next_question(
        self,
        quiz_public_id: str,
        attempt_public_id: str,
        user_id: uuid.UUID,
        *,
        answer: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return the next question for an in-progress attempt.

        In adaptive mode the selection reacts to the answers submitted so far
        (correct answers lift the concept target, incorrect ones lower it), so
        the delivered sequence genuinely changes within the same attempt. In
        fixed mode the next unanswered question is returned by position.

        An optional ``answer`` (for the question the learner just completed) is
        persisted first so the selection reflects it. Everything is
        user-scoped: only the authenticated owner's attempt and questions are
        ever considered.
        """
        attempt = await self._get_active_attempt(quiz_public_id, attempt_public_id, user_id)
        quiz = await self._quiz_repo.get_by_public_id_or_raise(quiz_public_id)

        if answer:
            await self.submit_answer(
                quiz_public_id,
                attempt_public_id,
                answer["question_id"],
                user_id,
                option_ids=answer.get("option_ids"),
                text_value=answer.get("text_value"),
                matching_pairs=answer.get("matching_pairs"),
                order_values=answer.get("order_values"),
            )

        qas = await self._qa_repo.list_by_attempt(attempt.id)
        if not qas:
            raise ValidationError(message="No questions found in this attempt")

        questions = await self._question_repo.list_by_version_with_options(attempt.quiz_version_id)
        questions_map = {q.id: q for q in questions}
        questions_by_public = {q.public_id: q for q in questions}

        answered_qas = [qa for qa in qas if qa.status == QuestionAttemptStatus.ANSWERED.value]
        unanswered_qas = [qa for qa in qas if qa.status != QuestionAttemptStatus.ANSWERED.value]

        concept_map = await self._concept_public_map(questions)
        memory = await self._load_memory(user_id)
        mastery_by_concept = memory.concept_records
        mastery_default = 50.0

        # Evaluated within-attempt history (correctness resolved server-side).
        answered_history: list[AnsweredQuestion] = []
        if answered_qas:
            answer_keys = await self._answer_key_repo.get_by_question_ids(
                [qa.question_id for qa in answered_qas]
            )
            answer_keys_map = {ak.question_id: ak for ak in answer_keys}
            user_answers = await self._answer_repo.list_by_question_attempts(
                [qa.id for qa in answered_qas]
            )
            user_answers_map = {ua.question_attempt_id: ua for ua in user_answers}
            for qa in answered_qas:
                question = questions_map.get(qa.question_id)
                user_answer = user_answers_map.get(qa.id)
                is_correct = False
                if question is not None and user_answer is not None:
                    answer_key = answer_keys_map.get(qa.question_id)
                    is_correct, _ = _evaluate_answer(
                        user_answer, answer_key, float(question.points)
                    )
                answered_history.append(
                    AnsweredQuestion(
                        concept_key=concept_map.get(question.concept_id)
                        if question is not None and question.concept_id
                        else None,
                        is_correct=bool(is_correct),
                    )
                )

        candidates: list[AdaptiveCandidate] = []
        for qa in unanswered_qas:
            question = questions_map.get(qa.question_id)
            if question is None:
                continue
            concept_key = (
                concept_map.get(question.concept_id) if question.concept_id else None
            )
            mastery = mastery_default
            if concept_key:
                record = mastery_by_concept.get(concept_key)
                if record is not None:
                    mastery = record.mastery_score
            candidates.append(
                AdaptiveCandidate(
                    question_public_id=question.public_id,
                    position=int(question.position),
                    difficulty=question.difficulty,
                    bloom_level=question.bloom_level,
                    concept_key=concept_key,
                    mastery_score=mastery,
                )
            )

        answered_count = len(answered_qas)
        remaining_count = len(unanswered_qas)
        if remaining_count == 0:
            return {
                "attempt_id": attempt.public_id,
                "quiz_id": quiz.public_id,
                "adaptive": bool(attempt.adaptive),
                "adaptive_rationale": None,
                "next_question": None,
                "answered_count": answered_count,
                "remaining_count": 0,
                "completed": True,
            }

        selected: Question | None = None
        adaptive_rationale: str | None = None
        completed = False
        if attempt.adaptive:
            next_candidate, adaptive_rationale = select_next_question(
                candidates, answered_history
            )
            if next_candidate is not None:
                selected = questions_by_public.get(next_candidate.question_public_id)
        else:
            next_qa = min(unanswered_qas, key=lambda qa: qa.position)
            selected = questions_map.get(next_qa.question_id)

        completed = True if selected is None else remaining_count == 1

        return {
            "attempt_id": attempt.public_id,
            "quiz_id": quiz.public_id,
            "adaptive": bool(attempt.adaptive),
            "adaptive_rationale": adaptive_rationale,
            "next_question": _question_to_response(selected) if selected else None,
            "answered_count": answered_count,
            "remaining_count": remaining_count,
            "completed": completed,
        }

    # ── Get Attempt Result ────────────────────────────────────────────────────

    async def get_attempt(
        self,
        quiz_public_id: str,
        attempt_public_id: str,
        user_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Get the result of a quiz attempt."""
        quiz = await self._quiz_repo.get_by_public_id_or_raise(quiz_public_id)
        attempt = await self._attempt_repo.get_by_public_id_or_raise(attempt_public_id)

        # Verify the attempt belongs to this user
        if str(attempt.user_id) != str(user_id):
            raise NotFoundError(
                message="Quiz attempt not found",
                details={"attempt_id": attempt_public_id},
            )
        if str(attempt.quiz_id) != str(quiz.id):
            raise NotFoundError(
                message="Quiz attempt does not belong to this quiz",
                details={"attempt_id": attempt_public_id, "quiz_id": quiz_public_id},
            )

        # Build result
        result: dict[str, Any] = {
            "attempt_id": attempt.public_id,
            "quiz_id": quiz.public_id,
            "status": attempt.status,
            "attempt_number": attempt.attempt_number,
            "score": float(attempt.score) if attempt.score is not None else None,
            "max_score": float(attempt.max_score) if attempt.max_score is not None else None,
            "percent_score": float(attempt.percent_score) if attempt.percent_score is not None else None,
            "time_spent_seconds": attempt.time_spent_seconds,
            "started_at": attempt.started_at,
            "completed_at": attempt.completed_at,
        }

        # If completed, include feedback
        if attempt.status == "completed":
            score_summary = await self._score_repo.get_by_attempt(attempt.id)
            if score_summary:
                passed = (
                    quiz.passing_score is not None
                    and float(score_summary.percent) >= float(quiz.passing_score)
                ) if quiz.passing_score else None
                result["passed"] = passed
                result["score_breakdown"] = {
                    "total_points": float(score_summary.total_points),
                    "earned_points": float(score_summary.earned_points),
                    "percent": float(score_summary.percent),
                    "correct_count": score_summary.correct_count,
                    "incorrect_count": score_summary.incorrect_count,
                    "partially_correct_count": score_summary.partially_correct_count,
                    "unanswered_count": score_summary.unanswered_count,
                }

            # Include per-question feedback if show_feedback_after is enabled
            if quiz.show_feedback_after:
                question_attempts = await self._qa_repo.list_by_attempt(attempt.id)
                questions = await self._question_repo.list_by_version_with_options(attempt.quiz_version_id)
                questions_map = {q.id: q for q in questions}
                answer_keys = await self._answer_key_repo.get_by_question_ids(
                    [qa.question_id for qa in question_attempts]
                )
                answer_keys_map = {ak.question_id: ak for ak in answer_keys}
                explanations_map = {
                    exp.question_id: exp
                    for exp in await self._explanation_repo.get_by_question_ids(
                        [qa.question_id for qa in question_attempts]
                    )
                }

                feedback_list = []
                for qa in question_attempts:
                    question = questions_map.get(qa.question_id)
                    explanation_obj = explanations_map.get(qa.question_id)
                    correct_answer = None
                    if qa.question_id in answer_keys_map:
                        correct_answer = _extract_correct_answer(
                            answer_keys_map[qa.question_id], question
                        )
                    feedback_list.append({
                        "question_id": question.public_id if question else str(qa.question_id),
                        "position": qa.position,
                        "is_correct": qa.is_correct,
                        "points_earned": float(qa.points_earned),
                        "points_possible": float(qa.points_possible),
                        "explanation": explanation_obj.explanation if explanation_obj else None,
                        "correct_answer": correct_answer,
                    })
                result["question_feedback"] = feedback_list

        return result

    async def list_attempts(
        self,
        quiz_public_id: str,
        user_id: uuid.UUID,
    ) -> list[dict[str, Any]]:
        """List all attempts for a quiz by a specific user."""
        quiz = await self._quiz_repo.get_by_public_id_or_raise(quiz_public_id)
        attempts = await self._attempt_repo.list_by_quiz_and_user(quiz.id, user_id)
        return [
            {
                "attempt_id": a.public_id,
                "quiz_id": quiz.public_id,
                "status": a.status,
                "attempt_number": a.attempt_number,
                "score": float(a.score) if a.score is not None else None,
                "max_score": float(a.max_score) if a.max_score is not None else None,
                "percent_score": float(a.percent_score) if a.percent_score is not None else None,
                "time_spent_seconds": a.time_spent_seconds,
                "started_at": a.started_at,
                "completed_at": a.completed_at,
                "passed": None,
            }
            for a in attempts
        ]

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _get_question_in_version(
        self, question_public_id: str, quiz_version_id: uuid.UUID
    ) -> Question:
        """Get a question by public_id, ensuring it belongs to the quiz version."""
        from sqlalchemy import select as sel
        stmt = sel(Question).where(
            Question.public_id == question_public_id,
            Question.quiz_version_id == quiz_version_id,
        )
        result = await self._uow.session.execute(stmt)
        question = result.scalar_one_or_none()
        if question is None:
            raise NotFoundError(
                message="Question not found in this quiz version",
                details={"question_id": question_public_id},
            )
        return question

    async def _get_active_attempt(
        self,
        quiz_public_id: str,
        attempt_public_id: str,
        user_id: uuid.UUID,
    ) -> QuizAttempt:
        """Validate and return an active attempt."""
        quiz = await self._quiz_repo.get_by_public_id_or_raise(quiz_public_id)
        attempt = await self._attempt_repo.get_by_public_id_or_raise(attempt_public_id)

        if str(attempt.user_id) != str(user_id):
            raise NotFoundError(
                message="Quiz attempt not found",
                details={"attempt_id": attempt_public_id},
            )
        if str(attempt.quiz_id) != str(quiz.id):
            raise NotFoundError(
                message="Quiz attempt does not belong to this quiz",
                details={"attempt_id": attempt_public_id, "quiz_id": quiz_public_id},
            )
        if attempt.status != "in_progress":
            raise ConflictError(
                message="This attempt has already been submitted",
                details={"attempt_id": attempt_public_id, "status": attempt.status},
            )
        return attempt

    async def _adaptive_ordered_question_ids(
        self,
        quiz_version_id: uuid.UUID,
        questions: list[Question],
        user_id: uuid.UUID,
    ) -> list[str]:
        """Return question public_ids in deterministic adaptive delivery order.

        Weak concepts (band 0) first at matched difficulty, then developing
        (band 1), then mastered (band 2), with difficulty-fit, difficulty,
        Bloom, position and finally public_id as the deterministic tie-breaks.
        No randomness, no AI.
        """
        concept_map = await self._concept_public_map(questions)
        memory = await self._load_memory(user_id)
        candidates = []
        for q in questions:
            concept_key = concept_map.get(q.concept_id) if q.concept_id else None
            mastery = 50.0
            if concept_key:
                record = memory.concept_records.get(concept_key)
                if record is not None:
                    mastery = record.mastery_score
            candidates.append(
                AdaptiveCandidate(
                    question_public_id=q.public_id,
                    position=int(q.position),
                    difficulty=q.difficulty,
                    bloom_level=q.bloom_level,
                    concept_key=concept_key,
                    mastery_score=mastery,
                )
            )
        ordered = order_candidate_questions(candidates)
        return [c.question_public_id for c in ordered]

    async def _concept_public_map(self, questions: list[Question]) -> dict[uuid.UUID, str]:
        """Map internal concept ids -> concept public ids for a question set."""
        concept_ids = {q.concept_id for q in questions if q.concept_id}
        if not concept_ids:
            return {}
        try:
            concepts = await ConceptRepository(self._uow.session).list_by_ids(
                sorted(concept_ids)
            )
        except Exception:
            logger.warning("quiz_concept_public_map_failed")
            return {}
        return {c.id: str(c.public_id) for c in concepts}

    async def _load_memory(self, user_id: uuid.UUID) -> EducationalMemory:
        """Load (or create) the learner's educational memory (cache-backed)."""
        from app.services.educational_memory_service import educational_memory_service

        return await educational_memory_service.load_from_db(self._uow.session, str(user_id))

    async def _update_concept_mastery(
        self,
        user_id: uuid.UUID,
        quiz: Quiz,
        feedback_list: list[dict[str, Any]],
        percent_score: float,
        concept_public: dict[uuid.UUID, str] | None = None,
    ) -> None:
        """Update educational memory with concept mastery from quiz results.

        Aggregates per-question scores into per-concept averages before
        updating, so multiple questions on the same concept produce a
        single averaged mastery score rather than last-write-wins.
        """
        try:
            from app.services.educational_memory_service import educational_memory_service

            user_str = str(user_id)

            # Load existing memory from database
            await educational_memory_service.load_from_db(self._uow.session, user_str)

            # Aggregate scores per concept
            concept_scores: dict[str, dict[str, Any]] = {}
            for fb in feedback_list:
                question_public_id = fb.get("question_id", "")
                concept_id = fb.get("concept_id") or question_public_id
                concept_name = fb.get("concept_name", "")
                is_correct = fb.get("is_correct")

                if is_correct is True:
                    score = 100.0
                elif is_correct is False:
                    score = 0.0
                else:
                    score = 50.0

                # Record mastery under the concept's public_id (the key the review
                # and recommendation engines read) rather than the internal id, so a
                # correct answer actually closes the learner gap (NG-3 loop closure).
                memory_key = concept_id
                if concept_public and fb.get("concept_id"):
                    try:
                        resolved = concept_public.get(uuid.UUID(concept_id))
                    except (ValueError, TypeError):
                        resolved = None
                    if resolved:
                        memory_key = resolved

                if memory_key not in concept_scores:
                    concept_scores[memory_key] = {
                        "scores": [],
                        "name": concept_name or f"Concept {memory_key[:8]}",
                    }
                concept_scores[memory_key]["scores"].append(score)

            # Update mastery once per concept with averaged score
            for concept_id, data in concept_scores.items():
                scores = data["scores"]
                avg_score = sum(scores) / len(scores) if scores else 0.0
                educational_memory_service.update_concept_mastery(
                    user_id=user_str,
                    concept_id=concept_id,
                    concept_name=data["name"],
                    score=avg_score,
                )

            educational_memory_service.add_milestone(
                user_id=user_str,
                title=f"Completed quiz: {quiz.title or 'Untitled'}",
                category="quiz_completed",
                details={
                    "quiz_id": quiz.public_id,
                    "percent_score": percent_score,
                    "total_questions": len(feedback_list),
                },
            )

            # Persist to database
            await educational_memory_service.save_to_db(self._uow.session, user_str)
        except Exception as exc:
            logger.warning("concept_mastery_update_failed", error=str(exc))


# ── Module-level helpers ─────────────────────────────────────────────────────


async def _resume_attempt(
    attempt: QuizAttempt,
    quiz: Quiz,
    version: QuizVersion,
    question_repo: QuestionRepository,
    qa_repo: QuestionAttemptRepository,
) -> dict[str, Any]:
    """Return the data for an existing in-progress attempt.

    Questions are ordered by the attempt's delivery position (identical to the
    canonical question position in fixed mode, and the adaptive order in
    adaptive mode), so a resumed adaptive attempt keeps the same delivery
    sequence the learner saw.
    """
    questions = await question_repo.list_by_version_with_options(version.id)
    question_attempts = await qa_repo.list_by_attempt(attempt.id)
    delivery_by_question = {qa.question_id: qa.position for qa in question_attempts}
    ordered = sorted(questions, key=lambda q: delivery_by_question.get(q.id, q.position))

    return {
        "attempt_id": attempt.public_id,
        "quiz_id": quiz.public_id,
        "quiz_version_id": version.public_id,
        "attempt_number": attempt.attempt_number,
        "status": attempt.status,
        "started_at": attempt.started_at,
        "questions": [_question_to_response(q) for q in ordered],
        "adaptive": bool(attempt.adaptive),
        "adaptive_rationale": RATIONALE_START if attempt.adaptive else None,
    }


def _question_to_response(question: Question) -> dict[str, Any]:
    """Build the delivery payload for a single question (answers never exposed)."""
    return {
        "id": question.public_id,
        "position": question.position,
        "question_type": question.question_type,
        "stem": question.stem,
        "bloom_level": question.bloom_level,
        "difficulty": question.difficulty,
        "points": question.points,
        "scenario_context": question.scenario_context,
        "options": [
            {
                "id": o.public_id,
                "position": o.position,
                "text": o.text,
            }
            for o in sorted(question.options, key=lambda x: x.position)
        ],
    }


def _evaluate_answer(
    user_answer: UserAnswer,
    answer_key: AnswerKey | None,
    points_possible: float,
) -> tuple[bool, float]:
    """Evaluate a single user answer against the answer key.

    Returns (is_correct, points_earned).
    """
    if answer_key is None:
        return False, 0.0

    ak_type = answer_key.answer_type

    if ak_type in ("multiple_choice", "true_false"):
        correct_ids = answer_key.correct_option_ids or []
        user_ids = user_answer.option_ids or []
        is_correct = {str(i) for i in correct_ids} == {str(i) for i in user_ids}
        return is_correct, points_possible if is_correct else 0.0

    if ak_type == "multiple_select":
        correct_ids = {str(i) for i in (answer_key.correct_option_ids or [])}
        user_ids = {str(i) for i in (user_answer.option_ids or [])}
        if correct_ids == user_ids:
            return True, points_possible
        # Partial credit: proportion of correct selections
        if not correct_ids:
            return False, 0.0
        correct_selected = len(correct_ids & user_ids)
        incorrect_selected = len(user_ids - correct_ids)
        ratio = max(0.0, (correct_selected - incorrect_selected) / len(correct_ids))
        points = round(points_possible * ratio, 2)
        return ratio >= 1.0, points

    if ak_type == "fill_blank":
        acceptable = answer_key.acceptable_answers or []
        user_text = (user_answer.text_value or "").strip()
        case_sensitive = answer_key.case_sensitive
        compare = (lambda s: s) if case_sensitive else str.lower

        for acceptable_answer in acceptable:
            scoring_rule = answer_key.scoring_rule or ScoringRule.EXACT.value
            if scoring_rule == ScoringRule.EXACT.value and compare(user_text) == compare(acceptable_answer):
                return True, points_possible
            if scoring_rule == ScoringRule.CONTAINS.value and compare(acceptable_answer) in compare(user_text):
                return True, points_possible
        return False, 0.0

    if ak_type == "short_answer":
        acceptable = answer_key.acceptable_answers or []
        user_text = (user_answer.text_value or "").strip()
        case_sensitive = answer_key.case_sensitive
        compare = (lambda s: s) if case_sensitive else str.lower
        scoring_rule = answer_key.scoring_rule or ScoringRule.EXACT.value

        for acceptable_answer in acceptable:
            if scoring_rule == ScoringRule.EXACT.value and compare(user_text) == compare(acceptable_answer):
                return True, points_possible
            if scoring_rule == ScoringRule.CONTAINS.value and compare(acceptable_answer) in compare(user_text):
                return True, points_possible
        return False, 0.0

    if ak_type == "matching":
        correct_pairs = answer_key.matching_pairs or []
        user_pairs = user_answer.matching_pairs or []
        correct_map = {p.get("left", ""): p.get("right", "") for p in correct_pairs}
        user_map = {p.get("left", ""): p.get("right", "") for p in user_pairs}
        is_correct = correct_map == user_map
        return is_correct, points_possible if is_correct else 0.0

    if ak_type == "ordering":
        correct_order = answer_key.correct_order or []
        user_order = user_answer.order_values or []
        is_correct = [str(i) for i in correct_order] == [str(i) for i in user_order]
        return is_correct, points_possible if is_correct else 0.0

    return False, 0.0


def _extract_correct_answer(
    answer_key: AnswerKey | None,
    question: Question | None,
) -> Any:
    """Extract the correct answer in a portable format for feedback."""
    if answer_key is None:
        return None

    ak_type = answer_key.answer_type

    if ak_type in ("multiple_choice", "multiple_select"):
        return answer_key.correct_option_ids

    if ak_type == "true_false":
        return answer_key.correct_text

    if ak_type in ("fill_blank", "short_answer"):
        return answer_key.acceptable_answers

    if ak_type == "matching":
        return answer_key.matching_pairs

    if ak_type == "ordering":
        return answer_key.correct_order

    return None
