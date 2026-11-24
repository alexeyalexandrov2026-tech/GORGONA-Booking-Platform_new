"""R6b: overdue time and meter excess derived from the agreement and the inspections (FAKE data).

docs/plan/PACKAGE_R6B_DESIGN_2026-11-07.md decisions 2-4.
"""

from datetime import UTC, datetime, timedelta

from gorgona_booking.business.rental_usage import derive_usage

END = datetime(2031, 6, 3, 10, tzinfo=UTC)
HANDED = datetime(2031, 6, 1, 10, tzinfo=UTC)


def usage(**changes: object) -> dict[str, object]:
    fields: dict[str, object] = {
        "period_end": END,
        "rental_days": 2,
        "meter_kind": "odometer",
        "allowance_per_day": 100,
        "excess_rate": 25,
        "handed_at": HANDED,
        "handover_meter": 1_000,
        "returned_at": END,
        "return_meter": 1_300,
        "as_of": END + timedelta(days=1),
    }
    fields.update(changes)
    return derive_usage(**fields).model_dump()  # type: ignore[arg-type]


def test_a_return_on_time_gives_the_excess_over_the_allowance() -> None:
    got = usage()
    assert got["state"] == "returned"
    assert (got["overdue_seconds"], got["overdue_hours"]) == (0, 0)
    assert (got["distance"], got["allowance"], got["excess"], got["excess_amount"]) == (
        300,
        200,
        100,
        2_500,
    )


def test_within_the_allowance_there_is_no_excess() -> None:
    got = usage(return_meter=1_150)
    assert (got["distance"], got["excess"], got["excess_amount"]) == (150, 0, 0)


def test_a_late_return_counts_started_hours() -> None:
    assert (usage(returned_at=END + timedelta(seconds=1))["overdue_hours"]) == 1
    got = usage(returned_at=END + timedelta(hours=1, seconds=1))
    assert (got["overdue_seconds"], got["overdue_hours"]) == (3_601, 2)
    early = usage(returned_at=END - timedelta(hours=5))
    assert (early["overdue_seconds"], early["overdue_hours"]) == (0, 0)


def test_while_out_the_read_time_counts_and_no_distance() -> None:
    got = usage(returned_at=None, return_meter=None, as_of=END + timedelta(minutes=30))
    assert got["state"] == "out"
    assert (got["overdue_seconds"], got["overdue_hours"]) == (1_800, 1)
    assert (got["distance"], got["excess"], got["excess_amount"]) == (None, None, None)
    assert got["allowance"] == 200
    inside = usage(returned_at=None, return_meter=None, as_of=END - timedelta(hours=1))
    assert inside["overdue_seconds"] == 0


def test_before_the_handover_nothing_is_counted() -> None:
    got = usage(handed_at=None, handover_meter=None, returned_at=None, return_meter=None)
    assert got["state"] == "not_handed_over"
    assert (got["overdue_seconds"], got["overdue_hours"], got["distance"]) == (0, 0, None)


def test_cards_without_allowance_or_rate_and_classes_without_a_meter() -> None:
    bare = usage(allowance_per_day=None)
    assert (bare["distance"], bare["allowance"], bare["excess"], bare["excess_amount"]) == (
        300,
        None,
        None,
        None,
    )
    unpriced = usage(excess_rate=None)
    assert (unpriced["excess"], unpriced["excess_amount"]) == (100, None)
    none = usage(meter_kind="none", handover_meter=None, return_meter=None)
    assert (none["distance"], none["allowance"], none["excess"]) == (None, None, None)
