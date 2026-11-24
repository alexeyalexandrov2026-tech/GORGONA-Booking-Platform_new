"""Unit contract checks for PROPERTY-01 5a maintenance inputs."""

from uuid import uuid7

import pytest
from pydantic import TypeAdapter, ValidationError

from gorgona_booking.business.property_maintenance import (
    ApproveMaintenanceInput,
    AssignMaintenanceInput,
    CancelMaintenanceInput,
    CompleteMaintenanceInput,
    ContractorCompanyInput,
    ContractorUpdateInput,
    MaintenanceEventInput,
    MaintenanceObligationInput,
    MaintenanceRequestInput,
)


def _req(**changes: object) -> dict[str, object]:
    return {
        "schema_version": 1,
        "object_id": str(uuid7()),
        "lease_id": None,
        "category": "plumbing",
        "priority": "urgent",
        "title": "FAKE Pipe leak",
        "description": "FAKE Active drip under sink",
        **changes,
    }


@pytest.mark.parametrize(
    "bad",
    [
        {"schema_version": 2},
        {"extra": "field"},
        {"category": "roofing"},
        {"priority": "critical"},
        {"title": "   "},
        {"title": "FAKE\nnewline"},
        {"title": "FAKE\x00nul"},
        {"title": "x" * 201},
        {"description": "   "},
        {"description": "FAKE\x00nul"},
        {"description": "x" * 4001},
    ],
)
def test_maintenance_request_input_rejects_invalid_values(bad: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        MaintenanceRequestInput.model_validate(_req(**bad))


def test_maintenance_request_input_trims_and_allows_multiline_description() -> None:
    parsed = MaintenanceRequestInput.model_validate(
        _req(title="  FAKE Leak  ", description="  Line 1\nLine 2  ")
    )
    assert parsed.title == "FAKE Leak"
    assert parsed.description == "Line 1\nLine 2"


def test_maintenance_event_union_validates_each_action() -> None:
    adapter: TypeAdapter[object] = TypeAdapter(MaintenanceEventInput)
    assert isinstance(
        adapter.validate_python(
            {
                "schema_version": 1,
                "action": "approve",
                "expected_revision": 1,
                "approved_limit_minor": 10000,
                "currency": "USD",
            }
        ),
        ApproveMaintenanceInput,
    )
    assert isinstance(
        adapter.validate_python(
            {
                "schema_version": 1,
                "action": "assign",
                "expected_revision": 2,
                "contractor_id": str(uuid7()),
            }
        ),
        AssignMaintenanceInput,
    )
    assert isinstance(
        adapter.validate_python(
            {"schema_version": 1, "action": "complete", "expected_revision": 3}
        ),
        CompleteMaintenanceInput,
    )
    assert isinstance(
        adapter.validate_python({"schema_version": 1, "action": "cancel", "expected_revision": 1}),
        CancelMaintenanceInput,
    )
    for bad in (
        {
            "schema_version": 1,
            "action": "approve",
            "expected_revision": 1,
            "approved_limit_minor": 0,
            "currency": "USD",
        },
        {
            "schema_version": 1,
            "action": "approve",
            "expected_revision": 1,
            "approved_limit_minor": 100,
            "currency": "usd",
        },
        {
            "schema_version": 1,
            "action": "approve",
            "expected_revision": True,
            "approved_limit_minor": 100,
            "currency": "USD",
        },
        {"schema_version": 1, "action": "assign", "expected_revision": 1},
        {
            "schema_version": 1,
            "action": "complete",
            "expected_revision": 1,
            "contractor_id": str(uuid7()),
        },
        {"schema_version": 1, "action": "reopen", "expected_revision": 1},
    ):
        with pytest.raises(ValidationError):
            adapter.validate_python(bad)


def test_maintenance_obligation_input_validates_fields() -> None:
    parsed = MaintenanceObligationInput.model_validate(
        {
            "schema_version": 1,
            "book_id": str(uuid7()),
            "invoice_document_id": str(uuid7()),
            "note": "  FAKE invoice note  ",
        }
    )
    assert parsed.note == "FAKE invoice note"
    with pytest.raises(ValidationError):
        MaintenanceObligationInput.model_validate(
            {
                "schema_version": 1,
                "book_id": str(uuid7()),
                "invoice_document_id": str(uuid7()),
                "note": "   ",
            }
        )


def test_contractor_company_and_update_inputs_validate_strictly() -> None:
    parsed = ContractorCompanyInput.model_validate(
        {"schema_version": 1, "expected_revision": 0, "company_id": str(uuid7())}
    )
    assert parsed.company_id is not None
    assert (
        ContractorCompanyInput.model_validate(
            {"schema_version": 1, "expected_revision": 1, "company_id": None}
        ).company_id
        is None
    )
    with pytest.raises(ValidationError):
        ContractorCompanyInput.model_validate(
            {"schema_version": 1, "expected_revision": -1, "company_id": None}
        )
    upd = ContractorUpdateInput.model_validate(
        {"schema_version": 1, "kind": "in_progress", "note": "  FAKE Working on valve  "}
    )
    assert upd.note == "FAKE Working on valve"
    for bad in (
        {"schema_version": 1, "kind": "completed", "note": "FAKE bad kind"},
        {"schema_version": 1, "kind": "work_done", "note": "   "},
        {"schema_version": 1, "kind": "work_done", "note": "FAKE\x00nul"},
    ):
        with pytest.raises(ValidationError):
            ContractorUpdateInput.model_validate(bad)
