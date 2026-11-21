"""Unit contract checks for REST-01 Slice 3 checks, kitchen tickets and consumption."""

from datetime import date
from uuid import uuid7

import pytest
from pydantic import ValidationError

from gorgona_booking.business import restaurant_checks as checks


def test_open_check_and_line_validation() -> None:
    loc = uuid7()
    chk = checks.OpenCheckInput(
        schema_version=1,
        location_id=loc,
        service_mode="takeout",
        currency="USD",
        guest_name="  Walk-in Guest  ",
        note="  No cutlery ",
    )
    assert chk.guest_name == "Walk-in Guest"
    assert chk.note == "No cutlery"
    assert chk.table_id is None
    assert chk.reservation_id is None

    with pytest.raises(ValidationError):
        checks.OpenCheckInput(
            schema_version=1,
            location_id=loc,
            service_mode="takeout",
            currency="usd",
        )

    line = checks.AddCheckLineInput(
        schema_version=1,
        menu_item_id=uuid7(),
        quantity=2,
        modifier_option_ids=[uuid7()],
        note="  Extra hot ",
    )
    assert line.note == "Extra hot"

    with pytest.raises(ValidationError):
        checks.AddCheckLineInput(
            schema_version=1,
            menu_item_id=uuid7(),
            quantity=0,
        )


def test_void_ticket_and_consumption_validation() -> None:
    void_in = checks.VoidCheckLineInput(schema_version=1, reason="  Guest changed mind ")
    assert void_in.reason == "Guest changed mind"

    with pytest.raises(ValidationError):
        checks.VoidCheckLineInput(schema_version=1, reason="   ")

    ev = checks.KitchenTicketEventInput(
        schema_version=1,
        expected_revision=1,
        action="start",
        note="On grill",
    )
    assert ev.action == "start"

    post = checks.PostConsumptionInput(
        schema_version=1,
        legal_entity_id=uuid7(),
        place_id=uuid7(),
        document_date=date(2026, 10, 1),
    )
    assert post.document_date == date(2026, 10, 1)
