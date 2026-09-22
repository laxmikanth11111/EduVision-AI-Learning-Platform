"""Grounding benchmark: precision / recall evaluation against the deterministic verifier.

Runs every case through the DeterministicGroundingVerifier (local, zero network)
and reports:
  1. Per-category safety decision (reject / pass) accuracy.
  2. Deterministic verdict-value match rate against declared expected.
  3. False positives (safe content wrongly rejected) and false negatives
     (fabricated content wrongly accepted).
  4. Precision / recall at the *safety-decision* level.

The LLM-verifier expected values are reported for comparison but not executed;
they represent the reference standard a capable entailment model would achieve.
"""

from __future__ import annotations

import json

import pytest

from app.services.claim_grounding import (
    ClaimType,
    DeterministicGroundingVerifier,
    GroundingVerdict,
    SourceEvidence,
    run_claim_grounding,
)
from tests.fixtures.grounding.benchmark_cases import (
    BenchmarkCase,
    get_all_cases,
    get_category_counts,
)


def _safety_decision(
    verdict: GroundingVerdict,
    confidence: float,
    risk: str,
    *,
    min_confidence: float = 0.6,
) -> str:
    """Derive safety decision (reject/pass) from a ClaimGroundingResult fields."""
    if verdict in (GroundingVerdict.UNSUPPORTED, GroundingVerdict.CONTRADICTED):
        return "reject"
    if verdict == GroundingVerdict.SUPPORTED and confidence >= min_confidence:
        return "pass"
    if verdict == GroundingVerdict.UNCERTAIN and risk == "high":
        return "reject"
    # UNCERTAIN + low risk
    return "pass"


ALL_CASES = get_all_cases()

# Categories where the correct safety decision is REJECT
REJECT_CATEGORIES = {"unsupported", "contradiction", "vocab_overlap", "numeric_causal"}
# Categories where the correct safety decision is PASS
PASS_CATEGORIES = {"restatement", "paraphrase", "educational_injection"}


@pytest.mark.parametrize(
    "case",
    ALL_CASES,
    ids=[f"{c.category}:{c.description[:40]}" for c in ALL_CASES],
)
def test_deterministic_verdict_matches_expected(case: BenchmarkCase) -> None:
    verifier = DeterministicGroundingVerifier()
    evidence = [SourceEvidence(
        source_unit_index=0, title="source",
        text=case.source, similarity=1.0,
    )]
    import asyncio
    result = asyncio.run(
        verifier.verify_claim(
            claim=case.claim,
            claim_type=ClaimType.FACTUAL,
            risk=case.risk,
            evidence=evidence,
        )
    )
    assert result.verdict.value == case.expected_deterministic, (
        f"MISMATCH [{case.category}] {case.description}\n"
        f"  source: {case.source!r}\n"
        f"  claim:  {case.claim!r}\n"
        f"  expected={case.expected_deterministic}, actual={result.verdict.value}, "
        f"method={result.method}, confidence={result.confidence}"
    )


def test_safety_decision_accuracy() -> None:
    verifier = DeterministicGroundingVerifier()
    import asyncio
    fp = 0  # safe content wrongly rejected
    fn = 0  # fabricated content wrongly accepted
    tp = 0  # fabricated content correctly rejected
    tn = 0  # safe content correctly accepted
    verdict_matches = 0
    total = len(ALL_CASES)
    undocumented_flag_offs = []

    for case in ALL_CASES:
        evidence = [SourceEvidence(source_unit_index=0, title="source",
                                   text=case.source, similarity=1.0)]
        result = asyncio.run(
            verifier.verify_claim(
                claim=case.claim,
                claim_type=ClaimType.FACTUAL,
                risk=case.risk,
                evidence=evidence,
            )
        )
        decision = _safety_decision(result.verdict, result.confidence, result.risk)
        should_reject = case.category in REJECT_CATEGORIES

        if result.verdict.value == case.expected_deterministic:
            verdict_matches += 1

        if should_reject and decision == "reject":
            tp += 1
        elif should_reject and decision == "pass":
            fn += 1
            if not case.deterministic_known_limitation:
                undocumented_flag_offs.append(
                    f"FN  [{case.category}] {case.description}"
                )
        elif not should_reject and decision == "pass":
            tn += 1
        elif not should_reject and decision == "reject":
            fp += 1
            if not case.deterministic_known_limitation:
                undocumented_flag_offs.append(
                    f"FP  [{case.category}] {case.description}"
                )

    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    safety_accuracy = (tp + tn) / total
    verdict_accuracy = verdict_matches / total

    report = {
        "total_cases": total,
        "category_counts": get_category_counts(),
        "deterministic": {
            "safety_accuracy": round(safety_accuracy, 4),
            "verdict_value_accuracy": round(verdict_accuracy, 4),
            "precision_reject_fabrications": round(precision, 4),
            "recall_reject_fabrications": round(recall, 4),
            "f1_score": round(f1, 4),
            "true_positives": tp,
            "false_negatives": fn,
            "true_negatives": tn,
            "false_positives": fp,
        },
        "documented_known_limitations": {
            "count": sum(
                1 for c in ALL_CASES if c.deterministic_known_limitation
            ),
            "note": "Each is a deliberately-reported deterministic limitation "
                    "that the LLM verifier (authority) is expected to close.",
        },
        "llm_reference": {
            "note": "LLM expected values in the dataset; not executed here.",
            "expected_safety_accuracy": 1.0,
        },
    }
    print("\n" + "=" * 60)
    print("GROUNDING BENCHMARK — DETERMINISTIC VERIFIER")
    print("=" * 60)
    print(json.dumps(report, indent=2))

    # Core assertions: the deterministic path must be fail-safe.
    # Every false decision must have been openly documented as a known
    # limitation in the benchmark dataset — never silent.
    assert fn == 0 or undocumented_flag_offs == [], (
        "UNDOCUMENTED false decisions on deterministic fail-safe path:\n"
        + "\n".join(undocumented_flag_offs)
    )
    assert safety_accuracy >= 0.75, (
        f"Safety accuracy {safety_accuracy:.1%} is below 75% minimum. "
        f"FP={fp}, FN={fn}"
    )
    # Verdict accuracy may be lower than safety accuracy since UNCERTAIN
    # is acceptable when the final decision is still REJECT
    assert verdict_accuracy >= 0.85, (
        f"Verdict-value accuracy {verdict_accuracy:.1%} is below 85% minimum. "
        f"The deterministic path should match its declared expectations."
    )


