from __future__ import annotations

from decimal import Decimal

from app.ai.cost import ModelCost, cost_per_1k, estimate_cost, estimate_cost_for_text


class TestCostTable:
    def test_known_model(self) -> None:
        tier = cost_per_1k("gpt-4o-mini")
        assert tier is not None
        assert tier.input_per_1k == Decimal("0.000150")
        assert tier.output_per_1k == Decimal("0.000600")

    def test_unknown_model(self) -> None:
        assert cost_per_1k("unknown-model") is None

    def test_empty_model(self) -> None:
        assert cost_per_1k(None) is None
        assert cost_per_1k("") is None


class TestEstimateCost:
    def test_known_model(self) -> None:
        total = estimate_cost(input_tokens=1000, output_tokens=1000, model="gpt-4o-mini")
        assert total == Decimal("0.000750")

    def test_unknown_model_returns_none(self) -> None:
        assert estimate_cost(input_tokens=100, output_tokens=100, model="nope") is None

    def test_zero_usage(self) -> None:
        total = estimate_cost(input_tokens=0, output_tokens=0, model="gemini-1.5-flash")
        assert total == Decimal("0.000000")


class TestEstimateCostForText:
    def test_output_only_estimate(self) -> None:
        total = estimate_cost_for_text(text="hello world", model="gemini-1.5-flash")
        assert total == Decimal("0.000001")

    def test_unknown_model_returns_none(self) -> None:
        assert estimate_cost_for_text(text="hello", model="nope") is None
