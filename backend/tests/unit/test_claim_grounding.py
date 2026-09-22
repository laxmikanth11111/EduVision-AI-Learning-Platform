"""Unit tests for the claim-level semantic grounding pipeline.

Covers segmentation, classification, evidence retrieval, deterministic
policy, verifier resolution and failure modes.  All assertions are
against deterministic behavior (AI_PROVIDER=local in conftest).
"""

from __future__ import annotations

import json
import re

import pytest

from app.ai.models import AIResponse, TokenUsage
from app.services.claim_grounding import (
    ABSOLUTE_MARKERS,
    CAUSAL_CHANGE_VERBS,
    ClaimGroundingResult,
    ClaimType,
    DeterministicGroundingVerifier,
    GroundingVerdict,
    SourceEvidence,
    _extract_verdict_json,
    classify_claim,
    content_tokens,
    evaluate_topic_claims,
    resolve_verifier,
    retrieve_evidence_batch,
    split_claims,
)
from app.services.lesson_safety import GroundedLessonSafetyValidator, LessonSafetyError

# ── Helpers ──────────────────────────────────────────────────────────────────

class _SourceStub:
    def __init__(self, text: str) -> None:
        self._text = text

    def to_text(self) -> str:
        return self._text


class _UnitStub:
    def __init__(self, position: int, title: str | None = None, raw_text: str | None = None, blocks=None) -> None:
        self.position = position
        self.title = title
        self.raw_text = raw_text
        self.blocks = blocks or []


class _TopicStub:
    def __init__(self, topic: str, description: str) -> None:
        self.topic = topic
        self.description = description


class _SourceContextStub:
    def __init__(self, units) -> None:
        self.units = units


class _FakeAIService:
    def __init__(self, response_text: str | None = None, exc: Exception | None = None) -> None:
        self._text = response_text
        self._exc = exc

    async def generate(self, request) -> AIResponse:
        if self._exc is not None:
            raise self._exc
        text = self._text or "{}"
        return AIResponse(
            text=text,
            usage=TokenUsage(input_tokens=5, output_tokens=5),
            provider="fake",
            model="fake-v1",
        )


# ── Segmentation ─────────────────────────────────────────────────────────────

class TestSplitClaims:
    @pytest.mark.asyncio
    async def test_simple_sentences(self) -> None:
        claims = split_claims("Hello brave new world. The quick brown fox jumps.")
        assert len(claims) == 2
        assert "Hello brave new world" in claims[0]
        assert "brown fox jumps" in claims[1]

    @pytest.mark.asyncio
    async def test_short_fragment_merged(self) -> None:
        claims = split_claims("Main sentence. It.")
        assert len(claims) == 1
        assert "Main sentence." in claims[0]

    @pytest.mark.asyncio
    async def test_empty(self) -> None:
        assert split_claims("") == []
        assert split_claims("   ") == []

    @pytest.mark.asyncio
    async def test_single_claim(self) -> None:
        assert len(split_claims("A single claim here.")) == 1


# ── Classification ───────────────────────────────────────────────────────────

class TestClassifyClaim:
    @pytest.mark.asyncio
    async def test_numeric_risk_high(self) -> None:
        ct, risk = classify_claim("There are exactly 7 planets.")
        assert ct == ClaimType.NUMERIC
        assert risk == "high"

    @pytest.mark.asyncio
    async def test_causal_risk_high(self) -> None:
        ct, risk = classify_claim("Exercise prevents heart disease.")
        assert ct == ClaimType.CAUSAL
        assert risk == "high"

    @pytest.mark.asyncio
    async def test_comparative_risk_high(self) -> None:
        ct, risk = classify_claim("Binary search is better than linear.")
        assert ct == ClaimType.COMPARATIVE
        assert risk == "high"

    @pytest.mark.asyncio
    async def test_definition_risk_low(self) -> None:
        ct, risk = classify_claim("TCP is a communication protocol.")
        assert ct == ClaimType.DEFINITION
        assert risk == "low"

    @pytest.mark.asyncio
    async def test_low_risk_normal(self) -> None:
        ct, risk = classify_claim("Photosynthesis uses light energy to make sugar.")
        assert risk == "low"


