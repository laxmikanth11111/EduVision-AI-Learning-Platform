"""Regression tests for visual component granularity (Phase 3 cleanup).

Guards against the word-fragment node defect: nodes must be intact multi-word
concepts (e.g. "Bayes' Theorem" as one node), never single-word fragments of a
larger phrase, and never generic section headings / structural labels.
"""

from __future__ import annotations

import json

import pytest

from app.ai.models import AIRequest, AIResponse, FinishReason, TokenUsage
from app.services.component_discovery_service import ComponentDiscoveryService
from app.services.visual_prompts import COMPONENT_DISCOVERY_SYSTEM_PROMPT

_MULTI_WORD_CONTENT = (
    "Bayes' Theorem lets us update the probability of a hypothesis given evidence. "
    "The AI-Based Face Attendance System uses facial recognition to mark attendance. "
    "Course Objectives and Key Probability Terms are structural labels, not concepts."
)


class _FakeProvider:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    async def generate(self, request: AIRequest) -> AIResponse:
        return AIResponse(
            text=json.dumps(self._payload),
            finish_reason=FinishReason.STOP,
            usage=TokenUsage(input_tokens=0, output_tokens=0, provider="fake", model="fake"),
            latency_ms=0.0,
            request_id="",
            correlation_id=None,
            provider="fake",
            model="fake",
        )


def _install_fake_provider(monkeypatch, payload: dict) -> None:
    fake = _FakeProvider(payload)
    monkeypatch.setattr(
        "app.services.component_discovery_service.get_ai_provider",
        lambda: fake,
    )


def test_component_discovery_prompt_forbids_multiword_splitting():
    """The LLM prompt must mandate intact multi-word concepts and forbid
    structural labels. This is the regression guard for the Phase 3 fix:
    before the fix the prompt had no granularity guidance at all."""
    prompt = COMPONENT_DISCOVERY_SYSTEM_PROMPT
    assert "GRANULARITY RULES" in prompt
    assert "independently-explainable" in prompt
    assert "Bayes' Theorem" in prompt
    assert "never split" in prompt
    assert "Face Attendance System" in prompt
    assert "Course Objectives" in prompt
    assert "3-8" in prompt


@pytest.mark.asyncio
async def test_component_discovery_preserves_intact_multiword_concepts(monkeypatch):
    """A compliant model returning intact multi-word names must have them
    passed through unchanged — never re-split into fragments."""
    _install_fake_provider(
        monkeypatch,
        {
            "components": [
                {"name": "Bayes' Theorem", "category": "core"},
                {"name": "AI-Based Face Attendance System", "category": "core"},
                {"name": "Conditional Probability", "category": "helper"},
            ]
        },
    )
    comps = await ComponentDiscoveryService().discover_components(
        _MULTI_WORD_CONTENT, title="Bayes' Theorem"
    )
    names = [c.name for c in comps]

    assert "Bayes' Theorem" in names
    assert "AI-Based Face Attendance System" in names
    assert "Conditional Probability" in names

    # No bare word-fragment of a known phrase may appear as a standalone node.
    for fragment in ("Bayes", "Theorem", "Face", "Attendance", "System", "Probability"):
        assert fragment not in names


def test_heuristic_discovery_keeps_multiword_phrases_intact():
    """The offline heuristic fallback (exercised by tests / when the LLM is
    unavailable) must keep multi-word concepts intact and drop headings.

    This is the test that would have caught the defect: the old heuristic
    matched single capitalized words, splitting "Bayes' Theorem" into
    "Bayes" and "Theorem" nodes."""
    svc = ComponentDiscoveryService()
    comps = svc._heuristic_discovery(_MULTI_WORD_CONTENT, title="Bayes' Theorem")
    names = [c.name for c in comps]

    assert names  # non-empty
    for fragment in ("Bayes", "Theorem", "Face", "Attendance", "System", "Course", "Objectives"):
        assert fragment not in names, f"word-fragment node leaked: {fragment}"
    assert not any(svc._is_structural_label(n) for n in names)


def test_is_structural_label_rejects_section_headings():
    svc = ComponentDiscoveryService()
    for heading in (
        "Course Objectives",
        "Introduction",
        "Abstract",
        "Conclusion",
        "Learn",
        "Understand",
        "Project",
        "Methodology",
        "Requirements",
        "Key Probability Terms",
    ):
        assert svc._is_structural_label(heading), heading
    for concept in (
        "Bayes' Theorem",
        "Face Attendance System",
        "Conditional Probability",
        "Central Processing Unit",
        "Random Variable",
    ):
        assert not svc._is_structural_label(concept), concept
