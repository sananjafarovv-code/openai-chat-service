from decimal import Decimal

import pytest

from app.core.exceptions import PricingNotConfiguredError
from app.services.pricing import PricingService


def test_pricing_uses_decimal_and_current_luna_rates() -> None:
    result = PricingService().calculate(
        model="gpt-5.6-luna",
        input_tokens=1_000,
        output_tokens=500,
    )

    assert result.input_cost == Decimal("0.0002000000")
    assert result.output_cost == Decimal("0.0006000000")
    assert result.total_cost == Decimal("0.0008000000")


def test_pricing_uses_current_terra_rates() -> None:
    result = PricingService().calculate(
        model="gpt-5.6-terra",
        input_tokens=1_000,
        output_tokens=500,
    )

    assert result.input_cost == Decimal("0.0020000000")
    assert result.output_cost == Decimal("0.0060000000")
    assert result.total_cost == Decimal("0.0080000000")


def test_pricing_rejects_unknown_model() -> None:
    with pytest.raises(PricingNotConfiguredError):
        PricingService().calculate("unknown-model", input_tokens=1, output_tokens=1)


def test_pricing_accounts_for_cached_and_cache_write_tokens() -> None:
    result = PricingService().calculate(
        model="gpt-5.6-luna",
        input_tokens=1_000,
        cached_input_tokens=200,
        cache_write_tokens=100,
        output_tokens=500,
    )

    assert result.uncached_input_cost == Decimal("0.0001400000")
    assert result.cached_input_cost == Decimal("0.0000040000")
    assert result.cache_write_cost == Decimal("0.0000250000")
    assert result.input_cost == Decimal("0.0001690000")
    assert result.output_cost == Decimal("0.0006000000")
    assert result.total_cost == Decimal("0.0007690000")
    assert result.long_context_applied is False


def test_pricing_applies_long_context_multiplier() -> None:
    result = PricingService().calculate(
        model="gpt-5.6-luna",
        input_tokens=272_001,
        output_tokens=1_000,
    )

    assert result.input_price_per_1m == Decimal("0.40")
    assert result.output_price_per_1m == Decimal("1.800")
    assert result.input_cost == Decimal("0.1088004000")
    assert result.output_cost == Decimal("0.0018000000")
    assert result.total_cost == Decimal("0.1106004000")
    assert result.long_context_applied is True


@pytest.mark.parametrize(
    ("input_tokens", "output_tokens", "cached_tokens", "cache_write_tokens"),
    [
        (-1, 1, 0, 0),
        (1, -1, 0, 0),
        (10, 1, 8, 3),
    ],
)
def test_pricing_rejects_invalid_usage(
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int,
    cache_write_tokens: int,
) -> None:
    with pytest.raises(ValueError):
        PricingService().calculate(
            "gpt-5.6-luna",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cached_tokens,
            cache_write_tokens=cache_write_tokens,
        )
