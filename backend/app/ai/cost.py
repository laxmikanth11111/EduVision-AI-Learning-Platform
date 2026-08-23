"""AI cost estimation.

Cost tables are centralized here (per model, USD per 1K tokens). Providers can
override via ``AIProviderInfo``; this module provides the shared fallback used
for token accounting and future billing/analytics.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.ai.tokens import estimate_tokens

_ZERO = Decimal("0.000000")


@dataclass(frozen=True)
class ModelCost:
    input_per_1k: Decimal
    output_per_1k: Decimal


# USD per 1,000 tokens. Unknown models are treated as $0 until configured.
MODEL_COST_TABLE: dict[str, ModelCost] = {
    # Gemini
    "gemini-1.5-flash": ModelCost(Decimal("0.000075"), Decimal("0.000300")),
    "gemini-1.5-pro": ModelCost(Decimal("0.001250"), Decimal("0.005000")),
    "gemini-2.0-flash": ModelCost(Decimal("0.000100"), Decimal("0.000400")),
    "gemini-3.5-flash": ModelCost(Decimal("0.000100"), Decimal("0.000400")),
    # OpenAI
    "gpt-4o-mini": ModelCost(Decimal("0.000150"), Decimal("0.000600")),
    "gpt-4o": ModelCost(Decimal("0.002500"), Decimal("0.010000")),
    "gpt-4.1-mini": ModelCost(Decimal("0.000400"), Decimal("0.001600")),
    "gpt-4.1": ModelCost(Decimal("0.002000"), Decimal("0.008000")),
    "gpt-3.5-turbo": ModelCost(Decimal("0.000500"), Decimal("0.001500")),
}

# Normalize on full model name only (do not substring-match prefixes that could
# silently match the wrong tier, e.g. gpt-4o vs gpt-4o-mini).
MODEL_COST_LOOKUP = dict(MODEL_COST_TABLE)


def cost_per_1k(model: str | None) -> ModelCost | None:
    """Return the configured cost tier for ``model`` or ``None`` if unknown."""
    if not model:
        return None
    return MODEL_COST_LOOKUP.get(model)


def estimate_cost(
    *,
    input_tokens: int,
    output_tokens: int,
    model: str | None,
    currency: str = "USD",
) -> Decimal | None:
    """Estimate the cost in ``currency`` for a token usage record.

    Returns ``None`` when no cost tier is configured for the model.
    """
    tier = cost_per_1k(model)
    if tier is None:
        return None

    input_cost = (Decimal(input_tokens) / Decimal(1000)) * tier.input_per_1k
    output_cost = (Decimal(output_tokens) / Decimal(1000)) * tier.output_per_1k
    total = (input_cost + output_cost).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    return total


def estimate_cost_for_text(
    *,
    text: str,
    model: str | None,
    currency: str = "USD",
) -> Decimal | None:
    """Cost estimate when only the response text is available (fallback)."""
    output_tokens = estimate_tokens(text)
    tier = cost_per_1k(model)
    if tier is None:
        return None
    output_cost = (Decimal(output_tokens) / Decimal(1000)) * tier.output_per_1k
    return output_cost.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
