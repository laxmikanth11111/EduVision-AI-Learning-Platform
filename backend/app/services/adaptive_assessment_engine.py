"""Adaptive Assessment Engine (Phase 4I.6).

Evaluates user answer submissions, updates difficulty, and computes topic mastery.
"""

from __future__ import annotations

from typing import Any

from app.schemas.visual_assessment import (
    AnswerEvaluationResult,
    AssessmentDifficulty,
    VisualQuestion,
)


class AdaptiveAssessmentEngineService:

    def evaluate_answer(
        self,
        question: VisualQuestion,
        user_answer: Any,
        time_taken_seconds: float = 0.0,
    ) -> AnswerEvaluationResult:
        is_correct = False

        if isinstance(question.correct_answer, list) and isinstance(user_answer, list):
            is_correct = question.correct_answer == user_answer
        elif str(question.correct_answer).strip().lower() == str(user_answer).strip().lower():
            is_correct = True

        score = 1.0 if is_correct else 0.0

        # Adapt difficulty recommendation for next questions
        next_diff = question.difficulty
        if is_correct and question.difficulty == AssessmentDifficulty.BEGINNER:
            next_diff = AssessmentDifficulty.INTERMEDIATE
        elif is_correct and question.difficulty == AssessmentDifficulty.INTERMEDIATE:
            next_diff = AssessmentDifficulty.ADVANCED
        elif not is_correct and question.difficulty == AssessmentDifficulty.ADVANCED:
            next_diff = AssessmentDifficulty.INTERMEDIATE
        elif not is_correct and question.difficulty == AssessmentDifficulty.INTERMEDIATE:
            next_diff = AssessmentDifficulty.BEGINNER

        suggested_review = None
        if not is_correct and question.related_component_id:
            suggested_review = f"Review the working mechanisms and data contracts of component: {question.related_component_id}."

        return AnswerEvaluationResult(
            question_id=question.question_id,
            is_correct=is_correct,
            score=score,
            user_answer=user_answer,
            correct_answer=question.correct_answer,
            explanation=question.explanation,
            related_component_id=question.related_component_id,
            suggested_review=suggested_review,
            next_difficulty=next_diff,
        )


adaptive_assessment_engine = AdaptiveAssessmentEngineService()
