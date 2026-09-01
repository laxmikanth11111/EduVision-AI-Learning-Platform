"""Quiz delivery service — validates ownership, manages attempts, evaluates answers."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.database.unit_of_work import UnitOfWork
from app.models.answer_key import AnswerKey
from app.models.quiz import Quiz
from app.models.quiz_attempt import QuizAttempt
from app.models.quiz_content import Question
from app.models.quiz_version import QuizVersion
from app.models.user_answer import UserAnswer
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
from shared.constants import QuestionAttemptStatus, ScoringRule

logger = get_logger(__name__)


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
    ) -> dict[str, Any]:
        """Start a new quiz attempt (or resume existing in-progress one)."""
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
            return await _resume_attempt(active, quiz, version, self._question_repo)

        # Create new attempt
        attempt_number = attempt_count + 1
        attempt = await self._attempt_repo.create(
            quiz_id=quiz.id,
            quiz_version_id=version.id,
            user_id=user_id,
            attempt_number=attempt_number,
            status="in_progress",
            is_practice=quiz.mode == "practice",
            started_at=datetime.now(UTC),
        )

        # Create question attempts
        questions = await self._question_repo.list_by_version_with_options(version.id)
        question_responses = []
        for q in questions:
            await self._qa_repo.create(
                attempt_id=attempt.id,
                question_id=q.id,
                position=q.position,
                status=QuestionAttemptStatus.UNANSWERED.value,
                points_possible=float(q.points),
            )
            question_responses.append({
                "id": q.public_id,
                "position": q.position,
                "question_type": q.question_type,
                "stem": q.stem,
                "bloom_level": q.bloom_level,
                "difficulty": q.difficulty,
                "points": q.points,
                "scenario_context": q.scenario_context,
                "options": [
                    {
                        "id": o.public_id,
                        "position": o.position,
                        "text": o.text,
                    }
                    for o in sorted(q.options, key=lambda x: x.position)
                ],
            })

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
            user_answer = await self._answer_repo.get_by_question_attempt(qa.id)

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
                explanation_obj = await self._explanation_repo.get_by_question_id(
                    qa.question_id
                )
                if explanation_obj:
                    explanation_text = explanation_obj.explanation

            correct_answer = _extract_correct_answer(answer_key, question) if answer_key else None

            # Resolve concept name from Question model
            concept_id_str = str(question.concept_id) if question and question.concept_id else None
            concept_name = None
            if concept_id_str:
                try:
                    from sqlalchemy import select as sa_select

                    from app.models.concept import Concept as ConceptModel
                    concept_stmt = sa_select(ConceptModel).where(ConceptModel.id == question.concept_id)
                    concept_result = await self._uow.session.execute(concept_stmt)
                    concept_obj = concept_result.scalar_one_or_none()
                    if concept_obj:
                        concept_name = concept_obj.name
                except Exception:
                    pass

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
        attempt.time_spent_seconds = time_spent_seconds
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
        )

        # Generate recommendations based on updated mastery
        recommendations = None
        try:
            from app.services.educational_memory_service import educational_memory_service
            from app.services.recommendation_engine import generate_recommendations
            user_str = str(user_id)
            memory = await educational_memory_service.load_from_db(self._uow.session, user_str)
            recommendation = generate_recommendations(user_str, memory)
            recommendations = recommendation.model_dump()
        except Exception:
            pass

        return {
            "attempt_id": attempt.public_id,
            "quiz_id": quiz.public_id,
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

                feedback_list = []
                for qa in question_attempts:
                    question = questions_map.get(qa.question_id)
                    explanation_obj = await self._explanation_repo.get_by_question_id(qa.question_id)
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

    async def _update_concept_mastery(
        self,
        user_id: uuid.UUID,
        quiz: Quiz,
        feedback_list: list[dict[str, Any]],
        percent_score: float,
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

                if concept_id not in concept_scores:
                    concept_scores[concept_id] = {
                        "scores": [],
                        "name": concept_name or f"Concept {concept_id[:8]}",
                    }
                concept_scores[concept_id]["scores"].append(score)

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
) -> dict[str, Any]:
    """Return the data for an existing in-progress attempt."""
    questions = await question_repo.list_by_version_with_options(version.id)
    question_responses = []
    for q in questions:
        question_responses.append({
            "id": q.public_id,
            "position": q.position,
            "question_type": q.question_type,
            "stem": q.stem,
            "bloom_level": q.bloom_level,
            "difficulty": q.difficulty,
            "points": q.points,
            "scenario_context": q.scenario_context,
            "options": [
                {
                    "id": o.public_id,
                    "position": o.position,
                    "text": o.text,
                }
                for o in sorted(q.options, key=lambda x: x.position)
            ],
        })

    return {
        "attempt_id": attempt.public_id,
        "quiz_id": quiz.public_id,
        "quiz_version_id": version.public_id,
        "attempt_number": attempt.attempt_number,
        "status": attempt.status,
        "started_at": attempt.started_at,
        "questions": question_responses,
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
