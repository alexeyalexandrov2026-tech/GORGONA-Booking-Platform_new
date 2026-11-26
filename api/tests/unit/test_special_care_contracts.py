"""Unit contract tests for SPECIAL-02 (0146): clinical_care module & consent validation."""

from datetime import date
from uuid import uuid7

import pytest
from pydantic import ValidationError

from gorgona_booking.auth.permissions import DELEGABLE_PERMISSIONS, PERMISSIONS_VERSION, Permission
from gorgona_booking.business import modules
from gorgona_booking.business.readiness_registry import Readiness
from gorgona_booking.business.special_care import CareEncounterInput, CareSubjectInput


def test_clinical_care_module_and_care_permissions_registered() -> None:
    assert modules.MODULE_REGISTRY_VERSION == 17
    mod = modules.MODULES_BY_ID["clinical_care"]
    assert mod.readiness == Readiness.IMPLEMENTED
    assert mod.enableable is False
    assert set(mod.depends_on) == {"counterparties"}
    assert PERMISSIONS_VERSION == 25
    for perm in (Permission.CARE_READ, Permission.CARE_WORK, Permission.CARE_MANAGE):
        assert perm not in DELEGABLE_PERMISSIONS


def test_care_contracts_validate_subject_and_encounter_inputs() -> None:
    subj = CareSubjectInput(
        expected_revision=0,
        location_id=uuid7(),
        guardian_counterparty_id=uuid7(),
        subject_kind="animal_patient",
        code="pet_rex_01",
        display_name="Rex",
        species_or_profile="Canine / Shepherd",
    )
    assert subj.code == "PET_REX_01"

    with pytest.raises(ValidationError):
        CareEncounterInput(
            location_id=uuid7(),
            subject_id=uuid7(),
            consent_id=uuid7(),
            encounter_date=date(2026, 11, 5),
            summary="Checkup",
            clinical_notes="   ",
        )
