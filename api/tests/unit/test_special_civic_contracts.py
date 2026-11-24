"""Unit contract tests for SPECIAL-04 (0148): Staffing, advisory, orgs & public admin."""

from datetime import date
from uuid import uuid7

import pytest
from pydantic import ValidationError

from gorgona_booking.auth.permissions import PERMISSIONS_VERSION, Permission
from gorgona_booking.business import modules
from gorgona_booking.business.readiness_registry import Readiness
from gorgona_booking.business.special_civic import (
    CivicAllocationInput,
    CivicAuditEventInput,
    CivicCaseInput,
    CivicProgramInput,
)


def test_public_civic_module_registered_implemented_not_enableable() -> None:
    assert modules.MODULE_REGISTRY_VERSION == 16
    assert PERMISSIONS_VERSION == 25
    mod = modules.MODULES_BY_ID["public_civic"]
    assert mod.readiness is Readiness.IMPLEMENTED
    assert mod.enableable is False
    assert Permission.CIVIC_READ.value == "civic.read"
    assert Permission.CIVIC_WORK.value == "civic.work"
    assert Permission.CIVIC_MANAGE.value == "civic.manage"


def test_civic_contracts_validate_codes_and_date_ranges() -> None:
    loc, prog, cp, case_id = uuid7(), uuid7(), uuid7(), uuid7()
    p = CivicProgramInput(
        schema_version=1,
        expected_revision=0,
        location_id=loc,
        program_domain="public_service_program",
        code="permit_2026",
        title="Municipal Permit Issuance",
        requires_dual_review=True,
    )
    assert p.code == "PERMIT_2026"

    c = CivicCaseInput(
        schema_version=1,
        expected_revision=0,
        location_id=loc,
        program_id=prog,
        subject_counterparty_id=cp,
        case_number="case-1001",
        summary="Application for commercial signage permit",
    )
    assert c.case_number == "CASE-1001"

    with pytest.raises(ValidationError):
        CivicAllocationInput(
            schema_version=1,
            expected_revision=0,
            location_id=loc,
            case_id=case_id,
            allocation_kind="public_permit",
            reference_code="PRM-1",
            effective_from=date(2026, 12, 1),
            effective_until=date(2026, 11, 1),
        )

    ev = CivicAuditEventInput(
        schema_version=1,
        location_id=loc,
        case_id=case_id,
        event_kind="compliance_check",
        details="Background verification attested",
    )
    assert ev.event_kind == "compliance_check"
