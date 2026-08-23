from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TopicMasterySummary(BaseModel):
    public_id: str
    topic: str
    mastery: float
    attempts: int
    correct: int
    accuracy: float
    avg_time_seconds: int
    status: str
    last_activity_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ConceptMasterySummary(BaseModel):
    public_id: str
    topic: str
    concept: str
    mastery: float
    attempts: int
    correct: int
    accuracy: float
    status: str
    last_activity_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class LearningProfileResponse(BaseModel):
    public_id: str
    overall_mastery: float | None = None
    average_score: float | None = None
    average_percent_score: float | None = None
    average_time_seconds: int
    total_attempts: int
    total_questions_answered: int
    correct_answers: int
    accuracy: float | None = None
    weak_concepts: list[str] | None = None
    strong_concepts: list[str] | None = None
    recommended_difficulty: str
    difficulty_progression: dict[str, Any] | None = None
    bloom_progress: dict[str, Any] | None = None
    objectives_completed: int
    objectives_total: int
    confidence_score: float | None = None
    engagement_score: float | None = None
    quiz_history: list[dict[str, Any]] | None = None
    knowledge_graph: dict[str, Any] | None = None
    review_plan: dict[str, Any] | None = None
    recommended_next_lesson_public_id: str | None = None
    last_activity_at: datetime | None = None
    profile_version: str

    model_config = ConfigDict(from_attributes=True)


StudentLearningProfileResponse = LearningProfileResponse  # backward compat alias


class MasteryOverviewResponse(BaseModel):
    profile: LearningProfileResponse
    topics: list[TopicMasterySummary]
    concepts: list[ConceptMasterySummary]


class RecommendationResponse(BaseModel):
    public_id: str
    recommendation_type: str
    title: str
    description: str | None = None
    target_type: str | None = None
    target_id: str | None = None
    rationale: dict[str, Any] | None = None
    score: float
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProgressSnapshotResponse(BaseModel):
    public_id: str
    period: str
    period_start: datetime
    period_end: datetime
    snapshot: dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AdaptiveHistoryEntryResponse(BaseModel):
    public_id: str
    event_type: str
    payload: dict[str, Any] | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AdaptiveQuestionOption(BaseModel):
    id: str
    position: int
    text: str
    is_correct: bool | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class AdaptiveQuestion(BaseModel):
    id: str
    position: int
    type: str
    bloom_level: str | None = None
    difficulty: str | None = None
    stem: str
    points: int = 1
    scenario_context: str | None = None
    source_ref: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
    topics: list[str] = Field(default_factory=list)
    concepts: list[str] = Field(default_factory=list)
    options: list[AdaptiveQuestionOption] = Field(default_factory=list)
    answer_key: dict[str, Any] | None = None
    explanation: dict[str, Any] | None = None


class AdaptiveQuizRationale(BaseModel):
    mode: str
    target_topics: list[str] = Field(default_factory=list)
    bloom_focus: list[str] = Field(default_factory=list)
    recommended_difficulty: str
    avoided_topics: list[str] = Field(default_factory=list)


class AdaptiveQuizResponse(BaseModel):
    mode: str
    quiz_public_id: str
    quiz_title: str | None = None
    difficulty: str | None = None
    questions: list[AdaptiveQuestion] = Field(default_factory=list)
    rationale: AdaptiveQuizRationale
