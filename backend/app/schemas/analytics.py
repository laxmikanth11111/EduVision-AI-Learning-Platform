from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TrendChartPoint(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    date: str
    label: str | None = None
    value: float = 0.0
    secondary_value: float | None = None


class HeatmapPoint(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    date: str
    count: int = 0
    intensity: int = 0  # 0 to 4 scale for GitHub-style heatmap contribution graph


class LeaderboardItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    rank: int
    user_id: str = Field(alias="userId")
    name: str
    avatar_url: str | None = Field(default=None, alias="avatarUrl")
    lessons_completed: int = Field(default=0, alias="lessonsCompleted")
    avg_quiz_score: float = Field(default=0.0, alias="avgQuizScore")
    total_study_time_minutes: int = Field(default=0, alias="totalStudyTimeMinutes")
    total_points: int = Field(default=0, alias="totalPoints")


class LearningAnalyticsResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    lessons_completed: int = Field(default=0, alias="lessonsCompleted")
    lessons_in_progress: int = Field(default=0, alias="lessonsInProgress")
    quiz_attempts: int = Field(default=0, alias="quizAttempts")
    avg_quiz_score: float = Field(default=0.0, alias="avgQuizScore")
    study_streak_days: int = Field(default=0, alias="studyStreakDays")
    study_time_minutes: int = Field(default=0, alias="studyTimeMinutes")
    completion_percentage: float = Field(default=0.0, alias="completionPercentage")
    bookmarks_count: int = Field(default=0, alias="bookmarksCount")
    notes_count: int = Field(default=0, alias="notesCount")
    tutor_sessions_count: int = Field(default=0, alias="tutorSessionsCount")
    exports_count: int = Field(default=0, alias="exportsCount")
    recent_activity: list[dict[str, Any]] = Field(default_factory=list, alias="recentActivity")


class PresentationAnalyticsDetailResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    presentation_id: str = Field(alias="presentationId")
    title: str
    upload_count: int = Field(default=1, alias="uploadCount")
    processing_duration_seconds: float = Field(default=0.0, alias="processingDurationSeconds")
    lesson_generation_count: int = Field(default=0, alias="lessonGenerationCount")
    quiz_generation_count: int = Field(default=0, alias="quizGenerationCount")
    tutor_sessions_count: int = Field(default=0, alias="tutorSessionsCount")
    exports_count: int = Field(default=0, alias="exportsCount")
    active_learners_count: int = Field(default=0, alias="activeLearnersCount")
    view_count: int = Field(default=0, alias="viewCount")
    unique_viewers: int = Field(default=0, alias="uniqueViewers")
    avg_quiz_score: float = Field(default=0.0, alias="avgQuizScore")
    completion_rate: float = Field(default=0.0, alias="completionRate")


class CreatorAnalyticsResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    total_learners: int = Field(default=0, alias="totalLearners")
    active_learners: int = Field(default=0, alias="activeLearners")
    presentation_usage_count: int = Field(default=0, alias="presentationUsageCount")
    engagement_score: float = Field(default=0.0, alias="engagementScore")
    completion_trends: list[TrendChartPoint] = Field(default_factory=list, alias="completionTrends")
    average_quiz_scores: list[TrendChartPoint] = Field(default_factory=list, alias="averageQuizScores")
    difficult_topics: list[dict[str, Any]] = Field(default_factory=list, alias="difficultTopics")
    learner_leaderboard: list[LeaderboardItem] = Field(default_factory=list, alias="learnerLeaderboard")


class SystemAnalyticsResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    api_requests_total: int = Field(default=0, alias="apiRequestsTotal")
    ai_requests_total: int = Field(default=0, alias="aiRequestsTotal")
    export_stats: dict[str, Any] = Field(default_factory=dict, alias="exportStats")
    processing_jobs_total: int = Field(default=0, alias="processingJobsTotal")
    storage_usage_bytes: int = Field(default=0, alias="storageUsageBytes")
    redis_usage_keys: int = Field(default=0, alias="redisUsageKeys")
    celery_jobs_active: int = Field(default=0, alias="celeryJobsActive")
    document_count_total: int = Field(default=0, alias="documentCountTotal")
    uptime_seconds: float = Field(default=86400.0, alias="uptimeSeconds")
    system_health_status: str = Field(default="healthy", alias="systemHealthStatus")


class AnalyticsFilterParams(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    start_date: datetime | None = Field(default=None, alias="startDate")
    end_date: datetime | None = Field(default=None, alias="endDate")
    period: str = Field(default="30d", max_length=20)  # 7d, 30d, 90d, 1y
    presentation_id: str | None = Field(default=None, alias="presentationId")
