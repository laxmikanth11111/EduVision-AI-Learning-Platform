"""Quiz API router — delivery, attempts, answers, and results."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.core.dependencies import get_current_user
from app.database.unit_of_work import UnitOfWork, get_unit_of_work
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.quiz import (
    AttemptResult,
    AttemptSummary,
    GenerateQuizRequest,
    GenerateQuizResponse,
    NextQuestionRequest,
    NextQuestionResponse,
    QuizDetail,
    SingleAnswerRequest,
    StartAttemptRequest,
    StartAttemptResponse,
    SubmitQuizRequest,
)
from app.services.quiz_attempt_service import QuizAttemptService
from app.services.quiz_generation_service import QuizGenerationService

quiz_router = APIRouter(prefix="/quizzes", tags=["Quizzes"])


# ── Quiz Generation ─────────────────────────────────────────────────────────


@quiz_router.post(
    "/generate",
    response_model=APIResponse[GenerateQuizResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Generate a quiz from lesson content using AI",
)
async def generate_quiz(
    request: GenerateQuizRequest,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[GenerateQuizResponse]:
    service = QuizGenerationService(uow)
    result = await service.generate_quiz(
        user_id=user.id,
        lesson_public_id=request.lesson_id,
        num_questions=request.num_questions,
        difficulty=request.difficulty,
    )
    return APIResponse(
        data=GenerateQuizResponse(**result),
        message="Quiz generated successfully",
    )


# ── Quiz CRUD ────────────────────────────────────────────────────────────────


@quiz_router.get(
    "/{quiz_id}",
    response_model=APIResponse[QuizDetail],
)
async def get_quiz(
    quiz_id: str,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[QuizDetail]:
    service = QuizAttemptService(uow)
    await service.assert_quiz_ownership(quiz_id, user.id)
    result = await service.get_quiz(quiz_id)
    return APIResponse(data=QuizDetail(**result))


# ── Attempts ─────────────────────────────────────────────────────────────────


@quiz_router.post(
    "/{quiz_id}/attempts",
    response_model=APIResponse[StartAttemptResponse],
    status_code=status.HTTP_201_CREATED,
)
async def start_attempt(
    quiz_id: str,
    request: StartAttemptRequest | None = None,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[StartAttemptResponse]:
    service = QuizAttemptService(uow)
    await service.assert_quiz_ownership(quiz_id, user.id)
    result = await service.start_attempt(
        quiz_id,
        user.id,
        adaptive=bool(request.adaptive) if request else False,
    )
    return APIResponse(
        data=StartAttemptResponse(**result),
        message="Quiz attempt started",
    )


@quiz_router.post(
    "/{quiz_id}/attempts/{attempt_id}/next",
    response_model=APIResponse[NextQuestionResponse],
    status_code=status.HTTP_200_OK,
)
async def next_question(
    quiz_id: str,
    attempt_id: str,
    request: NextQuestionRequest | None = None,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[NextQuestionResponse]:
    service = QuizAttemptService(uow)
    answer = request.answer.model_dump() if request is not None and request.answer else None
    result = await service.get_next_question(
        quiz_id,
        attempt_id,
        user.id,
        answer=answer,
    )
    return APIResponse(
        data=NextQuestionResponse(**result),
        message="Next question ready",
    )


@quiz_router.get(
    "/{quiz_id}/attempts",
    response_model=APIResponse[list[AttemptSummary]],
)
async def list_attempts(
    quiz_id: str,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[list[AttemptSummary]]:
    service = QuizAttemptService(uow)
    await service.assert_quiz_ownership(quiz_id, user.id)
    results = await service.list_attempts(quiz_id, user.id)
    return APIResponse(data=[AttemptSummary(**r) for r in results])


@quiz_router.get(
    "/{quiz_id}/attempts/{attempt_id}",
    response_model=APIResponse[AttemptResult],
)
async def get_attempt(
    quiz_id: str,
    attempt_id: str,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[AttemptResult]:
    service = QuizAttemptService(uow)
    result = await service.get_attempt(quiz_id, attempt_id, user.id)
    return APIResponse(data=AttemptResult(**result))


# ── Answers ──────────────────────────────────────────────────────────────────


@quiz_router.post(
    "/{quiz_id}/attempts/{attempt_id}/answers/{question_id}",
    response_model=APIResponse[dict],
)
async def submit_single_answer(
    quiz_id: str,
    attempt_id: str,
    question_id: str,
    request: SingleAnswerRequest,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[dict]:
    service = QuizAttemptService(uow)
    result = await service.submit_answer(
        quiz_id,
        attempt_id,
        question_id,
        user.id,
        option_ids=request.option_ids,
        text_value=request.text_value,
        matching_pairs=request.matching_pairs,
        order_values=request.order_values,
        time_spent_seconds=request.time_spent_seconds,
    )
    return APIResponse(data=result, message="Answer saved")


@quiz_router.post(
    "/{quiz_id}/attempts/{attempt_id}/submit",
    response_model=APIResponse[AttemptResult],
    status_code=status.HTTP_200_OK,
)
async def submit_quiz(
    quiz_id: str,
    attempt_id: str,
    request: SubmitQuizRequest | None = None,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[AttemptResult]:
    service = QuizAttemptService(uow)
    answers = None
    time_spent = None
    if request:
        answers = [a.model_dump() for a in request.answers]
        time_spent = request.time_spent_seconds
    result = await service.submit_quiz(
        quiz_id,
        attempt_id,
        user.id,
        answers=answers,
        time_spent_seconds=time_spent,
    )
    return APIResponse(
        data=AttemptResult(**result),
        message="Quiz submitted successfully",
    )
