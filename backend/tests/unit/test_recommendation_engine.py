"""Tests for the hardened recommendation engine."""

import pytest

from app.schemas.educational_memory import (
    ConceptMasteryRecord,
    EducationalMemory,
    LearnerProfile,
)
from app.schemas.next_action import ActionType, ActivityType, Priority
from app.services.recommendation_engine import (
    THRESHOLD_ADVANCED,
    THRESHOLD_DEVELOPING,
    THRESHOLD_WEAK,
    generate_recommendations,
)


def _make_memory(
    user_id: str = "user-1",
    concepts: dict[str, tuple[str, float]] | None = None,
) -> EducationalMemory:
    """Build a minimal EducationalMemory with the given concepts."""
    concept_records = {}
    for cid, (name, mastery) in (concepts or {}).items():
        concept_records[cid] = ConceptMasteryRecord(
            concept_id=cid,
            concept_name=name,
            first_learned_at=1000.0,
            last_reviewed_at=2000.0,
            mastery_score=mastery,
            review_count=1,
            trend="stable",
        )

    mastered = [cid for cid, (_, s) in (concepts or {}).items() if s >= THRESHOLD_DEVELOPING]
    developing = [
        cid
        for cid, (_, s) in (concepts or {}).items()
        if THRESHOLD_WEAK <= s < THRESHOLD_DEVELOPING
    ]
    weak = [cid for cid, (_, s) in (concepts or {}).items() if s < THRESHOLD_WEAK]

    return EducationalMemory(
        user_id=user_id,
        profile=LearnerProfile(user_id=user_id),
        mastered_concepts=mastered,
        developing_concepts=developing,
        weak_concepts=weak,
        concept_records=concept_records,
    )


class TestEmptyMemory:
    def test_no_concepts(self):
        mem = _make_memory(concepts=None)
        rec = generate_recommendations("user-1", mem)
        assert rec.actions == []
        assert "All 0 concepts mastered" in rec.summary

    def test_empty_concept_records(self):
        mem = _make_memory(concepts={})
        rec = generate_recommendations("user-1", mem)
        assert rec.actions == []
        assert "All 0 concepts mastered" in rec.summary


class TestSingleWeakConcept:
    def test_weak_gets_explanation_and_visual(self):
        mem = _make_memory(concepts={"c1": ("Authentication", 30.0)})
        rec = generate_recommendations("user-1", mem)
        assert len(rec.actions) == 2
        types = [a.action_type for a in rec.actions]
        assert ActionType.SIMPLIFY_EXPLANATION in types
        assert ActionType.SHOW_VISUAL in types

    def test_weak_action_has_metadata(self):
        mem = _make_memory(concepts={"c1": ("Auth", 25.0)})
        rec = generate_recommendations("user-1", mem)
        action = rec.actions[0]
        assert action.metadata["mastery"] == 25.0
        assert action.metadata["difficulty"] == "beginner"
        assert action.concept_id == "c1"
        assert action.concept_name == "Auth"


class TestSingleDevelopingConcept:
    def test_developing_gets_quiz(self):
        mem = _make_memory(concepts={"c1": ("OAuth", 65.0)})
        rec = generate_recommendations("user-1", mem)
        # Developing gets 1 action (best) — second round only adds for weak
        assert len(rec.actions) == 1
        assert rec.actions[0].action_type == ActionType.TAKE_KNOWLEDGE_CHECK
        assert rec.actions[0].metadata["difficulty"] == "intermediate"


class TestSingleAdvancedConcept:
    def test_advanced_gets_quiz(self):
        mem = _make_memory(concepts={"c1": ("Tokens", 90.0)})
        rec = generate_recommendations("user-1", mem)
        assert len(rec.actions) == 1
        assert rec.actions[0].action_type == ActionType.TAKE_KNOWLEDGE_CHECK
        assert rec.actions[0].metadata["difficulty"] == "advanced"


