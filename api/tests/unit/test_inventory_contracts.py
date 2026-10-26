"""Package J1 contracts, permissions and registry rules; no database."""

from uuid import uuid7

import pytest
from pydantic import ValidationError

from gorgona_booking.auth.permissions import (
    DELEGABLE_PERMISSIONS,
    PERMISSIONS_VERSION,
    PLATFORM_SUPPORT_PERMISSIONS,
    ROLE_PERMISSIONS,
    Permission,
)
from gorgona_booking.business import modules
from gorgona_booking.business.inventory_contracts import ItemInput, PlaceInput
from gorgona_booking.business.readiness_registry import SCENARIOS, Readiness, at_least

ITEM: dict[str, object] = {
    "expected_revision": 0,
    "code": "DYE-01",
    "name": "FAKE dye",
    "unit": "ml",
    "quantity_scale": 1,
}
PLACE: dict[str, object] = {
    "expected_revision": 0,
    "location_id": str(uuid7()),
    "code": "BACK",
    "name": "FAKE back room",
}


def test_inventory_rights_belong_to_admins_and_are_never_delegated() -> None:
    assert PERMISSIONS_VERSION == 10
    rights = {Permission.INVENTORY_READ, Permission.INVENTORY_MANAGE}
    for role in ("owner", "manager"):
        assert rights <= ROLE_PERMISSIONS[role]
    for role in ("front_desk", "artist"):
        assert not rights & ROLE_PERMISSIONS[role]
    assert not rights & DELEGABLE_PERMISSIONS
    assert not rights & PLATFORM_SUPPORT_PERMISSIONS


def test_inventory_module_depends_on_finance_and_follows_stock_01() -> None:
    module = modules.MODULES_BY_ID["inventory"]
    scenario = next(s for s in SCENARIOS if s.id == "STOCK-01")
    assert modules.MODULE_REGISTRY_VERSION == 4
    assert module.kind is modules.ModuleKind.OPTIONAL
    assert module.depends_on == ("finance",)
    assert module.readiness is scenario.status
    assert module.enableable is at_least(scenario.status, modules.MINIMUM_READINESS)
    assert ("DEPENDENCY_MISSING", "inventory") in {
        (code, module_id) for code, module_id, _ in modules.selection_problems(["inventory"])
    }


def test_stock_01_is_technically_verified_and_inventory_may_be_enabled() -> None:
    # Owner 2026-10-20: «ok» to the STOCK-01 readiness record; never a pilot or production approval.
    scenario = next(s for s in SCENARIOS if s.id == "STOCK-01")
    assert (scenario.status, scenario.code_version, scenario.schema_version) == (
        Readiness.TECHNICALLY_VERIFIED,
        "ea74bec66808f217f7ea56370b9292b4844f7d2b",
        62,
    )
    assert "docs/plan/evidence/2026-10-15-stock-01-acceptance/ACCEPTANCE.md" in scenario.evidence
    assert "docs/plan/evidence/2026-10-20-stock-01-readiness/RECORD.md" in scenario.evidence
    assert "no production approval" in scenario.scope
    module = modules.MODULES_BY_ID["inventory"]
    assert module.enableable
    assert "cannot be enabled" not in module.limits
    assert "Screens are not implemented" not in module.limits


def test_material_and_place_inputs_accept_the_documented_shape() -> None:
    item = ItemInput.model_validate({**ITEM, "name": "  FAKE dye  ", "unit": " ml "})
    assert (item.name, item.unit, item.quantity_scale, item.archived) == (
        "FAKE dye",
        "ml",
        1,
        False,
    )
    place = PlaceInput.model_validate(PLACE)
    assert (place.code, place.archived, place.schema_version) == ("BACK", False, 1)


@pytest.mark.parametrize(
    "change",
    [
        {"code": "dye"},
        {"code": ""},
        {"code": "DYE 01"},
        {"code": "D" * 65},
        {"unit": ""},
        {"unit": "u" * 17},
        {"unit": "m\tl"},
        {"quantity_scale": -1},
        {"quantity_scale": 4},
        {"quantity_scale": 1.5},
        {"name": ""},
        {"name": "FAKE\ndye"},
        # Control characters of the C1 range too: PostgreSQL may refuse them as well.
        {"name": "FAKE\u0085dye"},
        {"unit": "m\u009fl"},
        {"expected_revision": -1},
        {"schema_version": 2},
        {"price": "1.00"},
    ],
)
def test_material_input_is_strict(change: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ItemInput.model_validate({**ITEM, **change})


@pytest.mark.parametrize(
    "change",
    [
        {"code": "back"},
        {"code": ""},
        {"location_id": "not-a-uuid"},
        {"name": " "},
        {"name": "FAKE\u0080room"},
        {"expected_revision": 2147483647},
        {"capacity": 5},
    ],
)
def test_place_input_is_strict(change: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        PlaceInput.model_validate({**PLACE, **change})