# ── Evidence retrieval ───────────────────────────────────────────────────────

class TestEvidenceRetrieval:
    async def test_batch_returns_list_per_claim(self) -> None:
        source = _SourceStub("A. B. C.")
        results = await retrieve_evidence_batch(
            ["A", "B"], source, top_k=2
        )
        assert len(results) == 2
        for evidence_list in results:
            assert isinstance(evidence_list, list)

    async def test_top_k_limits_results(self) -> None:
        source = _SourceStub("Word1. Word2. Word3. Word4. Word5.")
        results = await retrieve_evidence_batch(
            ["Word1"], source, top_k=2
        )
        assert len(results[0]) <= 2

    async def test_embedding_failure_falls_back_to_lexical(self) -> None:
        class _FailProvider:
            async def embed(self, texts):
                raise RuntimeError("no embeddings")

        source = _SourceStub("Photosynthesis uses light energy.")
        results = await retrieve_evidence_batch(
            ["photosynthesis light energy"],
            source,
            top_k=2,
            embedding_provider=_FailProvider(),
        )
        assert len(results) == 1
        assert len(results[0]) >= 1


# ── Deterministic verifier ──────────────────────────────────────────────────

class TestDeterministicVerifier:
    async def test_exact_restatement_supported(self) -> None:
        verifier = DeterministicGroundingVerifier()
        evidence = [
            SourceEvidence(source_unit_index=0, title="S1", text="TCP uses a three-way handshake.", similarity=1.0),
        ]
        result = await verifier.verify_claim(
            claim="TCP uses a three-way handshake.",
            claim_type=ClaimType.FACTUAL,
            risk="low",
            evidence=evidence,
        )
        assert result.verdict == GroundingVerdict.SUPPORTED

    async def test_no_evidence_uncertain(self) -> None:
        verifier = DeterministicGroundingVerifier()
        result = await verifier.verify_claim(
            claim="Photosynthesis occurs in mitochondria.",
            claim_type=ClaimType.FACTUAL,
            risk="low",
            evidence=[],
        )
        assert result.verdict == GroundingVerdict.UNCERTAIN

    async def test_marker_rejection(self) -> None:
        verifier = DeterministicGroundingVerifier()
        evidence = [
            SourceEvidence(source_unit_index=0, title="S1", text="Binary search has logarithmic time complexity.", similarity=0.8),
        ]
        result = await verifier.verify_claim(
            claim="Binary search always completes in exactly 7 operations.",
            claim_type=ClaimType.NUMERIC,
            risk="high",
            evidence=evidence,
        )
        assert result.verdict == GroundingVerdict.UNSUPPORTED
        assert "absolute_claim" in result.flags

    async def test_antonym_contradiction(self) -> None:
        verifier = DeterministicGroundingVerifier()
        evidence = [
            SourceEvidence(source_unit_index=0, title="S1", text="TCP establishes connections via handshake.", similarity=0.9),
        ]
        result = await verifier.verify_claim(
            claim="TCP uses the handshake to destroy the connection.",
            claim_type=ClaimType.FACTUAL,
            risk="low",
            evidence=evidence,
        )
        assert result.verdict == GroundingVerdict.CONTRADICTED


# ── Policy ───────────────────────────────────────────────────────────────────