class TestSingleMasteredConcept:
    def test_mastered_gets_next_concept(self):
        mem = _make_memory(concepts={"c1": ("Passwords", 97.0)})
        rec = generate_recommendations("user-1", mem)
        assert len(rec.actions) == 1
        assert rec.actions[0].action_type == ActionType.MOVE_TO_NEXT_CONCEPT


class TestMixedMasteryLevels:
    def test_weakest_concepts_first(self):
        mem = _make_memory(
            concepts={
                "c1": ("Easy", 92.0),
                "c2": ("Hard", 20.0),
                "c3": ("Medium", 60.0),
            }
        )
        rec = generate_recommendations("user-1", mem, max_actions=3)
        # All three should have actions, weakest first
        assert len(rec.actions) == 3
        assert rec.actions[0].concept_id == "c2"  # weakest
        assert rec.actions[1].concept_id == "c3"  # medium
        assert rec.actions[2].concept_id == "c1"  # strongest

    def test_weak_concepts_get_priority_over_mastered(self):
        mem = _make_memory(
            concepts={
                "c1": ("Mastered", 98.0),
                "c2": ("Weak", 15.0),
            }
        )
        rec = generate_recommendations("user-1", mem, max_actions=2)
        # Weak concept should be first (higher priority)
        assert rec.actions[0].concept_id == "c2"
        assert rec.actions[0].priority == Priority.HIGH


class TestMaxActions:
    def test_limits_actions(self):
        mem = _make_memory(
            concepts={
                f"c{i}": (f"Concept {i}", 20.0)
                for i in range(10)
            }
        )
        rec = generate_recommendations("user-1", mem, max_actions=3)
        assert len(rec.actions) <= 3

    def test_weak_concepts_get_two_actions_in_limit(self):
        """With 3 slots and 1 weak concept, it should get up to 2 actions."""
        mem = _make_memory(
            concepts={
                "c1": ("Weak", 20.0),
                "c2": ("Weak2", 30.0),
            }
        )
        rec = generate_recommendations("user-1", mem, max_actions=3)
        # Each weak concept gets 2 actions (explanation + visual)
        # But max_actions=3 limits it
        assert len(rec.actions) == 3
        c1_actions = [a for a in rec.actions if a.concept_id == "c1"]
        c2_actions = [a for a in rec.actions if a.concept_id == "c2"]
        assert len(c1_actions) == 2
        assert len(c2_actions) == 1


class TestNoDuplicateActions:
    def test_no_duplicate_action_type_per_concept(self):
        mem = _make_memory(concepts={"c1": ("Auth", 30.0)})
        rec = generate_recommendations("user-1", mem)
        types = [(a.action_type, a.concept_id) for a in rec.actions]
        assert len(types) == len(set(types))


class TestConceptPrioritisation:
    def test_multiple_weak_concepts_ordered_by_mastery(self):
        mem = _make_memory(
            concepts={
                "c1": ("First", 10.0),
                "c2": ("Second", 40.0),
                "c3": ("Third", 5.0),
            }
        )
        rec = generate_recommendations("user-1", mem, max_actions=3)
        # c3 (5%) should come before c1 (10%) before c2 (40%)
        assert rec.actions[0].concept_id == "c3"
        assert rec.actions[1].concept_id == "c1"
        assert rec.actions[2].concept_id == "c2"

    def test_fewer_reviews_higher_priority(self):
        """Two concepts at same mastery, the one with fewer reviews ranks higher."""
        mem = _make_memory(concepts={})
        mem.concept_records["c1"] = ConceptMasteryRecord(
            concept_id="c1", concept_name="Well Reviewed",
            first_learned_at=1, last_reviewed_at=2,
            mastery_score=30.0, review_count=5, trend="stable",
        )
        mem.concept_records["c2"] = ConceptMasteryRecord(
            concept_id="c2", concept_name="Barely Reviewed",
            first_learned_at=1, last_reviewed_at=2,
            mastery_score=30.0, review_count=1, trend="stable",
        )
        mem.weak_concepts = ["c1", "c2"]

        rec = generate_recommendations("user-1", mem, max_actions=2)
        assert rec.actions[0].concept_id == "c2"  # fewer reviews → higher priority


