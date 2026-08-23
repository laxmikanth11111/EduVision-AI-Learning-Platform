"""P2 Validation — verifying boundaries between software validation and learning effectiveness.

This test module documents critical limitations of the effectiveness measurement system.

P2.11: No assumptions about learning gains. The system measures score changes only.
        Absolute gain = post - baseline. Normalized gain = absolute / (100 - baseline).
        These are mathematical facts about score deltas, not evidence of learning.

P2.12: No hypothesis testing or statistical power analysis.
        The comparison endpoint returns raw averages only.
        No p-values, confidence intervals, effect sizes, or power calculations.
        Statistical significance requires external analysis with proper study design.

P2.13: Comparison framework validates group data isolation and aggregation correctness.
        It does NOT validate that any observed difference is meaningful or causal.

P2.14: Clear boundary — these tests verify software correctness only.
        They prove: "the code computes X correctly."
        They do NOT prove: "users learn better with EduVision."
"""

from __future__ import annotations

import uuid

import pytest

from app.models.effectiveness_assessment import EffectivenessAssessment
from app.models.presentation import Presentation
from app.schemas.effectiveness import AssessmentType
from app.services.effectiveness_service import EffectivenessService

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_pres(session) -> Presentation:
    pres = Presentation(
        public_id=f"pres_{uuid.uuid4().hex[:16]}",
        title="Validation Test",
        description="P2 validation",
        status="ready",
        owner_id=uuid.uuid4(),
    )
    session.add(pres)
    await session.flush()
    return pres


# ---------------------------------------------------------------------------
# P2.11: No assumptions about learning gains
# ---------------------------------------------------------------------------


class TestNoUnwarrantedClaims:
    """Verify that the system never claims learning effectiveness.

    The system computes score deltas. It does not and cannot claim that
    these deltas represent actual learning, comprehension, or retention
    of knowledge by human beings.
    """

    async def test_gain_is_purely_mathematical(self, db_session):
        """Gain is post - baseline. No behavioral interpretation."""
        pres = await _create_pres(db_session)
        service = EffectivenessService(db_session)
        assessment = await service.get_or_create_assessment(
            user_id=uuid.uuid4(), presentation_id=pres.id,
        )
        assessment.baseline_score = 30.0
        assessment.post_score = 70.0
        service._compute_gains(assessment)

        # These are the ONLY claims the system makes:
        assert assessment.absolute_gain == 40.0
        assert assessment.normalized_gain == pytest.approx(40.0 / 70.0)

        # The system stores no claims about "learning", "understanding",
        # "comprehension", or "retention" in the database model.
        # Verify the model has no such columns:
        column_names = {c.name for c in EffectivenessAssessment.__table__.columns}
        forbidden_terms = {"learning_claim", "understanding_score", "comprehension"}
        for term in forbidden_terms:
            assert term not in column_names, (
                f"EffectivenessAssessment should not contain '{term}' — "
                "the system measures score deltas, not learning outcomes"
            )

    async def test_normalized_gain_does_not_imply_effectiveness(self, db_session):
        """Normalized gain of 1.0 means max possible improvement on test,
        not 'perfect learning'."""
        pres = await _create_pres(db_session)
        service = EffectivenessService(db_session)
        assessment = await service.get_or_create_assessment(
            user_id=uuid.uuid4(), presentation_id=pres.id,
        )
        assessment.baseline_score = 0.0
        assessment.post_score = 100.0
        service._compute_gains(assessment)
        assert assessment.normalized_gain == 1.0

        # The system computes this correctly. But normalized_gain == 1.0
        # does not mean the user "learned everything." It means they
        # improved from 0% to 100% on a specific quiz. This distinction
        # is critical for anyone interpreting the results.

    async def test_negative_gain_not_a_failure(self, db_session):
        """Negative gain is a valid measurement, not a system error."""
        pres = await _create_pres(db_session)
        service = EffectivenessService(db_session)
        assessment = await service.get_or_create_assessment(
            user_id=uuid.uuid4(), presentation_id=pres.id,
        )
        assessment.baseline_score = 80.0
        assessment.post_score = 60.0
        service._compute_gains(assessment)
        assert assessment.absolute_gain == -20.0

        # Negative gain could mean: user guessed on baseline, quiz was
        # harder, user was distracted, or many other factors.
        # The system correctly records the delta. Interpretation requires
        # human judgment about study design and confounders.

    async def test_no_causal_language_in_format_gain(self, db_session):
        """_format_gain output contains no causal language."""
        pres = await _create_pres(db_session)
        service = EffectivenessService(db_session)
        assessment = await service.get_or_create_assessment(
            user_id=uuid.uuid4(), presentation_id=pres.id,
        )
        assessment.baseline_score = 40.0
        assessment.post_score = 80.0
        service._compute_gains(assessment)
        gain = service._format_gain(assessment)

        # Keys are purely descriptive of measured values
        expected_keys = {
            "assessment_public_id", "presentation_id", "experiment_group",
            "baseline_score", "post_score", "absolute_gain", "normalized_gain",
            "retention_score", "retention_loss", "retention_pct",
            "total_learning_time_seconds", "events_summary",
            "concept_improvements", "weak_concepts", "strong_concepts",
            "status", "completed_at",
        }
        assert set(gain.keys()) == expected_keys

        # No key names imply causation
        causal_words = {"caused", "because", "result", "effect", "improvement_from"}
        for key in gain:
            for word in causal_words:
                assert word not in key, (
                    f"Key '{key}' implies causation — "
                    "the system measures deltas, not causal effects"
                )

    async def test_weak_concepts_not_a_diagnosis(self, db_session):
        """weak_concepts identifies low post-scores, not learning deficits."""
        pres = await _create_pres(db_session)
        service = EffectivenessService(db_session)
        assessment = await service.get_or_create_assessment(
            user_id=uuid.uuid4(), presentation_id=pres.id,
        )
        assessment.baseline_concept_scores = {"algebra": 80.0, "geometry": 30.0}
        assessment.post_concept_scores = {"algebra": 85.0, "geometry": 45.0}
        gain = service._format_gain(assessment)

        # Geometry is "weak" (post < 50) but improved by 15 points
        assert "geometry" in gain["weak_concepts"]
        assert gain["concept_improvements"][1]["improvement"] == 15.0

        # The system reports what the scores are. It does not diagnose
        # "learning deficits" — that requires expert human judgment.