class TestEvaluateTopicClaims:
    def test_all_supported_pass(self) -> None:
        results = [
            ClaimGroundingResult(claim="a", verdict=GroundingVerdict.SUPPORTED, confidence=0.9, risk="low"),
            ClaimGroundingResult(claim="b", verdict=GroundingVerdict.SUPPORTED, confidence=0.8, risk="low"),
        ]
        verdict, flags, rej = evaluate_topic_claims(results, min_confidence=0.6)
        assert verdict == "PASS"
        assert rej is None

    def test_unsupported_rejects(self) -> None:
        results = [
            ClaimGroundingResult(claim="a", verdict=GroundingVerdict.SUPPORTED, confidence=0.9, risk="low"),
            ClaimGroundingResult(claim="b", verdict=GroundingVerdict.UNSUPPORTED, confidence=0.0, risk="high"),
        ]
        verdict, _, rej = evaluate_topic_claims(results, min_confidence=0.6)
        assert verdict == "REJECT"
        assert rej is not None
        assert rej.verdict == GroundingVerdict.UNSUPPORTED

    def test_uncertain_high_risk_rejects(self) -> None:
        results = [
            ClaimGroundingResult(claim="a", verdict=GroundingVerdict.UNCERTAIN, confidence=0.5, risk="high"),
        ]
        verdict, flags, _ = evaluate_topic_claims(results, min_confidence=0.6)
        assert verdict == "REJECT"

    def test_uncertain_low_risk_passes_with_flag(self) -> None:
        results = [
            ClaimGroundingResult(claim="a", verdict=GroundingVerdict.UNCERTAIN, confidence=0.5, risk="low"),
        ]
        verdict, flags, _ = evaluate_topic_claims(results, min_confidence=0.6)
        assert verdict == "PASS"
        assert "uncertain_low_risk" in flags


# ── Verifier resolution ──────────────────────────────────────────────────────

class TestResolveVerifier:
    def test_auto_local_returns_deterministic(self) -> None:
        class _S:
            AI_LESSON_GROUNDING_VERIFIER = "auto"
            AI_PROVIDER = "local"
            AI_LESSON_GROUNDING_MIN_CONFIDENCE = 0.6
        verifier, name = resolve_verifier(_S())
        assert name == "deterministic"
        assert isinstance(verifier, DeterministicGroundingVerifier)

    def test_force_llm_requires_service(self) -> None:
        class _S:
            AI_LESSON_GROUNDING_VERIFIER = "llm"
            AI_PROVIDER = "local"
            AI_LESSON_GROUNDING_MIN_CONFIDENCE = 0.6
        verifier, name = resolve_verifier(_S())
        # no ai_service → fallback deterministic
        assert name == "deterministic"


# ── JSON extraction ──────────────────────────────────────────────────────────

class TestExtractVerdictJson:
    def test_clean_json(self) -> None:
        result = _extract_verdict_json('{"verdict": "supported", "confidence": 0.9}')
        assert result["verdict"] == "supported"

    def test_fenced_json(self) -> None:
        text = '```json\n{"verdict": "supported", "confidence": 0.9}\n```'
        result = _extract_verdict_json(text)
        assert result["confidence"] == 0.9

    def test_no_json_raises(self) -> None:
        with pytest.raises(ValueError, match="no JSON"):
            _extract_verdict_json("no json here")


# ── Full pipeline integration ────────────────────────────────────────────────

class TestRunClaimGroundingPipeline:
    async def test_grounded_payload_passes(self) -> None:
        from app.core.config import settings
        from app.services.claim_grounding import run_claim_grounding

        source = _SourceStub(
            "TCP uses a three-way handshake to establish a connection. "
            "HTTP is stateless."
        )
        topics = [_TopicStub("TCP", "TCP uses a three-way handshake to establish a connection.")]
        report, rejected = await run_claim_grounding(
            topics, source, settings=settings, ai_service=None, embedding_provider=None, top_k=3
        )
        assert report["verifier"] == "deterministic"
        assert rejected is None

    async def test_fabricated_payload_rejected(self) -> None:
        from app.core.config import settings
        from app.services.claim_grounding import run_claim_grounding

        source = _SourceStub("HTTP is stateless.")
        topics = [_TopicStub("HTTP", "HTTP maintains permanent server-side session state by default.")]
        _, rejected = await run_claim_grounding(
            topics, source, settings=settings, ai_service=None, embedding_provider=None, top_k=3
        )
        assert rejected is not None
        assert rejected["verdict"] in ("unsupported", "contradicted")
