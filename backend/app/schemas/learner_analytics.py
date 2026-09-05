"""P13 Learner Analytics response schemas.

Typed shapes for the ``/me/analytics/*`` endpoints. These borrow the shapes of
the historical (orphaned) ``app/schemas/analytics.py`` / ``analytics_insights.py``
models as reading surfaces only — P13 never writes to the orphaned analytics
tables. Every concept/effort row carries enough context to build actionable
deep-links (practice -> ``player.html?lesson=``, tutor -> ``tutor.html?concept=``)
server-side so the dashboard never emits a dead button.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ConceptFocus(BaseModel):
    """The single most actionable concept a learner should tackle next."""

    concept_public_id: str
    name: str
    band: str
    deep_link: str


class AnalyticsOverview(BaseModel):
    """High-level "know my trajectory" summary for one learner."""

    attempts_taken: int = Field(ge=0)
    avg_percent: float | None = None
    mastered_count: int = Field(ge=0)
    developing_count: int = Field(ge=0)
    weak_count: int = Field(ge=0)
    session_count: int = Field(ge=0)
    trend_percent: float | None = None
    current_focus: ConceptFocus | None = None


class TrendPoint(BaseModel):
    """One date-bucket of the bounded accuracy/percent trajectory."""

    date: str
    correct: int = Field(ge=0)
    incorrect: int = Field(ge=0)
    percent: float | None = None
    attempts: int = Field(ge=0)


class TrendResponse(BaseModel):
    """Accuracy/percent over the last ``window`` dates (oldest -> newest)."""

    points: list[TrendPoint] = Field(default_factory=list)
    window: int = Field(ge=1)


class ConceptAnalytic(BaseModel):
    """Per-concept mastery trajectory (band + arrow + actionable links)."""

    concept_public_id: str
    name: str
    band: str
    trend: str = "flat"  # up | flat | down
    current_mastery: float
    delta_mastery: float | None = None
    review_count: int = Field(ge=0)
    deep_link_practice: str | None = None
    deep_link_tutor: str | None = None


class ConceptsResponse(BaseModel):
    """Bounded list of concept trajectories (``max`` mirrors the hard cap)."""

    concepts: list[ConceptAnalytic] = Field(default_factory=list)
    max: int = Field(ge=0)


class EffortAnalytic(BaseModel):
    """Effort spent vs mastery gained for one concept (derived, deterministic)."""

    concept_public_id: str
    name: str
    attempts: int = Field(ge=0)
    sessions: int = Field(ge=0)
    time_seconds: int = Field(ge=0)
    mastery_delta: float | None = None
    efficiency: float | None = None


class EffortResponse(BaseModel):
    """Bounded list of effort-vs-mastery rows (``max`` mirrors the hard cap)."""

    effort: list[EffortAnalytic] = Field(default_factory=list)
    max: int = Field(ge=0)