# ---------------------------------------------------------------------------
# P2.12: No hypothesis testing or statistical power
# ---------------------------------------------------------------------------


class TestNoStatisticalClaims:
    """Verify the comparison endpoint returns raw data only.

    No p-values, confidence intervals, effect sizes, or significance tests.
    Statistical analysis requires external tools and proper study design.
    """

    async def test_comparison_returns_raw_averages(self, db_session):
        """compare_groups returns descriptive statistics only."""
        service = EffectivenessService(db_session)

        # Create two groups
        for i in range(5):
            pres = await _create_pres(db_session)
            uid = uuid.uuid4()
            a = await service.get_or_create_assessment(
                user_id=uid, presentation_id=pres.id,
                experiment_group="reference",
            )
            a.baseline_score = 40.0
            a.post_score = 60.0 + i * 5
            service._compute_gains(a)

        for i in range(5):
            pres = await _create_pres(db_session)
            uid = uuid.uuid4()
            a = await service.get_or_create_assessment(
                user_id=uid, presentation_id=pres.id,
                experiment_group="eduvision",
            )
            a.baseline_score = 40.0
            a.post_score = 70.0 + i * 5
            service._compute_gains(a)
        await db_session.flush()

        result = await service.compare_groups(
            group_a="reference", group_b="eduvision",
        )

        # Raw counts and averages only — no statistical inference
        assert "group_a_count" in result
        assert "group_b_count" in result
        assert "group_a_avg_absolute_gain" in result
        assert "group_b_avg_absolute_gain" in result

        # No statistical fields exist
        forbidden_fields = {
            "p_value", "confidence_interval", "effect_size",
            "statistical_significance", "chi_squared", "t_test",
            "p_value_a", "p_value_b", "power",
        }
        for field in forbidden_fields:
            assert field not in result, (
                f"Comparison result contains '{field}' — "
                "the system does not perform statistical inference"
            )

    async def test_comparison_count_required_for_inference(self, db_session):
        """Small sample sizes make any comparison meaningless."""
        service = EffectivenessService(db_session)
        pres = await _create_pres(db_session)

        # Only 1 user per group — far too small for any statistical claim
        a = await service.get_or_create_assessment(
            user_id=uuid.uuid4(), presentation_id=pres.id,
            experiment_group="reference",
        )
        a.baseline_score = 40.0
        a.post_score = 80.0
        service._compute_gains(a)

        pres2 = await _create_pres(db_session)
        b = await service.get_or_create_assessment(
            user_id=uuid.uuid4(), presentation_id=pres2.id,
            experiment_group="eduvision",
        )
        b.baseline_score = 40.0
        b.post_score = 90.0
        service._compute_gains(b)
        await db_session.flush()

        result = await service.compare_groups(
            group_a="reference", group_b="eduvision",
        )
        assert result["group_a_count"] == 1
        assert result["group_b_count"] == 1

        # With n=1 per group, any difference is anecdotal.
        # The system correctly reports the numbers. It does NOT claim
        # the 10-point difference is meaningful.


