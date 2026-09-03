"""Quiz repository — data access for the quiz delivery pipeline."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.repository import BaseRepository
from app.models.answer_key import AnswerKey
from app.models.question_attempt import QuestionAttempt
from app.models.question_explanation import QuestionExplanation
from app.models.quiz import Quiz
from app.models.quiz_attempt import QuizAttempt
from app.models.quiz_content import Question
from app.models.quiz_version import QuizVersion
from app.models.score_summary import ScoreSummary
from app.models.user_answer import UserAnswer


class QuizRepository(BaseRepository[Quiz]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Quiz)

    async def get_by_public_id(
        self,
        public_id: str,
        load_options: list | None = None,
    ) -> Quiz | None:
        stmt = select(Quiz).where(Quiz.public_id == public_id)
        if load_options:
            stmt = stmt.options(*load_options)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_public_id_or_raise(self, public_id: str) -> Quiz:
        quiz = await self.get_by_public_id(public_id)
        if quiz is None:
            from app.core.exceptions import NotFoundError
            raise NotFoundError(
                message="Quiz not found",
                details={"quiz_id": public_id},
            )
        return quiz

    async def list_by_presentation(
        self,
        presentation_id: uuid.UUID,
        *,
        status: str | None = None,
    ) -> list[Quiz]:
        stmt = select(Quiz).where(Quiz.presentation_id == presentation_id)
        if status:
            stmt = stmt.where(Quiz.status == status)
        stmt = stmt.order_by(Quiz.created_at.desc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_lesson(
        self,
        lesson_id: uuid.UUID,
        *,
        status: str | None = None,
    ) -> list[Quiz]:
        stmt = select(Quiz).where(Quiz.lesson_id == lesson_id)
        if status:
            stmt = stmt.where(Quiz.status == status)
        stmt = stmt.order_by(Quiz.created_at.desc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_published_version(self, quiz_id: uuid.UUID) -> QuizVersion | None:
        stmt = (
            select(QuizVersion)
            .where(QuizVersion.quiz_id == quiz_id, QuizVersion.status == "published")
            .order_by(QuizVersion.version.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def count_user_attempts(
        self, quiz_id: uuid.UUID, user_id: uuid.UUID
    ) -> int:
        stmt = select(func.count()).select_from(QuizAttempt).where(
            QuizAttempt.quiz_id == quiz_id,
            QuizAttempt.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def get_user_active_attempt(
        self,
        quiz_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> QuizAttempt | None:
        stmt = select(QuizAttempt).where(
            QuizAttempt.quiz_id == quiz_id,
            QuizAttempt.user_id == user_id,
            QuizAttempt.status == "in_progress",
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


class QuizVersionRepository(BaseRepository[QuizVersion]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, QuizVersion)

    async def get_by_quiz_id(
        self,
        quiz_id: uuid.UUID,
        *,
        version: int | None = None,
    ) -> QuizVersion | None:
        stmt = select(QuizVersion).where(QuizVersion.quiz_id == quiz_id)
        if version is not None:
            stmt = stmt.where(QuizVersion.version == version)
        else:
            stmt = stmt.order_by(QuizVersion.version.desc()).limit(1)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


class QuestionRepository(BaseRepository[Question]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Question)

    async def list_by_version(
        self,
        quiz_version_id: uuid.UUID,
    ) -> list[Question]:
        stmt = (
            select(Question)
            .where(Question.quiz_version_id == quiz_version_id)
            .order_by(Question.position)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_version_with_options(
        self,
        quiz_version_id: uuid.UUID,
    ) -> list[Question]:
        stmt = (
            select(Question)
            .where(Question.quiz_version_id == quiz_version_id)
            .options(selectinload(Question.options))
            .order_by(Question.position)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_with_options(self, question_id: uuid.UUID) -> Question | None:
        stmt = (
            select(Question)
            .where(Question.id == question_id)
            .options(selectinload(Question.options))
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


class AnswerKeyRepository(BaseRepository[AnswerKey]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, AnswerKey)

    async def get_by_question_id(self, question_id: uuid.UUID) -> AnswerKey | None:
        stmt = select(AnswerKey).where(AnswerKey.question_id == question_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_question_ids(
        self, question_ids: list[uuid.UUID]
    ) -> list[AnswerKey]:
        if not question_ids:
            return []
        stmt = select(AnswerKey).where(AnswerKey.question_id.in_(question_ids))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class QuestionExplanationRepository(BaseRepository[QuestionExplanation]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, QuestionExplanation)

    async def get_by_question_id(
        self, question_id: uuid.UUID
    ) -> QuestionExplanation | None:
        stmt = select(QuestionExplanation).where(
            QuestionExplanation.question_id == question_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_question_ids(
        self, question_ids: list[uuid.UUID]
    ) -> list[QuestionExplanation]:
        if not question_ids:
            return []
        stmt = select(QuestionExplanation).where(
            QuestionExplanation.question_id.in_(question_ids)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class QuizAttemptRepository(BaseRepository[QuizAttempt]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, QuizAttempt)

    async def get_by_public_id(self, public_id: str) -> QuizAttempt | None:
        stmt = select(QuizAttempt).where(QuizAttempt.public_id == public_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_public_id_or_raise(self, public_id: str) -> QuizAttempt:
        attempt = await self.get_by_public_id(public_id)
        if attempt is None:
            from app.core.exceptions import NotFoundError
            raise NotFoundError(
                message="Quiz attempt not found",
                details={"attempt_id": public_id},
            )
        return attempt

    async def count_user_attempts(
        self, quiz_id: uuid.UUID, user_id: uuid.UUID
    ) -> int:
        stmt = select(func.count()).select_from(QuizAttempt).where(
            QuizAttempt.quiz_id == quiz_id,
            QuizAttempt.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def list_by_quiz_and_user(
        self,
        quiz_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> list[QuizAttempt]:
        stmt = (
            select(QuizAttempt)
            .where(QuizAttempt.quiz_id == quiz_id, QuizAttempt.user_id == user_id)
            .order_by(QuizAttempt.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class QuestionAttemptRepository(BaseRepository[QuestionAttempt]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, QuestionAttempt)

    async def list_by_attempt(self, attempt_id: uuid.UUID) -> list[QuestionAttempt]:
        stmt = (
            select(QuestionAttempt)
            .where(QuestionAttempt.attempt_id == attempt_id)
            .order_by(QuestionAttempt.position)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_attempt_and_question(
        self, attempt_id: uuid.UUID, question_id: uuid.UUID
    ) -> QuestionAttempt | None:
        stmt = select(QuestionAttempt).where(
            QuestionAttempt.attempt_id == attempt_id,
            QuestionAttempt.question_id == question_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


class UserAnswerRepository(BaseRepository[UserAnswer]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, UserAnswer)

    async def get_by_question_attempt(
        self, question_attempt_id: uuid.UUID
    ) -> UserAnswer | None:
        stmt = select(UserAnswer).where(
            UserAnswer.question_attempt_id == question_attempt_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_question_attempts(
        self, question_attempt_ids: list[uuid.UUID]
    ) -> list[UserAnswer]:
        if not question_attempt_ids:
            return []
        stmt = select(UserAnswer).where(
            UserAnswer.question_attempt_id.in_(question_attempt_ids)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


StudentAnswerRepository = UserAnswerRepository  # backward compat alias


class ScoreSummaryRepository(BaseRepository[ScoreSummary]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ScoreSummary)

    async def get_by_attempt(self, attempt_id: uuid.UUID) -> ScoreSummary | None:
        stmt = select(ScoreSummary).where(ScoreSummary.attempt_id == attempt_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
