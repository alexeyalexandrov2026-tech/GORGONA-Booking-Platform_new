"""Unit contract tests for SPECIAL-03 (0147): Assets, inspections, work orders and incidents."""

from decimal import Decimal
from uuid import uuid7

import pytest
from pydantic import ValidationError

from gorgona_booking.auth.permissions import PERMISSIONS_VERSION, Permission
from gorgona_booking.business import modules
from gorgona_booking.business.readiness_registry import Readiness
from gorgona_booking.business.special_assets import (
    AssetIncidentInput,
    AssetInspectionInput,
    AssetWorkOrderInput,
    ManagedAssetInput,
)


def test_assets_module_registered_implemented_not_enableable() -> None:
    assert modules.MODULE_REGISTRY_VERSION == 16
    assert PERMISSIONS_VERSION == 25
    mod = modules.MODULES_BY_ID["assets"]
    assert mod.readiness is Readiness.IMPLEMENTED
    assert mod.enableable is False
    assert Permission.ASSETS_READ.value == "assets.read"
    assert Permission.ASSETS_WORK.value == "assets.work"
    assert Permission.ASSETS_MANAGE.value == "assets.manage"


def test_asset_contracts_validate_codes_and_readings() -> None:
    loc = uuid7()
    aid = uuid7()
    asset = ManagedAssetInput(
        schema_version=1,
        expected_revision=0,
        location_id=loc,
        asset_domain="utility_infrastructure",
        code="sub_01",
        name="North Substation",
    )
    assert asset.code == "SUB_01"

    insp = AssetInspectionInput(
        schema_version=1,
        location_id=loc,
        asset_id=aid,
        inspection_kind="meter_reading",
        outcome="passed",
        meter_reading=Decimal("1240.500"),
    )
    assert insp.meter_reading == Decimal("1240.500")

    with pytest.raises(ValidationError):
        AssetInspectionInput(
            schema_version=1,
            location_id=loc,
            asset_id=aid,
            inspection_kind="meter_reading",
            outcome="passed",
            meter_reading=Decimal("-1"),
        )

    wo = AssetWorkOrderInput(
        schema_version=1,
        expected_revision=0,
        location_id=loc,
        asset_id=aid,
        work_kind="remediation",
        summary="Seal valve leak",
    )
    assert wo.status == "open"

    inc = AssetIncidentInput(
        schema_version=1,
        expected_revision=0,
        location_id=loc,
        asset_id=aid,
        incident_kind="environmental_spill",
        severity="critical",
        description="Containment sensor triggered",
    )
    assert inc.status == "open"