# ---------------------------------------------------------------------------
# P2.13: Comparison framework validates correctness, not meaning
# ---------------------------------------------------------------------------


class TestComparisonFramework:
    """Verify comparison aggregation logic is correct.

    This proves the math is right. It does NOT prove the difference is real.
    """

    async def test_aggregation_is_correct(self, db_session):
        """Averages are computed correctly from the underlying data."""
        service = EffectivenessService(db_session)

        gains_a = [20.0, 40.0, 60.0]
        gains_b = [30.0, 50.0]

        for g in gains_a:
            pres = await _create_pres(db_session)
            a = await service.get_or_create_assessment(
                user_id=uuid.uuid4(), presentation_id=pres.id,
                experiment_group="ref",
            )
            a.baseline_score = 40.0
            a.post_score = 40.0 + g
            service._compute_gains(a)

        for g in gains_b:
            pres = await _create_pres(db_session)
            a = await service.get_or_create_assessment(
                user_id=uuid.uuid4(), presentation_id=pres.id,
                experiment_group="ev",
            )
            a.baseline_score = 40.0
            a.post_score = 40.0 + g
            service._compute_gains(a)
        await db_session.flush()

        result = await service.compare_groups(group_a="ref", group_b="ev")
        assert result["group_a_count"] == 3
        assert result["group_b_count"] == 2
        assert result["group_a_avg_absolute_gain"] == pytest.approx(sum(gains_a) / 3)
        assert result["group_b_avg_absolute_gain"] == pytest.approx(sum(gains_b) / 2)

    async def test_empty_groups_return_none(self, db_session):
        """Empty groups produce None averages, not 0."""
        service = EffectivenessService(db_session)
        result = await service.compare_groups(
            group_a="empty_a", group_b="empty_b",
        )
        assert result["group_a_avg_absolute_gain"] is None
        assert result["group_b_avg_absolute_gain"] is None

    async def test_group_isolation_bidirectional(self, db_session):
        """Group assignment is independent of query direction."""
        service = EffectivenessService(db_session)
        pres = await _create_pres(db_session)
        a = await service.get_or_create_assessment(
            user_id=uuid.uuid4(), presentation_id=pres.id,
            experiment_group="alpha",
        )
        a.baseline_score = 50.0
        a.post_score = 70.0
        service._compute_gains(a)
        await db_session.flush()

        result_ab = await service.compare_groups(group_a="alpha", group_b="beta")
        assert result_ab["group_a_count"] == 1
        assert result_ab["group_b_count"] == 0

        result_ba = await service.compare_groups(group_a="beta", group_b="alpha")
        assert result_ba["group_a_count"] == 0
        assert result_ba["group_b_count"] == 1


# ---------------------------------------------------------------------------
# P2.14: Clear boundary — software validation vs learning effectiveness
# ---------------------------------------------------------------------------