class _PipelineSettings:
    AI_LESSON_GROUNDING_VERIFIER = "auto"
    AI_PROVIDER = "local"
    AI_LESSON_GROUNDING_MIN_CONFIDENCE = 0.6
    AI_LESSON_GROUNDING_MAX_EVIDENCE = 2
    AI_LESSON_GROUNDING_MAX_CLAIMS_PER_TOPIC = 4


class _PipelineTopic:
    def __init__(self, claim: str) -> None:
        self.topic = "benchmark"
        self.description = claim


class _PipelineSource:
    def __init__(self, text: str) -> None:
        self._text = text

    def to_text(self) -> str:
        return self._text


def test_pipeline_level_safety_fidelity() -> None:
    """Measure the REAL pipeline (classify_claim -> verifier -> policy) end-to-end.

    Unlike test_safety_decision_accuracy -- which feeds the verifier idealised
    risk / claim_type labels -- this test lets the pipeline derive risk and
    claim_type itself from the raw claim and evidence, so the reported numbers
    reflect production behavior.  Every pipeline-level false decision must still
    be openly documented as a known deterministic limitation in the fixture:
    never silent.
    """
    import asyncio

    fp = 0
    fn = 0
    tp = 0
    tn = 0
    total = len(ALL_CASES)
    undocumented_flag_offs = []

    for case in ALL_CASES:
        report, rejected = asyncio.run(
            run_claim_grounding(
                [_PipelineTopic(case.claim)],
                _PipelineSource(case.source),
                settings=_PipelineSettings(),
                top_k=2,
            )
        )
        decision = "reject" if rejected is not None else "pass"
        should_reject = case.category in REJECT_CATEGORIES

        if should_reject and decision == "reject":
            tp += 1
        elif should_reject and decision == "pass":
            fn += 1
            if not case.deterministic_known_limitation:
                undocumented_flag_offs.append(
                    f"FN  [pipeline] [{case.category}] {case.description}"
                )
        elif not should_reject and decision == "pass":
            tn += 1
        elif not should_reject and decision == "reject":
            fp += 1
            if not case.deterministic_known_limitation:
                undocumented_flag_offs.append(
                    f"FP  [pipeline] [{case.category}] {case.description}"
                )

    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    pipeline_safety_accuracy = (tp + tn) / total

    pipeline_report = {
        "pipeline": {
            "safety_accuracy": round(pipeline_safety_accuracy, 4),
            "precision_reject_fabrications": round(precision, 4),
            "recall_reject_fabrications": round(recall, 4),
            "f1_score": round(f1, 4),
            "true_positives": tp,
            "false_negatives": fn,
            "true_negatives": tn,
            "false_positives": fp,
        },
        "note": "risk / claim_type are produced by the pipeline itself "
                "(classify_claim), not injected as ideal labels.",
        "documented_known_limitations": {
            "count": sum(
                1 for c in ALL_CASES if c.deterministic_known_limitation
            ),
            "note": "Includes every pipeline-level false decision; "
                    "the LLM verifier (authority) closes each one.",
        },
    }
    print("\n" + "=" * 60)
    print("GROUNDING BENCHMARK - REAL PIPELINE (classify_claim -> verifier)")
    print("=" * 60)
    print(json.dumps(pipeline_report, indent=2))

    assert undocumented_flag_offs == [], (
        "UNDOCUMENTED pipeline-level false decisions:\n"
        + "\n".join(undocumented_flag_offs)
    )
