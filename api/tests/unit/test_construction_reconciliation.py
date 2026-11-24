"""O6b decision 5: the reconciliation differences, as plain arithmetic (no database)."""

from gorgona_booking.business.construction_warranty import Totals, differences


def totals(**changes: int) -> Totals:
    base = {
        "contract_minor": 31007,
        "completed_minor": 31007,
        "budget_minor": 18333,
        "actual_minor": 6500,
        "billed_minor": 31007,
        "retained_minor": 3100,
        "released_minor": 1750,
        "due_settled_minor": 20000,
        "retainage_settled_minor": 2000,
    }
    return Totals(**{**base, **changes})


def test_differences_report_retainage_settled_before_its_release() -> None:
    found = differences(totals())
    assert found == {
        "contract_minus_billed_minor": 0,
        "completed_minus_billed_minor": 0,
        "billed_minus_settled_minor": 31007 - 22000,
        "held_minor": 1350,
        "retainage_settled_before_release_minor": 250,
        "budget_minus_actual_minor": 11833,
        "contract_minus_actual_minor": 24507,
    }
    # Settled within what was released: nothing is early, and the figure never goes below 0.
    for settled in (1750, 0):
        early = differences(totals(retainage_settled_minor=settled))
        assert early["retainage_settled_before_release_minor"] == 0, settled
    # Work done and not billed, and an overrun, show as they are (negative where it is so).
    found = differences(totals(billed_minor=20000, actual_minor=20000))
    assert (
        found["completed_minus_billed_minor"],
        found["contract_minus_billed_minor"],
        found["budget_minus_actual_minor"],
    ) == (11007, 11007, -1667)
