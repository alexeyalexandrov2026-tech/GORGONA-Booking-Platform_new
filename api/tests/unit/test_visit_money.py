"""L8a (R2): catalog prices are hundredths; billing converts them exactly to minor units."""

import pytest

from gorgona_booking.business.visit_billing import VisitPriceNotExactError, catalog_minor


@pytest.mark.parametrize(
    ("price_cents", "units", "minor"),
    [(5000, 2, 5000), (500000, 0, 5000), (1000, 3, 10000), (1234, 3, 12340), (0, 0, 0)],
)
def test_a_catalog_price_converts_exactly(price_cents: int, units: int, minor: int) -> None:
    assert catalog_minor(price_cents, units) == minor


def test_an_inexact_price_is_refused() -> None:
    # 123.45 cannot be written in a currency without decimals; it is never rounded.
    with pytest.raises(VisitPriceNotExactError):
        catalog_minor(12345, 0)
