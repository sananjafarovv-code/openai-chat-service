from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.core.exceptions import PricingNotConfiguredError


TOKENS_PER_MILLION = Decimal("1000000")
MONEY_QUANTUM = Decimal("0.0000000001")


@dataclass(frozen=True)
class ModelPricing:
    input_per_1m: Decimal
    output_per_1m: Decimal


MODEL_PRICING: dict[str, ModelPricing] = {
    "gpt-5.6-luna": ModelPricing(
        input_per_1m=Decimal("0.20"),
        output_per_1m=Decimal("1.20"),
    ),
}


@dataclass(frozen=True)
class PricingBreakdown:
    input_price_per_1m: Decimal
    output_price_per_1m: Decimal
    input_cost: Decimal
    output_cost: Decimal
    total_cost: Decimal


class PricingService:
    def __init__(self, pricing: dict[str, ModelPricing] | None = None) -> None:
        self._pricing = pricing or MODEL_PRICING

    def ensure_model_supported(self, model: str) -> None:
        if model not in self._pricing:
            raise PricingNotConfiguredError(model)

    def calculate(self, model: str, input_tokens: int, output_tokens: int) -> PricingBreakdown:
        self.ensure_model_supported(model)
        model_pricing = self._pricing[model]

        input_cost = (
            Decimal(input_tokens) / TOKENS_PER_MILLION * model_pricing.input_per_1m
        ).quantize(MONEY_QUANTUM)
        output_cost = (
            Decimal(output_tokens) / TOKENS_PER_MILLION * model_pricing.output_per_1m
        ).quantize(MONEY_QUANTUM)

        return PricingBreakdown(
            input_price_per_1m=model_pricing.input_per_1m,
            output_price_per_1m=model_pricing.output_per_1m,
            input_cost=input_cost,
            output_cost=output_cost,
            total_cost=(input_cost + output_cost).quantize(MONEY_QUANTUM),
        )
