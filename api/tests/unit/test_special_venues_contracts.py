"""Unit contract tests for SPECIAL-01 (0145): hospitality_events module & domain inputs."""

from datetime import date
from uuid import uuid7

import pytest
from pydantic import ValidationError

from gorgona_booking.auth.permissions import DELEGABLE_PERMISSIONS, PERMISSIONS_VERSION, Permission
from gorgona_booking.business import modules
from gorgona_booking.business.readiness_registry import Readiness
from gorgona_booking.business.special_venues import EventInput, ProgramInput, RoomInput


def test_hospitality_events_module_and_special_permissions_registered() -> None:
    assert modules.MODULE_REGISTRY_VERSION == 15
    mod = modules.MODULES_BY_ID["hospitality_events"]
    assert mod.readiness == Readiness.IMPLEMENTED
    assert mod.enableable is False
    assert set(mod.depends_on) == {"counterparties"}
    assert PERMISSIONS_VERSION == 24
    for perm in (Permission.SPECIAL_READ, Permission.SPECIAL_WORK, Permission.SPECIAL_MANAGE):
        assert perm not in DELEGABLE_PERMISSIONS


def test_special_venues_contracts_validate_inputs() -> None:
    prog = ProgramInput(
        expected_revision=0,
        location_id=uuid7(),
        code="yoga_10",
        title="10-Class Yoga Pack",
        program_kind="fitness_membership",
        capacity=20,
        included_sessions=10,
        price_minor=15000,
        currency="USD",
    )
    assert prog.code == "YOGA_10"

    with pytest.raises(ValidationError):
        RoomInput(
            expected_revision=0,
            location_id=uuid7(),
            room_number="101",
            room_type="Suite",
            max_guests=0,
            currency="USD",
        )
    with pytest.raises(ValidationError):
        EventInput(
            expected_revision=0,
            location_id=uuid7(),
            code="A",
            title="Too short code",
            event_date=date(2026, 11, 1),
            capacity=100,
            currency="USD",
        )
