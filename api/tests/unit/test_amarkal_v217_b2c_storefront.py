"""Unit tests for AMARKAL v2.17.0: 1-Click B2C Storefront Builder & Promo Engine."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid7

import pytest

from gorgona_booking.business.b2c_storefront import (
    B2CPromoCodeView,
    calculate_promo_discount_cents,
)


def _promo(**overrides: object) -> B2CPromoCodeView:
    base = {
        "id": uuid7(),
        "code": "WELCOME15",
        "discount_kind": "percent",
        "discount_value": 15,
        "min_subtotal_cents": 5000,
        "max_redemptions": 100,
        "redemptions_count": 2,
        "expires_at": datetime.now(UTC) + timedelta(days=30),
        "is_active": True,
        "created_at": datetime.now(UTC),
    }
    base.update(overrides)
    return B2CPromoCodeView(**base)  # type: ignore[arg-type]


def test_percent_and_fixed_promo_discount_exact_integer_cents() -> None:
    disc, code, msg = calculate_promo_discount_cents(subtotal_cents=10_000, promo=_promo())
    assert disc == 1500
    assert code == "WELCOME15"
    assert msg is not None
    assert "15% off" in msg

    fixed = _promo(code="SAVE25", discount_kind="fixed_cents", discount_value=2500)
    disc2, code2, msg2 = calculate_promo_discount_cents(subtotal_cents=10_000, promo=fixed)
    assert disc2 == 2500
    assert code2 == "SAVE25"
    assert msg2 is not None
    assert "$25.00 off" in msg2

    # Never reduces total below Stripe minimum $0.50 (50 cents)
    huge = _promo(
        code="HUGE", discount_kind="fixed_cents", discount_value=99_000, min_subtotal_cents=0
    )
    disc3, _, _ = calculate_promo_discount_cents(subtotal_cents=1000, promo=huge)
    assert disc3 == 950


def test_promo_validation_rejects_expired_inactive_min_and_limit() -> None:
    with pytest.raises(ValueError, match="inactive"):
        calculate_promo_discount_cents(subtotal_cents=10_000, promo=_promo(is_active=False))

    with pytest.raises(ValueError, match="expired"):
        calculate_promo_discount_cents(
            subtotal_cents=10_000,
            promo=_promo(expires_at=datetime.now(UTC) - timedelta(hours=1)),
        )

    with pytest.raises(ValueError, match="redemption limit"):
        calculate_promo_discount_cents(
            subtotal_cents=10_000,
            promo=_promo(max_redemptions=5, redemptions_count=5),
        )

    with pytest.raises(ValueError, match="minimum order"):
        calculate_promo_discount_cents(
            subtotal_cents=2000,
            promo=_promo(min_subtotal_cents=5000),
        )
