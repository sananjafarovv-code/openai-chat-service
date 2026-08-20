from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.core.exceptions import PricingNotConfiguredError


TOKENS_PER_MILLION = Decimal("1000000")
MONEY_QUANTUM = Decimal("0.0000000001")


@dataclass(frozen=True)
class ModelPricing:
    input_per_1m: Decimal
    cached_input_per_1m: Decimal
    cache_write_per_1m: Decimal
    output_per_1m: Decimal
    long_context_threshold: int
    long_context_input_multiplier: Decimal
    long_context_output_multiplier: Decimal


MODEL_PRICING: dict[str, ModelPricing] = {
    "gpt-5.6-luna": ModelPricing(
        input_per_1m=Decimal("0.20"),
        cached_input_per_1m=Decimal("0.02"),
        cache_write_per_1m=Decimal("0.25"),
        output_per_1m=Decimal("1.20"),
        long_context_threshold=272_000,
        long_context_input_multiplier=Decimal("2"),
        long_context_output_multiplier=Decimal("1.5"),
    ),
    "gpt-5.6-terra": ModelPricing(
        input_per_1m=Decimal("2.00"),
        cached_input_per_1m=Decimal("0.20"),
        cache_write_per_1m=Decimal("2.50"),
        output_per_1m=Decimal("12.00"),
        long_context_threshold=272_000,
        long_context_input_multiplier=Decimal("2"),
        long_context_output_multiplier=Decimal("1.5"),
    ),
}


@dataclass(frozen=True)
class PricingBreakdown:
    input_price_per_1m: Decimal
    cached_input_price_per_1m: Decimal
    cache_write_price_per_1m: Decimal
    output_price_per_1m: Decimal
    uncached_input_cost: Decimal
    cached_input_cost: Decimal
    cache_write_cost: Decimal
    input_cost: Decimal
    output_cost: Decimal
    total_cost: Decimal
    long_context_applied: bool


class PricingService:
    def __init__(self, pricing: dict[str, ModelPricing] | None = None) -> None:
        self._pricing = pricing if pricing is not None else MODEL_PRICING

    def ensure_model_supported(self, model: str) -> None:
        if model not in self._pricing:
            raise PricingNotConfiguredError(model)

    def calculate(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cached_input_tokens: int = 0,
        cache_write_tokens: int = 0,
    ) -> PricingBreakdown:
        self.ensure_model_supported(model)
        model_pricing = self._pricing[model]

        token_counts = (input_tokens, output_tokens, cached_input_tokens, cache_write_tokens)
        if any(token_count < 0 for token_count in token_counts):
            raise ValueError("Token counts must not be negative.")
        if cached_input_tokens + cache_write_tokens > input_tokens:
            raise ValueError("Cached and cache-write tokens exceed total input tokens.")

        uncached_input_tokens = input_tokens - cached_input_tokens - cache_write_tokens
        long_context_applied = input_tokens > model_pricing.long_context_threshold
        input_multiplier = (
            model_pricing.long_context_input_multiplier
            if long_context_applied
            else Decimal("1")
        )
        output_multiplier = (
            model_pricing.long_context_output_multiplier
            if long_context_applied
            else Decimal("1")
        )

        input_price = model_pricing.input_per_1m * input_multiplier
        cached_input_price = model_pricing.cached_input_per_1m * input_multiplier
        cache_write_price = model_pricing.cache_write_per_1m * input_multiplier
        output_price = model_pricing.output_per_1m * output_multiplier

        uncached_input_cost = (
            Decimal(uncached_input_tokens) / TOKENS_PER_MILLION * input_price
        ).quantize(MONEY_QUANTUM)
        cached_input_cost = (
            Decimal(cached_input_tokens) / TOKENS_PER_MILLION * cached_input_price
        ).quantize(MONEY_QUANTUM)
        cache_write_cost = (
            Decimal(cache_write_tokens) / TOKENS_PER_MILLION * cache_write_price
        ).quantize(MONEY_QUANTUM)
        output_cost = (
            Decimal(output_tokens) / TOKENS_PER_MILLION * output_price
        ).quantize(MONEY_QUANTUM)
        input_cost = (
            uncached_input_cost + cached_input_cost + cache_write_cost
        ).quantize(MONEY_QUANTUM)

        return PricingBreakdown(
            input_price_per_1m=input_price,
            cached_input_price_per_1m=cached_input_price,
            cache_write_price_per_1m=cache_write_price,
            output_price_per_1m=output_price,
            uncached_input_cost=uncached_input_cost,
            cached_input_cost=cached_input_cost,
            cache_write_cost=cache_write_cost,
            input_cost=input_cost,
            output_cost=output_cost,
            total_cost=(input_cost + output_cost).quantize(MONEY_QUANTUM),
            long_context_applied=long_context_applied,
        )
