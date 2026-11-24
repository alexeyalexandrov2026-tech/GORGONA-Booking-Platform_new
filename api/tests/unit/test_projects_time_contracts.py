"""PRO-01 Slice 3 unit contract tests (ADR-0038)."""

from datetime import date

import pytest
from pydantic import ValidationError

from gorgona_booking.business.projects_time import (
    RecurringScheduleInput,
    TimeEntryDecisionInput,
    TimeEntryInput,
    advance_period,
    compute_time_amount_minor,
)


def test_compute_time_amount_rounding_and_non_billable() -> None:
    # 90 minutes at $250.00/hr (25000 minor) -> 37500
    assert (
        compute_time_amount_minor(duration_minutes=90, hourly_rate_minor=25000, billable=True)
        == 37500
    )
    # 20 minutes at $100.00/hr (10000 minor) -> 3333.33 -> 3333
    assert (
        compute_time_amount_minor(duration_minutes=20, hourly_rate_minor=10000, billable=True)
        == 3333
    )
    # 40 minutes at $100.00/hr (10000 minor) -> 6666.67 -> 6667
    assert (
        compute_time_amount_minor(duration_minutes=40, hourly_rate_minor=10000, billable=True)
        == 6667
    )
    # Non-billable always yields 0
    assert (
        compute_time_amount_minor(duration_minutes=120, hourly_rate_minor=30000, billable=False)
        == 0
    )


def test_advance_period_handles_month_ends_and_cadences() -> None:
    assert advance_period(date(2026, 1, 31), "monthly") == (date(2026, 2, 27), date(2026, 2, 28))
    assert advance_period(date(2026, 11, 1), "weekly") == (date(2026, 11, 7), date(2026, 11, 8))
    assert advance_period(date(2026, 11, 1), "biweekly") == (date(2026, 11, 14), date(2026, 11, 15))
    assert advance_period(date(2026, 11, 1), "quarterly") == (date(2027, 1, 31), date(2027, 2, 1))


def test_time_and_recurring_inputs_strict() -> None:
    t = TimeEntryInput(
        schema_version=1,
        expected_revision=0,
        work_date=date(2026, 11, 21),
        duration_minutes=45,
        hourly_rate_minor=20_000,
        description="Reviewed master services agreement.",
        submit=True,
    )
    assert t.submit is True

    d = TimeEntryDecisionInput(schema_version=1, expected_revision=1, decision="approve")
    assert d.decision == "approve"

    s = RecurringScheduleInput(
        schema_version=1,
        expected_revision=0,
        title="Monthly Bookkeeping Retainer",
        task_template_title="Close monthly books",
        cadence="monthly",
        next_run_date=date(2026, 12, 1),
        fixed_fee_minor=150_000,
    )
    assert s.cadence == "monthly"

    with pytest.raises(ValidationError):
        TimeEntryInput(
            schema_version=1,
            expected_revision=0,
            work_date=date(2026, 11, 21),
            duration_minutes=0,
            hourly_rate_minor=1000,
            description="Zero minutes rejected",
        )
