"""I3 strict command shapes and elapsed time across DST folds."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import TypeAdapter, ValidationError

from gorgona_booking.business.timesheet_contracts import (
    ClockCommand,
    ClockInInput,
    CorrectionCommand,
    TimeCommand,
    microseconds,
)

NY = ZoneInfo("America/New_York")


def fold(hour: int, minute: int, repeated: int = 0) -> datetime:
    return datetime(2026, 11, 1, hour, minute, tzinfo=NY, fold=repeated)


def test_duration_counts_elapsed_microseconds_across_dst_fold() -> None:
    assert microseconds(fold(1, 45), fold(1, 15, 1)) == 30 * 60 * 1_000_000


def test_correct_break_order_uses_instants_across_repeated_wall_hours() -> None:
    value = CorrectionCommand(
        action="correct",
        expected_revision=2,
        starts_at=fold(0, 30),
        ends_at=fold(2, 30),
        reason="FAKE DST",
        breaks=[
            {"starts_at": fold(1, 30), "ends_at": fold(1, 45)},
            {"starts_at": fold(1, 5, 1), "ends_at": fold(1, 15, 1)},
        ],
    )
    assert len(value.breaks) == 2


def test_correct_refuses_breaks_reversed_in_real_time_even_if_wall_time_increases() -> None:
    with pytest.raises(ValidationError):
        CorrectionCommand(
            action="correct",
            expected_revision=2,
            starts_at=fold(0, 30),
            ends_at=fold(2, 30),
            reason="FAKE DST",
            breaks=[
                {"starts_at": fold(1, 10, 1), "ends_at": fold(1, 20, 1)},
                {"starts_at": fold(1, 30), "ends_at": fold(1, 40)},
            ],
        )


@pytest.mark.parametrize("value", [True, 1.0, "1", 0, 2147483647])
def test_clock_revision_is_a_strict_bounded_integer(value: object) -> None:
    with pytest.raises(ValidationError):
        ClockCommand.model_validate(
            {"expected_revision": value, "action": "clock_out", "at": "2026-10-11T12:00:00Z"}
        )


@pytest.mark.parametrize(
    "body",
    [
        {"action": "approve", "expected_revision": 2, "at": "2026-10-11T12:00:00Z"},
        {"action": "approve", "expected_revision": 2, "reason": "FAKE"},
        {"action": "decline", "expected_revision": 2},
        {"action": "clock_in", "expected_revision": 1, "at": "2026-10-11T12:00:00Z"},
        {
            "action": "clock_out",
            "expected_revision": 2,
            "at": "2026-10-11T12:00:00Z",
            "starts_at": "2026-10-10T12:00:00Z",
        },
    ],
)
def test_clock_commands_cannot_supply_a_different_snapshot_or_implicit_decision(
    body: object,
) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(TimeCommand).validate_python(body)


def test_start_requires_aware_supported_date_and_complete_shift_pair() -> None:
    with pytest.raises(ValidationError):
        ClockInInput.model_validate(
            {
                "staff_profile_id": "11111111-1111-4111-8111-111111111111",
                "starts_at": "2026-10-11T12:00:00",
            }
        )