class TestBoundaryBetweenSoftwareAndLearning:
    """These tests document what the system CAN and CANNOT validate.

    CAN validate (Level 1 — Software):
      - Code executes without errors
      - Data is stored and retrieved correctly
      - Calculations are mathematically correct
      - API endpoints return expected status codes and schemas
      - User data is properly isolated

    CANNOT validate (Level 2 — Learning Effectiveness):
      - Whether users actually learn
      - Whether score gains represent real understanding
      - Whether EduVision causes better outcomes than alternatives
      - Whether retention scores reflect long-term knowledge
      - Whether concept scores accurately measure concept mastery
    """

    async def test_system_measures_scores_not_learning(self, db_session):
        """The system stores and computes SCORES. It does not measure LEARNING.

        Learning is a complex cognitive process that cannot be determined
        from quiz scores alone. Factors like test anxiety, guessing,
        question familiarity, and motivation all affect scores independently
        of actual learning.
        """
        pres = await _create_pres(db_session)
        service = EffectivenessService(db_session)
        assessment = await service.get_or_create_assessment(
            user_id=uuid.uuid4(), presentation_id=pres.id,
        )
        assessment.baseline_score = 30.0
        assessment.post_score = 90.0
        service._compute_gains(assessment)

        # The system says: "score changed by 60 points"
        assert assessment.absolute_gain == 60.0

        # The system does NOT say: "user learned a lot"
        # Anyone interpreting this data must consider:
        # 1. Were the baseline and post quizzes equally difficult?
        # 2. Did the user guess correctly on the post quiz?
        # 3. Was the user more familiar with the test format?
        # 4. Were there ceiling/floor effects?

    async def test_comparison_requires_human_interpretation(self, db_session):
        """Group differences require expert interpretation, not just numbers.

        Even if group B has a higher average gain than group A, this could be
        due to: selection bias, motivation differences, prior knowledge,
        time of day, sample size, or countless other confounders.
        """
        service = EffectivenessService(db_session)
        pres = await _create_pres(db_session)

        a = await service.get_or_create_assessment(
            user_id=uuid.uuid4(), presentation_id=pres.id,
            experiment_group="control",
        )
        a.baseline_score = 50.0
        a.post_score = 70.0
        service._compute_gains(a)

        pres2 = await _create_pres(db_session)
        b = await service.get_or_create_assessment(
            user_id=uuid.uuid4(), presentation_id=pres2.id,
            experiment_group="treatment",
        )
        b.baseline_score = 50.0
        b.post_score = 80.0
        service._compute_gains(b)
        await db_session.flush()

        result = await service.compare_groups(
            group_a="control", group_b="treatment",
        )
        # The system computes: treatment group avg gain = 30, control = 20
        assert result["group_b_avg_absolute_gain"] > result["group_a_avg_absolute_gain"]

        # But this 10-point difference could be completely meaningless
        # without proper experimental design, randomization, and
        # statistical analysis by qualified researchers.

    async def test_retention_does_not_measure_memory(self, db_session):
        """retention_pct is a score ratio, not a measure of memory.

        retention_pct = retention_score / post_score * 100

        This measures "what fraction of the post-quiz score was maintained
        on the retention quiz." It does NOT measure whether the user
        actually remembers the material.
        """
        pres = await _create_pres(db_session)
        service = EffectivenessService(db_session)
        assessment = await service.get_or_create_assessment(
            user_id=uuid.uuid4(), presentation_id=pres.id,
        )
        assessment.post_score = 80.0
        assessment.retention_score = 60.0
        service._compute_gains(assessment)

        assert assessment.retention_loss == 20.0
        assert assessment.retention_pct == pytest.approx(75.0)

        # 75% "retention" means the retention quiz score was 75% of the
        # post-quiz score. It does NOT mean the user "retained 75% of
        # what they learned." Memory is far more complex than this.

    async def test_user_feedback_is_subjective(self, db_session):
        """User feedback reflects perception, not objective effectiveness.

        A user saying they "understood well" (high perceived_understanding)
        does not mean they actually learned. Confidence and competence
        are often poorly correlated (Dunning-Kruger effect).
        """
        from app.services.feedback_service import UserFeedbackService

        service = UserFeedbackService(db_session)
        fb = await service.submit(
            user_id=uuid.uuid4(),
            perceived_understanding=5,
            confidence=5,
            usefulness=5,
            overall_experience=5,
        )
        # User says everything is great. This is valuable feedback about
        # user experience. It is NOT evidence of learning effectiveness.
        assert fb.perceived_understanding == 5
        assert fb.confidence == 5


# ---------------------------------------------------------------------------
# P3.5: Data Isolation — record-score endpoint
# ---------------------------------------------------------------------------