class TestUserMemoryMismatch:
    def test_mismatch_logged_but_still_works(self):
        mem = _make_memory(user_id="user-2", concepts={"c1": ("Auth", 30.0)})
        rec = generate_recommendations("user-1", mem)
        # Should still produce recommendations
        assert len(rec.actions) == 2
        assert rec.user_id == "user-1"


class TestSummary:
    def test_weak_summary(self):
        mem = _make_memory(
            concepts={
                "c1": ("Weak1", 20.0),
                "c2": ("Weak2", 30.0),
                "c3": ("Dev", 60.0),
            }
        )
        rec = generate_recommendations("user-1", mem)
        assert "2 concepts needing review" in rec.summary
        assert "1 developing" in rec.summary

    def test_developing_only_summary(self):
        mem = _make_memory(
            concepts={
                "c1": ("Dev1", 60.0),
                "c2": ("Dev2", 75.0),
            }
        )
        rec = generate_recommendations("user-1", mem)
        assert "2 concepts developing" in rec.summary
        assert "needing review" not in rec.summary

    def test_mastered_only_summary(self):
        mem = _make_memory(
            concepts={
                "c1": ("M1", 96.0),
                "c2": ("M2", 99.0),
            }
        )
        rec = generate_recommendations("user-1", mem)
        assert "2 concepts mastered" in rec.summary
        assert "Ready for advanced topics" in rec.summary


class TestBoundaryValues:
    def test_exactly_weak_threshold(self):
        mem = _make_memory(concepts={"c1": ("Borderline", THRESHOLD_WEAK)})
        rec = generate_recommendations("user-1", mem)
        # Exactly at 50% should be developing, not weak
        types = [a.action_type for a in rec.actions]
        assert ActionType.TAKE_KNOWLEDGE_CHECK in types

    def test_exactly_developing_threshold(self):
        mem = _make_memory(concepts={"c1": ("Borderline", THRESHOLD_DEVELOPING)})
        rec = generate_recommendations("user-1", mem)
        # Exactly at 85% should be advanced
        assert len(rec.actions) == 1
        assert rec.actions[0].action_type == ActionType.TAKE_KNOWLEDGE_CHECK
        assert rec.actions[0].metadata["difficulty"] == "advanced"

    def test_exactly_advanced_threshold(self):
        mem = _make_memory(concepts={"c1": ("Borderline", THRESHOLD_ADVANCED)})
        rec = generate_recommendations("user-1", mem)
        # Exactly at 95% should be mastered
        assert rec.actions[0].action_type == ActionType.MOVE_TO_NEXT_CONCEPT

    def test_zero_mastery(self):
        mem = _make_memory(concepts={"c1": ("Zero", 0.0)})
        rec = generate_recommendations("user-1", mem)
        assert len(rec.actions) == 2
        assert rec.actions[0].action_type == ActionType.SIMPLIFY_EXPLANATION

    def test_hundred_mastery(self):
        mem = _make_memory(concepts={"c1": ("Perfect", 100.0)})
        rec = generate_recommendations("user-1", mem)
        assert rec.actions[0].action_type == ActionType.MOVE_TO_NEXT_CONCEPT


class TestAllActionFieldsPopulated:
    def test_every_action_has_required_fields(self):
        mem = _make_memory(
            concepts={
                "c1": ("Weak", 20.0),
                "c2": ("Dev", 60.0),
                "c3": ("Adv", 90.0),
                "c4": ("Mastered", 98.0),
            }
        )
        rec = generate_recommendations("user-1", mem)
        for action in rec.actions:
            assert action.action_type is not None
            assert action.concept_id
            assert action.concept_name
            assert action.reason
            assert action.activity_type is not None
            assert action.priority is not None
            assert action.title
            assert action.description
            assert isinstance(action.metadata, dict)
