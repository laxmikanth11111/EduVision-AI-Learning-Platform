"""WS10 query-count regression: quiz submission must not degrade to N+1.

Instruments the shared test SQLite engine during a real quiz submit and
asserts the per-question detail tables (explanations, user answers, concepts)
are loaded with bulk ``IN`` queries rather than one SELECT per question.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import TEST_USER_ID, test_engine


@pytest_asyncio.fixture
async def quiz_id(db_session: AsyncSession) -> str:
    """Create a 3-question quiz with explanations for a couple of questions."""
    from app.models.answer_key import AnswerKey
    from app.models.presentation import Presentation
    from app.models.question_explanation import QuestionExplanation
    from app.models.quiz import Quiz
    from app.models.quiz_content import Question, QuestionOption
    from app.models.quiz_version import QuizVersion

    p = Presentation(
        title="Query Count Presentation",
        owner_id=TEST_USER_ID,
        status="published",
        slide_count=2,
    )
    db_session.add(p)
    await db_session.flush()

    quiz = Quiz(
        presentation_id=p.id,
        user_id=TEST_USER_ID,
        status="published",
        mode="practice",
        title="Query Count Quiz",
        question_count=3,
        max_attempts_per_user=3,
        passing_score=60.0,
        show_feedback_after=True,
        latest_version=1,
        published_version=1,
    )
    db_session.add(quiz)
    await db_session.flush()

    version = QuizVersion(quiz_id=quiz.id, version=1, status="published")
    db_session.add(version)
    await db_session.flush()

    specs = [
        (1, "multiple_choice", [(1, "3", False), (2, "4", True), (3, "5", False)]),
        (2, "true_false", [(1, "True", True), (2, "False", False)]),
        (3, "multiple_select", [(1, "2", True), (2, "3", True), (3, "4", False), (4, "5", True)]),
    ]
    question_ids_by_position: dict[int, int] = {}
    for position, qtype, options in specs:
        q = Question(
            quiz_version_id=version.id,
            position=position,
            question_type=qtype,
            stem=f"Question {position}",
            points=1,
            bloom_level="remember",
            difficulty="beginner",
        )
        db_session.add(q)
        await db_session.flush()
        question_ids_by_position[position] = q.id

        correct_option_public_ids: list[str] = []
        for opt_position, text, is_correct in options:
            opt = QuestionOption(question_id=q.id, position=opt_position, text=text, is_correct=is_correct)
            db_session.add(opt)
            await db_session.flush()
            if is_correct:
                correct_option_public_ids.append(opt.public_id)

        db_session.add(
            AnswerKey(
                question_id=q.id,
                answer_type=qtype,
                correct_option_ids=correct_option_public_ids,
            )
        )
        if position in (1, 2):
            db_session.add(
                QuestionExplanation(
                    question_id=q.id,
                    explanation=f"Explanation for {position}",
                    display_timing="after_submit",
                )
            )

    await db_session.flush()
    await db_session.commit()
    return quiz.public_id


@pytest.fixture
def statement_log() -> list[str]:
    return []


@pytest.fixture
def sql_logger(statement_log: list[str]) -> Iterator[None]:
    sync_engine = test_engine.sync_engine

    def _capture(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        statement_log.append(statement)

    event.listen(sync_engine, "before_cursor_execute", _capture)
    try:
        yield
    finally:
        event.remove(sync_engine, "before_cursor_execute", _capture)


@pytest.mark.asyncio
async def test_submit_quiz_uses_bulk_not_n_plus_one(
    client: AsyncClient,
    quiz_id: str,
    statement_log: list[str],
    sql_logger: None,
) -> None:
    resp = await client.post(f"/api/v1/quizzes/{quiz_id}/attempts")
    assert resp.status_code == 201
    data = resp.json()["data"]
    attempt_id = data["attempt_id"]

    for q in data["questions"]:
        if q["question_type"] == "multiple_select":
            correct_opts = [o for o in q["options"] if o["position"] in (1, 2, 4)]
            option_ids = [o["id"] for o in correct_opts]
        else:
            correct_opt = next(o for o in q["options"] if o["position"] == 2)
            option_ids = [correct_opt["id"]]
        await client.post(
            f"/api/v1/quizzes/{quiz_id}/attempts/{attempt_id}/answers/{q['id']}",
            json={"option_ids": option_ids},
        )

    statement_log.clear()
    resp = await client.post(
        f"/api/v1/quizzes/{quiz_id}/attempts/{attempt_id}/submit",
        json={"answers": [], "time_spent_seconds": 30},
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    submit_sql = statement_log
    explain_single = [s for s in submit_sql if "FROM question_explanations" in s and ".question_id =" in s]
    explain_bulk = [s for s in submit_sql if "FROM question_explanations" in s and "IN (" in s]
    answer_single = [s for s in submit_sql if "FROM user_answers" in s and "question_attempt_id =" in s]
    answer_bulk = [s for s in submit_sql if "FROM user_answers" in s and "IN (" in s]
    concept_single = [s for s in submit_sql if "FROM concepts" in s and "WHERE concepts.id =" in s]

    assert explain_single == [], "per-question explanation SELECT leaked back"
    assert explain_bulk, "explanations are not bulk-loaded with IN"
    assert answer_single == [], "per-question answer SELECT leaked back"
    assert answer_bulk, "user answers are not bulk-loaded with IN"
    assert concept_single == [], "per-question concept SELECT leaked back"
