"""L2a pure parts: stage spans and the specialist-aware slot finder."""

from datetime import UTC, datetime, timedelta

from gorgona_booking.booking.stages import stage_spans
from gorgona_booking.catalog.models import StageSpec
from gorgona_booking.customer.availability import available_starts

COLOUR = (
    StageSpec("active", 30, ("specialist", "chair")),
    StageSpec("processing", 60, ("chair", "equipment")),
    StageSpec("finish", 20, ("specialist", "chair")),
)


def test_consecutive_stages_on_one_kind_join_and_a_gap_splits() -> None:
    assert stage_spans(COLOUR) == {
        "specialist": [(0, 30), (90, 110)],
        "chair": [(0, 110)],
        "equipment": [(30, 90)],
    }


def test_a_single_active_stage_is_one_span() -> None:
    assert stage_spans((StageSpec("active", 45, ("specialist",)),)) == {"specialist": [(0, 45)]}


def test_the_artist_may_be_busy_while_the_colour_develops() -> None:
    day = datetime(2031, 6, 2, 9, tzinfo=UTC)
    hours = [(day, day + timedelta(hours=8))]
    busy = [(day + timedelta(minutes=60), day + timedelta(minutes=110))]
    whole = available_starts(hours, hours, busy, minutes=110, step=30, after=day)
    staged = available_starts(
        hours, hours, busy, minutes=110, step=30, after=day, works=[(0, 30), (90, 110)]
    )
    # The artist is busy 10:00-10:50. From 9:00 the staged visit needs the artist again at
    # 10:30 (refused); from 9:30 the artist works 9:30-10:00 and 11:00-11:20 (allowed).
    assert day not in whole
    assert day not in staged
    assert day + timedelta(minutes=30) in staged  # works 9:30-10:00 and 11:00-11:20
    assert day + timedelta(minutes=30) not in whole
    assert set(whole) <= set(staged)
