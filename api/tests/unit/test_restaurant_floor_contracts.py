"""Unit contract checks for REST-01 Slice 1: floor areas, tables and reservations."""

from datetime import UTC, datetime, timedelta
from uuid import uuid7

import pytest
from pydantic import ValidationError

from gorgona_booking.auth.permissions import (
    DELEGABLE_PERMISSIONS,
    PERMISSIONS_VERSION,
    ROLE_PERMISSIONS,
    Permission,
)
from gorgona_booking.business import modules
from gorgona_booking.business.readiness_registry import Readiness
from gorgona_booking.business.restaurant_floor import (
    AreaInput,
    ReservationEventInput,
    ReservationInput,
    TableInput,
)


def test_restaurant_module_is_implemented_and_not_enableable() -> None:
    assert modules.MODULE_REGISTRY_VERSION == 8
    mod = modules.MODULES_BY_ID["restaurant"]
    assert mod.readiness is Readiness.IMPLEMENTED
    assert mod.enableable is False
    assert set(mod.depends_on) == {
        "booking_resources",
        "counterparties",
        "finance_documents",
        "inventory",
        "workforce",
    }


def test_restaurant_permissions_are_role_scoped_and_never_delegated() -> None:
    assert PERMISSIONS_VERSION == 17
    rest_perms = {
        Permission.RESTAURANT_READ,
        Permission.RESTAURANT_KITCHEN,
        Permission.RESTAURANT_SERVICE,
        Permission.RESTAURANT_MANAGE,
    }
    assert not (rest_perms & DELEGABLE_PERMISSIONS)
    assert Permission.RESTAURANT_READ in ROLE_PERMISSIONS["artist"]
    assert Permission.RESTAURANT_KITCHEN in ROLE_PERMISSIONS["artist"]
    assert Permission.RESTAURANT_SERVICE not in ROLE_PERMISSIONS["artist"]
    assert Permission.RESTAURANT_MANAGE not in ROLE_PERMISSIONS["artist"]
    assert Permission.RESTAURANT_SERVICE in ROLE_PERMISSIONS["front_desk"]
    assert Permission.RESTAURANT_MANAGE not in ROLE_PERMISSIONS["front_desk"]
    assert Permission.RESTAURANT_MANAGE in ROLE_PERMISSIONS["manager"]
    assert Permission.RESTAURANT_MANAGE in ROLE_PERMISSIONS["owner"]


def test_area_and_table_inputs_enforce_bounds_and_text_rules() -> None:
    loc, area = uuid7(), uuid7()
    parsed_area = AreaInput.model_validate(
        {
            "schema_version": 1,
            "expected_revision": 0,
            "location_id": loc,
            "name": "  Main Dining  ",
            "service_style": "dining",
        }
    )
    assert parsed_area.name == "Main Dining"
    with pytest.raises(ValidationError):
        AreaInput.model_validate(
            {
                "schema_version": 1,
                "expected_revision": 0,
                "location_id": loc,
                "name": "Bad\nName",
                "service_style": "dining",
            }
        )
    parsed_table = TableInput.model_validate(
        {
            "schema_version": 1,
            "expected_revision": 0,
            "location_id": loc,
            "area_id": area,
            "code": "T-12",
            "min_covers": 2,
            "max_covers": 6,
        }
    )
    assert parsed_table.code == "T-12"
    with pytest.raises(ValidationError):
        TableInput.model_validate(
            {
                "schema_version": 1,
                "expected_revision": 0,
                "location_id": loc,
                "area_id": area,
                "code": "T-12",
                "min_covers": 6,
                "max_covers": 4,
            }
        )


def test_reservation_and_event_inputs_enforce_interval_and_action() -> None:
    start = datetime(2030, 5, 10, 18, 0, tzinfo=UTC)
    valid = ReservationInput.model_validate(
        {
            "schema_version": 1,
            "table_id": uuid7(),
            "guest_name": "Alex Guest",
            "party_size": 4,
            "starts_at": start,
            "ends_at": start + timedelta(hours=2),
            "note": "Window table",
        }
    )
    assert valid.party_size == 4
    with pytest.raises(ValidationError):
        ReservationInput.model_validate(
            {
                "schema_version": 1,
                "table_id": uuid7(),
                "guest_name": "Alex Guest",
                "party_size": 4,
                "starts_at": start,
                "ends_at": start,
            }
        )
    with pytest.raises(ValidationError):
        ReservationInput.model_validate(
            {
                "schema_version": 1,
                "table_id": uuid7(),
                "guest_name": "Alex Guest",
                "party_size": 4,
                "starts_at": start,
                "ends_at": start + timedelta(hours=25),
            }
        )
    ev = ReservationEventInput.model_validate(
        {"schema_version": 1, "expected_revision": 1, "action": "seat"}
    )
    assert ev.action == "seat"
    with pytest.raises(ValidationError):
        ReservationEventInput.model_validate(
            {"schema_version": 1, "expected_revision": 0, "action": "seat"}
        )
