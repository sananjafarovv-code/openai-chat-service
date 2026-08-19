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


def test_pricing_rejects_unknown_model() -> None:
    with pytest.raises(PricingNotConfiguredError):
        PricingService().calculate("unknown-model", input_tokens=1, output_tokens=1)
