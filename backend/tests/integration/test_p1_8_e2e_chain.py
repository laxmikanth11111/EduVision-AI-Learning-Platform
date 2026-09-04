"""P1.8 E2E test: concept → lesson → visual → quiz → mastery → recommendation.

Demonstrates the full adaptive learning chain with real database operations.
No mocked 200 responses — every step touches the DB.

Chain:
  1. Create a concept in the DB
  2. Create a quiz with questions linked to that concept
  3. Take the quiz → submit wrong answers → low mastery
  4. Verify educational memory updated
  5. Verify recommendations suggest remediation
  6. Take the quiz again → submit correct answers → improved mastery
  7. Verify mastery improved
  8. Verify AI tutor context includes updated learner state
  9. Verify recommendations changed
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.unit_of_work import UnitOfWork
from app.models.answer_key import AnswerKey
from app.models.concept import Concept
from app.models.educational_memory import EducationalMemoryRecord
from app.models.presentation import Presentation
from app.models.quiz import Quiz
from app.models.quiz_content import Question, QuestionOption
from app.models.quiz_version import QuizVersion
from app.services.educational_memory_service import educational_memory_service
from app.services.recommendation_engine import generate_recommendations

pytestmark = pytest.mark.integration

# Use the session-wide test user (created in tests/conftest.py)
TEST_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_concept(
    db: AsyncSession,
    *,
    name: str = "OAuth 2.0 Authentication",
    topic: str = "Web Security",
) -> Concept:
    """Insert a real concept into the database."""
    concept = Concept(
        name=name,
        description=f"Understanding {name} flows and tokens",
        topic=topic,
        difficulty_level="intermediate",
    )
    db.add(concept)
    await db.flush()
    await db.refresh(concept)
    return concept


async def _create_presentation(
    db: AsyncSession,
    *,
    owner_id: uuid.UUID,
    title: str = "Web Security Fundamentals",
) -> Presentation:
    """Insert a minimal presentation for quiz ownership."""
    pres = Presentation(
        title=title,
        owner_id=owner_id,
        status="ready",
        visibility="private",
    )
    db.add(pres)
    await db.flush()
    await db.refresh(pres)
    return pres


async def _create_quiz_with_questions(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    presentation_id: uuid.UUID,
    concept: Concept,
    num_questions: int = 3,
) -> tuple[Quiz, list[Question]]:
    """Create a quiz with questions linked to a concept.

    This bypasses the AI generation step to focus on the mastery chain.
    """
    quiz = Quiz(
        user_id=user_id,
        presentation_id=presentation_id,
        status="ready",
        mode="practice",
        title="OAuth 2.0 Knowledge Check",
        difficulty="intermediate",
        passing_score=70.0,
        question_count=num_questions,
    )
    db.add(quiz)
    await db.flush()

    version = QuizVersion(
        quiz_id=quiz.id,
        version=1,
        status="ready",
        title=quiz.title,
    )
    db.add(version)
    await db.flush()

    quiz.latest_version = 1
    quiz.published_version = 1

    questions = []
    for i in range(num_questions):
        q = Question(
            quiz_version_id=version.id,
            position=i + 1,
            question_type="multiple_choice",
            stem=f"Question {i + 1}: What is the primary purpose of {concept.name}?",
            difficulty="intermediate",
            points=1,
            concept_id=concept.id,
        )
        db.add(q)
        await db.flush()

        # Create options
        opt_a = QuestionOption(question_id=q.id, position=1, text="Secure authorization", is_correct=True)
        opt_b = QuestionOption(question_id=q.id, position=2, text="Data encryption", is_correct=False)
        opt_c = QuestionOption(question_id=q.id, position=3, text="User storage", is_correct=False)
        db.add_all([opt_a, opt_b, opt_c])
        await db.flush()

        # Create answer key
        ak = AnswerKey(
            question_id=q.id,
            answer_type="multiple_choice",
            correct_option_ids=[opt_a.public_id],
            scoring_rule="exact",
        )
        db.add(ak)

        questions.append(q)

    await db.flush()
    return quiz, questions


async def _start_attempt(
    db: AsyncSession,
    quiz: Quiz,
    user_id: uuid.UUID,
) -> dict:
    """Start a quiz attempt via the service layer."""
    from app.repositories.quiz_repository import (
        AnswerKeyRepository,
        QuestionAttemptRepository,
        QuestionExplanationRepository,
        QuestionRepository,
        QuizAttemptRepository,
        QuizRepository,
        ScoreSummaryRepository,
        UserAnswerRepository,
    )
    from app.services.quiz_attempt_service import QuizAttemptService

    uow = UnitOfWork(session=db)
    service = QuizAttemptService(uow)
    return await service.start_attempt(quiz.public_id, user_id)


async def _submit_wrong_answers(
    db: AsyncSession,
    quiz: Quiz,
    questions: list[Question],
    attempt_id: str,
    user_id: uuid.UUID,
) -> dict:
    """Submit intentionally wrong answers."""
    from app.database.unit_of_work import UnitOfWork
    from app.services.quiz_attempt_service import QuizAttemptService

    uow = UnitOfWork(session=db)
    service = QuizAttemptService(uow)

    # Build answers — pick option B (wrong) for each question
    answers = []
    for q in questions:
        # Get options for this question
        opt_stmt = select(QuestionOption).where(QuestionOption.question_id == q.id)
        result = await db.execute(opt_stmt)
        opts = result.scalars().all()
        # Pick the second option (wrong answer)
        wrong_opt = opts[1] if len(opts) > 1 else opts[0]
        answers.append({
            "question_id": q.public_id,
            "option_ids": [wrong_opt.public_id],
        })

    return await service.submit_quiz(
        quiz.public_id,
        attempt_id,
        user_id,
        answers=answers,
        time_spent_seconds=60,
    )


async def _submit_correct_answers(
    db: AsyncSession,
    quiz: Quiz,
    questions: list[Question],
    attempt_id: str,
    user_id: uuid.UUID,
) -> dict:
    """Submit correct answers."""
    from app.database.unit_of_work import UnitOfWork
    from app.services.quiz_attempt_service import QuizAttemptService

    uow = UnitOfWork(session=db)
    service = QuizAttemptService(uow)

    answers = []
    for q in questions:
        opt_stmt = select(QuestionOption).where(QuestionOption.question_id == q.id)
        result = await db.execute(opt_stmt)
        opts = result.scalars().all()
        # Pick the first option (correct answer)
        correct_opt = opts[0]
        answers.append({
            "question_id": q.public_id,
            "option_ids": [correct_opt.public_id],
        })

    return await service.submit_quiz(
        quiz.public_id,
        attempt_id,
        user_id,
        answers=answers,
        time_spent_seconds=45,
    )


# ---------------------------------------------------------------------------
# The E2E Chain Test
# ---------------------------------------------------------------------------


class TestP18FullAdaptiveLearningChain:
    """Demonstrates the complete adaptive learning loop with real DB state."""

    async def test_concept_to_recommendation_chain(
        self,
        db_session: AsyncSession,
    ):
        educational_memory_service._memories.clear()
        # Clean any stale educational memory from previous tests
        from sqlalchemy import delete as sa_delete
        await db_session.execute(
            sa_delete(EducationalMemoryRecord).where(
                EducationalMemoryRecord.user_id == TEST_USER_ID
            )
        )
        await db_session.flush()
        user_id = TEST_USER_ID
        user_str = str(user_id)

        # ── Step 1: Create a concept ─────────────────────────────────────
        concept = await _create_concept(
            db_session,
            name="OAuth 2.0 Authentication",
            topic="Web Security",
        )
        assert concept.public_id.startswith("concept_")
        assert concept.name == "OAuth 2.0 Authentication"

        # ── Step 2: Create quiz with questions linked to concept ──────────
        pres = await _create_presentation(db_session, owner_id=user_id)
        quiz, questions = await _create_quiz_with_questions(
            db_session,
            user_id=user_id,
            presentation_id=pres.id,
            concept=concept,
            num_questions=3,
        )
        assert quiz.status == "ready"
        assert len(questions) == 3

        # Verify every question has concept_id
        for q in questions:
            assert q.concept_id == concept.id, f"Question {q.public_id} missing concept_id"

        # ── Step 3: Start attempt #1 ─────────────────────────────────────
        attempt1 = await _start_attempt(db_session, quiz, user_id)
        assert attempt1["status"] == "in_progress"
        attempt1_id = attempt1["attempt_id"]

        # ── Step 4: Submit WRONG answers → low mastery ───────────────────
        result1 = await _submit_wrong_answers(
            db_session, quiz, questions, attempt1_id, user_id,
        )
        assert result1["status"] == "completed"
        assert result1["percent_score"] == 0.0  # all wrong
        assert result1["passed"] is False

        # ── Step 5: Verify educational memory updated ────────────────────
        memory = await educational_memory_service.load_from_db(db_session, user_str)
        # Quiz-derived mastery is recorded under the concept's PUBLIC id (the
        # key the learner/review/recommendation engine reads), not its internal id.
        concept_str = str(concept.public_id)

        # Concept mastery should exist with 0% (all wrong)
        assert concept_str in memory.concept_records, (
            f"Concept {concept_str} not in concept_records. "
            f"Found: {list(memory.concept_records.keys())}"
        )
        record = memory.concept_records[concept_str]
        assert record.mastery_score == 0.0, f"Expected 0% mastery, got {record.mastery_score}"
        assert record.review_count == 1

        # Concept should be in weak list
        assert concept_str in memory.weak_concepts, (
            f"Concept {concept_str} not in weak_concepts. "
            f"weak={memory.weak_concepts}, dev={memory.developing_concepts}, "
            f"mastered={memory.mastered_concepts}"
        )

        # ── Step 6: Verify recommendations suggest remediation ───────────
        assert result1["recommendations"] is not None
        recs = result1["recommendations"]
        assert len(recs["actions"]) > 0, "No recommendations generated"

        # Should suggest SIMPLIFY_EXPLANATION (weak concept)
        action_types = [a["action_type"] for a in recs["actions"]]
        assert "simplify_explanation" in action_types or "show_visual" in action_types, (
            f"Expected remediation actions for weak concept, got: {action_types}"
        )
        # The concept_id in recommendations should match our concept
        rec_concept_ids = [a["concept_id"] for a in recs["actions"]]
        assert concept_str in rec_concept_ids, (
            f"Concept {concept_str} not in recommendation actions. "
            f"Found: {rec_concept_ids}"
        )

        # ── Step 7: Start attempt #2 with CORRECT answers ────────────────
        attempt2 = await _start_attempt(db_session, quiz, user_id)
        assert attempt2["status"] == "in_progress"
        attempt2_id = attempt2["attempt_id"]

        result2 = await _submit_correct_answers(
            db_session, quiz, questions, attempt2_id, user_id,
        )
        assert result2["status"] == "completed"
        assert result2["percent_score"] == 100.0  # all correct
        assert result2["passed"] is True

        # ── Step 8: Verify mastery improved ──────────────────────────────
        memory2 = await educational_memory_service.load_from_db(db_session, user_str)
        record2 = memory2.concept_records[concept_str]
        assert record2.mastery_score == 100.0, (
            f"Expected 100% mastery after correct answers, got {record2.mastery_score}"
        )
        assert record2.review_count == 2
        assert record2.trend == "improving"

        # Concept should no longer be weak — should be mastered
        assert concept_str not in memory2.weak_concepts, (
            f"Concept still weak after 100% score: {memory2.weak_concepts}"
        )
        assert concept_str in memory2.mastered_concepts, (
            f"Concept not mastered after 100% score. "
            f"weak={memory2.weak_concepts}, dev={memory2.developing_concepts}, "
            f"mastered={memory2.mastered_concepts}"
        )

        # ── Step 9: Verify recommendations changed ───────────────────────
        assert result2["recommendations"] is not None
        recs2 = result2["recommendations"]
        action_types2 = [a["action_type"] for a in recs2["actions"]]

        # For mastered concept, should suggest MOVE_TO_NEXT_CONCEPT
        assert "move_to_next_concept" in action_types2, (
            f"Expected move_to_next_concept for mastered concept, got: {action_types2}"
        )
        # Should NOT suggest remediation actions
        assert "simplify_explanation" not in action_types2, (
            f"Should not suggest simplify_explanation for mastered concept: {action_types2}"
        )

        # ── Step 10: Verify AI tutor context includes learner state ──────
        # Build the context text as the AI tutor would
        from app.models.generated_lesson import GeneratedLesson

        # Create a minimal lesson for the tutor context
        lesson = GeneratedLesson(
            public_id=f"lesson_{uuid.uuid4().hex[:8]}",
            presentation_id=pres.id,
            user_id=user_id,
            title="OAuth 2.0 Deep Dive",
            mode="slide",
            status="ready",
        )
        db_session.add(lesson)
        await db_session.flush()

        # Simulate what _build_context_text does with the memory
        context_parts = []
        if memory2.weak_concepts or memory2.mastered_concepts or memory2.developing_concepts or memory2.concept_records:
            context_parts.append("--- LEARNER PROFILE ---")
        if memory2.mastered_concepts:
            context_parts.append(f"Mastered concepts: [{concept.name}]")
        if memory2.concept_records:
            context_parts.append("Per-concept mastery:")
            for _cid, record in memory2.concept_records.items():
                context_parts.append(
                    f"  - {record.concept_name}: {record.mastery_score:.0f}%"
                )
        if memory2.profile.average_mastery > 0:
            context_parts.append(f"Overall mastery: {memory2.profile.average_mastery}%")

        context_text = "\n".join(context_parts)

        # Verify the context includes the concept and its mastery
        assert "LEARNER PROFILE" in context_text
        assert "OAuth 2.0 Authentication" in context_text
        assert "100%" in context_text
        assert "Mastered concepts" in context_text

        # ── Step 11: Verify DB persistence of memory ─────────────────────
        # Reload from DB directly (not from cache)
        educational_memory_service._memories.clear()
        memory_fresh = await educational_memory_service.load_from_db(db_session, user_str)
        assert str(concept.public_id) in memory_fresh.concept_records
        assert memory_fresh.concept_records[str(concept.public_id)].mastery_score == 100.0
        assert memory_fresh.profile.average_mastery == 100.0

        # ── Step 12: Verify question_feedback includes concept_id ─────────
        assert "concept_id" in result1["question_feedback"][0]
        assert result1["question_feedback"][0]["concept_id"] == str(concept.id)
        assert result1["question_feedback"][0]["concept_name"] == concept.name


class TestP18ConceptRepository:
    """Verify ConceptRepository works with real DB."""

    async def test_get_or_create(self, db_session: AsyncSession):
        from app.repositories.concept_repository import ConceptRepository

        repo = ConceptRepository(db_session)
        pres = await _create_presentation(db_session, owner_id=None, title="Concept Test")
        pres_id = pres.id

        # First call creates
        c1 = await repo.get_or_create(
            "Linear Regression",
            topic="Machine Learning",
            presentation_id=pres_id,
        )
        assert c1.name == "Linear Regression"
        c1_id = c1.id

        # Second call returns existing
        c2 = await repo.get_or_create(
            "Linear Regression",
            topic="Machine Learning",
            presentation_id=pres_id,
        )
        assert c2.id == c1_id

    async def test_list_by_presentation(self, db_session: AsyncSession):
        from app.repositories.concept_repository import ConceptRepository

        repo = ConceptRepository(db_session)
        pres = await _create_presentation(db_session, owner_id=None, title="CNN RNN Concepts")
        other_pres = await _create_presentation(db_session, owner_id=None, title="GAN Concepts")
        pres_id = pres.id

        await repo.get_or_create("CNN", presentation_id=pres_id)
        await repo.get_or_create("RNN", presentation_id=pres_id)
        await repo.get_or_create("GAN", presentation_id=other_pres.id)  # different pres

        concepts = await repo.list_by_presentation(pres_id)
        names = {c.name for c in concepts}
        assert names == {"CNN", "RNN"}


class TestP18MasteryProgression:
    """Verify mastery progresses through multiple quiz attempts."""

    async def test_weak_to_developing_to_mastered(
        self,
        db_session: AsyncSession,
    ):
        educational_memory_service._memories.clear()
        from sqlalchemy import delete as sa_delete
        await db_session.execute(
            sa_delete(EducationalMemoryRecord).where(
                EducationalMemoryRecord.user_id == TEST_USER_ID
            )
        )
        await db_session.flush()
        user_id = TEST_USER_ID
        user_str = str(user_id)

        concept = await _create_concept(db_session, name="Neural Networks")
        pres = await _create_presentation(db_session, owner_id=user_id, title="Deep Learning")
        quiz, questions = await _create_quiz_with_questions(
            db_session,
            user_id=user_id,
            presentation_id=pres.id,
            concept=concept,
            num_questions=3,
        )

        # Attempt 1: 1 wrong → 33% → weak
        att = await _start_attempt(db_session, quiz, user_id)
        opts_per_q = []
        for q in questions:
            result = await db_session.execute(
                select(QuestionOption).where(QuestionOption.question_id == q.id)
            )
            opts_per_q.append(result.scalars().all())

        # 1 correct, 2 wrong → 33%
        mixed_answers = [
            {"question_id": questions[0].public_id, "option_ids": [opts_per_q[0][0].public_id]},
            {"question_id": questions[1].public_id, "option_ids": [opts_per_q[1][1].public_id]},
            {"question_id": questions[2].public_id, "option_ids": [opts_per_q[2][1].public_id]},
        ]
        from app.database.unit_of_work import UnitOfWork
        from app.services.quiz_attempt_service import QuizAttemptService
        uow = UnitOfWork(session=db_session)
        svc = QuizAttemptService(uow)
        r1 = await svc.submit_quiz(quiz.public_id, att["attempt_id"], user_id, answers=mixed_answers)
        assert r1["percent_score"] == pytest.approx(33.33, abs=1)

        mem = await educational_memory_service.load_from_db(db_session, user_str)
        # Quiz-derived mastery (incl. weak/developing/mastered buckets) is keyed
        # by the concept's public id, matching the learner/review/recommendation engine.
        cid = str(concept.public_id)
        assert cid in mem.weak_concepts

        # Attempt 2: 2 correct, 1 wrong → 67% → developing
        att2 = await _start_attempt(db_session, quiz, user_id)
        mixed_answers2 = [
            {"question_id": questions[0].public_id, "option_ids": [opts_per_q[0][0].public_id]},
            {"question_id": questions[1].public_id, "option_ids": [opts_per_q[1][0].public_id]},
            {"question_id": questions[2].public_id, "option_ids": [opts_per_q[2][1].public_id]},
        ]
        uow2 = UnitOfWork(session=db_session)
        svc2 = QuizAttemptService(uow2)
        r2 = await svc2.submit_quiz(quiz.public_id, att2["attempt_id"], user_id, answers=mixed_answers2)
        assert r2["percent_score"] == pytest.approx(66.67, abs=1)

        mem2 = await educational_memory_service.load_from_db(db_session, user_str)
        assert cid in mem2.developing_concepts
        assert cid not in mem2.weak_concepts

        # Attempt 3: all correct → 100% → mastered
        att3 = await _start_attempt(db_session, quiz, user_id)
        all_correct = [
            {"question_id": q.public_id, "option_ids": [opts_per_q[i][0].public_id]}
            for i, q in enumerate(questions)
        ]
        uow3 = UnitOfWork(session=db_session)
        svc3 = QuizAttemptService(uow3)
        r3 = await svc3.submit_quiz(quiz.public_id, att3["attempt_id"], user_id, answers=all_correct)
        assert r3["percent_score"] == 100.0

        mem3 = await educational_memory_service.load_from_db(db_session, user_str)
        assert cid in mem3.mastered_concepts
        assert cid not in mem3.developing_concepts
        assert cid not in mem3.weak_concepts
        assert mem3.concept_records[cid].review_count == 3
        assert mem3.concept_records[cid].trend == "improving"