class TestDataIsolation:
    async def test_user_cannot_overwrite_other_users_assessment(self, db_session):
        """User A cannot use record_quiz_score to modify User B's assessment.

        The record_quiz_score method now requires user_id and filters both
        the assessment and quiz attempt by ownership.
        """
        from app.models.quiz import Quiz
        from app.models.quiz_attempt import QuizAttempt
        from app.models.quiz_version import QuizVersion
        from app.services.effectiveness_service import EffectivenessService

        user_a = uuid.uuid4()
        user_b = uuid.uuid4()

        # Create presentation + quiz + attempt for User A
        pres_a = await _create_pres(db_session)
        quiz_a = Quiz(
            public_id=f"quiz_{uuid.uuid4().hex[:16]}",
            presentation_id=pres_a.id,
            user_id=user_a,
            status="published",
            mode="practice",
            assessment_type="normal",
            question_count=1,
            latest_version=1,
        )
        db_session.add(quiz_a)
        await db_session.flush()

        version_a = QuizVersion(
            public_id=f"qver_{uuid.uuid4().hex[:16]}",
            quiz_id=quiz_a.id,
            version=1,
            status="published",
        )
        db_session.add(version_a)
        await db_session.flush()

        attempt_a = QuizAttempt(
            public_id=f"qatt_{uuid.uuid4().hex[:16]}",
            quiz_id=quiz_a.id,
            quiz_version_id=version_a.id,
            user_id=user_a,
            status="completed",
            score=1.0,
            max_score=1.0,
            percent_score=100.0,
            time_spent_seconds=60,
        )
        db_session.add(attempt_a)
        await db_session.flush()

        # User A creates their own assessment
        service = EffectivenessService(db_session)
        assessment_a = await service.get_or_create_assessment(
            user_id=user_a, presentation_id=pres_a.id,
        )
        assessment_a = await service.record_quiz_score(
            user_id=user_a,
            assessment_id=assessment_a.id,
            assessment_type="baseline",
            quiz_id=quiz_a.id,
            score=50.0,
        )
        assert assessment_a.baseline_score == 50.0

        # User B tries to overwrite User A's assessment — should fail
        from app.core.exceptions import NotFoundError

        with pytest.raises(NotFoundError):
            await service.record_quiz_score(
                user_id=user_b,
                assessment_id=assessment_a.id,
                assessment_type="baseline",
                quiz_id=quiz_a.id,
                score=99.0,
            )

        # User A's score should remain unchanged
        await db_session.refresh(assessment_a)
        assert assessment_a.baseline_score == 50.0

    async def test_user_cannot_record_other_users_attempt(self, db_session):
        """User B cannot use User A's quiz attempt to record a score."""
        from app.models.quiz import Quiz
        from app.models.quiz_attempt import QuizAttempt
        from app.models.quiz_version import QuizVersion
        from app.services.effectiveness_service import EffectivenessService

        user_a = uuid.uuid4()
        user_b = uuid.uuid4()

        pres = await _create_pres(db_session)
        quiz = Quiz(
            public_id=f"quiz_{uuid.uuid4().hex[:16]}",
            presentation_id=pres.id,
            user_id=user_a,
            status="published",
            mode="practice",
            assessment_type="normal",
            question_count=1,
            latest_version=1,
        )
        db_session.add(quiz)
        await db_session.flush()

        version = QuizVersion(
            public_id=f"qver_{uuid.uuid4().hex[:16]}",
            quiz_id=quiz.id,
            version=1,
            status="published",
        )
        db_session.add(version)
        await db_session.flush()

        attempt_a = QuizAttempt(
            public_id=f"qatt_{uuid.uuid4().hex[:16]}",
            quiz_id=quiz.id,
            quiz_version_id=version.id,
            user_id=user_a,
            status="completed",
            score=1.0,
            max_score=1.0,
            percent_score=100.0,
            time_spent_seconds=60,
        )
        db_session.add(attempt_a)
        await db_session.flush()

        # User B creates their own assessment
        service = EffectivenessService(db_session)
        assessment_b = await service.get_or_create_assessment(
            user_id=user_b, presentation_id=pres.id,
        )

        # User B tries to use User A's quiz attempt — should fail
        from app.core.exceptions import NotFoundError

        with pytest.raises(NotFoundError):
            await service.record_attempt_score(
                user_id=user_b,
                assessment_id=assessment_b.id,
                assessment_type="baseline",
                quiz_attempt_id=attempt_a.id,
            )

        # User B's assessment should have no score
        await db_session.refresh(assessment_b)
        assert assessment_b.baseline_score is None
