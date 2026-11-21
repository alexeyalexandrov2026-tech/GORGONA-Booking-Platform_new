"""PRO-01 Slice 1 unit contract tests (ADR-0038)."""

from datetime import date
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
from gorgona_booking.business.projects_matters import (
    PROJECTS_MODULE,
    ConflictCheckInput,
    MatterInput,
    MatterMemberInput,
)
from gorgona_booking.business.readiness_registry import Readiness


def test_projects_module_is_implemented_and_not_enableable() -> None:
    assert modules.MODULE_REGISTRY_VERSION == 11
    mod = modules.MODULES_BY_ID[PROJECTS_MODULE]
    assert mod.readiness is Readiness.IMPLEMENTED
    assert mod.enableable is False
    assert mod.depends_on == ("counterparties", "documents", "finance_documents")


def test_projects_permissions_are_role_scoped_and_never_delegated() -> None:
    assert PERMISSIONS_VERSION == 20
    pro_perms = {
        Permission.PROJECTS_READ,
        Permission.PROJECTS_WORK,
        Permission.PROJECTS_MANAGE,
    }
    assert pro_perms.isdisjoint(DELEGABLE_PERMISSIONS)
    assert pro_perms.isdisjoint(PLATFORM_SUPPORT_PERMISSIONS)

    assert Permission.PROJECTS_READ in ROLE_PERMISSIONS["artist"]
    assert Permission.PROJECTS_WORK in ROLE_PERMISSIONS["artist"]
    assert Permission.PROJECTS_MANAGE not in ROLE_PERMISSIONS["artist"]

    assert Permission.PROJECTS_READ in ROLE_PERMISSIONS["front_desk"]
    assert Permission.PROJECTS_WORK in ROLE_PERMISSIONS["front_desk"]
    assert Permission.PROJECTS_MANAGE not in ROLE_PERMISSIONS["front_desk"]

    assert pro_perms <= ROLE_PERMISSIONS["manager"]
    assert pro_perms <= ROLE_PERMISSIONS["owner"]


def test_matter_input_validation_rules() -> None:
    valid = MatterInput(
        schema_version=1,
        expected_revision=0,
        location_id=uuid7(),
        code="MAT-2026-001",
        title="Acme Corp M&A Diligence",
        description="Confidential diligence matter.",
        kind="legal_case",
        status="intake",
        access_mode="restricted",
        client_counterparty_id=uuid7(),
        currency="USD",
        budget_minor=500_000,
        opened_on=date(2026, 11, 21),
        due_on=date(2026, 12, 31),
    )
    assert valid.code == "MAT-2026-001"

    with pytest.raises(ValidationError):
        MatterInput(
            schema_version=1,
            expected_revision=0,
            location_id=uuid7(),
            code="MAT-1",
            title="Bad date range",
            kind="project",
            status="active",
            client_counterparty_id=uuid7(),
            currency="USD",
            opened_on=date(2026, 11, 21),
            due_on=date(2026, 11, 20),
        )

    with pytest.raises(ValidationError):
        MatterInput(
            schema_version=1,
            expected_revision=0,
            location_id=uuid7(),
            code="BAD\nCODE",
            title="Ctrl char",
            kind="project",
            status="active",
            client_counterparty_id=uuid7(),
            currency="USD",
            opened_on=date(2026, 11, 21),
        )

    with pytest.raises(ValidationError):
        MatterInput(
            schema_version=1,
            expected_revision=0,
            location_id=uuid7(),
            code="MAT-2",
            title="Lowercase currency",
            kind="project",
            status="active",
            client_counterparty_id=uuid7(),
            currency="usd",
            opened_on=date(2026, 11, 21),
        )


def test_conflict_check_and_member_inputs_are_strict() -> None:
    chk = ConflictCheckInput(
        schema_version=1,
        checked_parties="Acme Corp vs Beta Holdings",
        decision="clear",
        rationale="No adverse representation found in counterparty index.",
    )
    assert chk.decision == "clear"

    mem = MatterMemberInput(schema_version=1, user_id=uuid7(), matter_role="contributor")
    assert mem.matter_role == "contributor"

    with pytest.raises(ValidationError):
        ConflictCheckInput(
            schema_version=1,
            checked_parties="   ",
            decision="clear",
            rationale="Empty parties rejected",
        )
