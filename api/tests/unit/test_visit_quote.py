"""L2c: a visit of several services is one quote (FAKE catalog data only)."""

import json
from dataclasses import replace

import pytest

from gorgona_booking.catalog.models import AddOnSpec, StageSpec, VariantSpec
from gorgona_booking.catalog.quote import (
    IncompatibleSelectionError,
    ServiceNotBookableError,
    build_quote,
    build_visit_quote,
)
from tests.unit.test_quote import fake_add_on, fake_variant

CUT = fake_variant("FAKE_CUT", 45, 4000, {"FAKE_CUT"})
COLOUR = replace(
    fake_variant("FAKE_COLOUR", 110, 9000, {"FAKE_COLOUR"}),
    stages=(
        StageSpec("active", 30, ("specialist", "chair")),
        StageSpec("processing", 60, ("chair", "equipment")),
        StageSpec("finish", 20, ("specialist", "chair")),
    ),
)
GLOSS = fake_add_on("FAKE_GLOSS", 10, 1500, provides={"FAKE_GLOSS"}, requires={"FAKE_COLOUR"})
WASH = fake_add_on("FAKE_WASH", 5, 500, provides={"FAKE_WASH"})


# L2-12 ------------------------------------------------------------------------------


def test_two_services_are_one_quote_in_order() -> None:
    quote = build_visit_quote([(COLOUR, [GLOSS]), (CUT, [WASH])])
    assert [(line.kind, line.code) for line in quote.lines] == [
        ("variant", "FAKE_COLOUR"),
        ("add_on", "FAKE_GLOSS"),
        ("variant", "FAKE_CUT"),
        ("add_on", "FAKE_WASH"),
    ]
    assert quote.total_cents == 9000 + 1500 + 4000 + 500
    assert quote.booking_duration_minutes == 110 + 10 + 45 + 5
    # The colour's gloss joins its last active stage (L1 rule; "finish" is not "active"); the
    # cut is one active stage with its wash.
    assert [(s.kind, s.minutes, s.resources) for s in quote.stages] == [
        ("active", 40, ("specialist", "chair")),
        ("processing", 60, ("chair", "equipment")),
        ("finish", 20, ("specialist", "chair")),
        ("active", 50, ("specialist",)),
    ]
    snapshot = quote.snapshot()
    assert snapshot["version"] == 2
    assert sum(s.minutes for s in quote.stages) == quote.booking_duration_minutes
    assert len(snapshot["stages"]) == 4  # type: ignore[arg-type]


def test_two_unstaged_services_still_quote_stages() -> None:
    quote = build_visit_quote([(CUT, []), (fake_variant("FAKE_STYLE", 30, 2500, {"X"}), [])])
    assert [(s.kind, s.minutes, s.resources) for s in quote.stages] == [
        ("active", 45, ("specialist",)),
        ("active", 30, ("specialist",)),
    ]
    assert quote.snapshot()["version"] == 2


# L2-15 ------------------------------------------------------------------------------


@pytest.mark.parametrize(("variant", "add_ons"), [(CUT, []), (CUT, [WASH]), (COLOUR, [GLOSS])])
def test_one_line_is_exactly_the_single_service_quote(
    variant: VariantSpec, add_ons: list[AddOnSpec]
) -> None:
    visit = build_visit_quote([(variant, add_ons)])
    single = build_quote(variant, add_ons)
    assert visit == single
    assert json.dumps(visit.snapshot(), sort_keys=True) == json.dumps(
        single.snapshot(), sort_keys=True
    )


# L2-13 ------------------------------------------------------------------------------


def _reason(lines: list[tuple[VariantSpec, list[AddOnSpec]]]) -> str:
    with pytest.raises((IncompatibleSelectionError, ServiceNotBookableError)) as caught:
        build_visit_quote(lines)
    return str(caught.value.details.get("reason"))


def test_a_component_provided_twice_across_lines_is_refused() -> None:
    other_cut = fake_variant("FAKE_CUT_LONG", 60, 5000, {"FAKE_CUT"})
    assert _reason([(CUT, []), (other_cut, [])]) == "duplicate_component"
    washed = fake_variant("FAKE_WASHED", 20, 1000, {"FAKE_WASH"})
    assert _reason([(washed, []), (CUT, [WASH])]) == "duplicate_component"


def test_a_requirement_met_by_another_line_is_accepted_and_none_refuses() -> None:
    assert build_visit_quote([(CUT, [GLOSS]), (COLOUR, [])]).total_cents == 4000 + 1500 + 9000
    assert _reason([(CUT, [GLOSS])]) == "requirement_missing"


def test_a_conflict_across_lines_is_refused() -> None:
    no_colour = fake_add_on("FAKE_NATURAL", 5, 100, conflicts_with={"FAKE_COLOUR"})
    assert _reason([(CUT, [no_colour]), (COLOUR, [])]) == "conflict"


def test_a_service_twice_another_currency_and_too_long_are_refused() -> None:
    assert _reason([(CUT, []), (CUT, [])]) == "duplicate_service"
    euro = replace(fake_variant("FAKE_EURO", 30, 1000, {"E"}), currency="EUR")
    assert _reason([(CUT, []), (euro, [])]) == "currency_mismatch"
    long_a = fake_variant("FAKE_LONG_A", 400, 1000, {"A"})
    long_b = fake_variant("FAKE_LONG_B", 400, 1000, {"B"})
    assert _reason([(long_a, []), (long_b, [])]) == "duration_too_long"


def test_an_empty_visit_or_too_many_lines_are_refused() -> None:
    with pytest.raises(IncompatibleSelectionError):
        build_visit_quote([])
    many: list[tuple[VariantSpec, list[AddOnSpec]]] = [
        (fake_variant(f"FAKE_{i}", 5, 100, {f"C{i}"}), []) for i in range(6)
    ]
    assert _reason(many) == "too_many_services"
