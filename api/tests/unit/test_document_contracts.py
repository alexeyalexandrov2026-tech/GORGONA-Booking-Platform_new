"""Document commands reject ambiguous input; downloads name files safely."""

from uuid import uuid7

import pytest
from pydantic import TypeAdapter, ValidationError

from gorgona_booking.api.documents import _content_disposition
from gorgona_booking.business.document_contracts import (
    DocumentInput,
    DocumentLinkInput,
    FileMetadata,
    UnlinkCounterpartyInput,
)
from gorgona_booking.db import schema_guard
from gorgona_booking.db.financial_guard import FINANCIAL_BOUNDARY, FINANCIAL_PARAMETERS
from gorgona_booking.db.ledger_guard import LEDGER_BOUNDARY, LEDGER_PARAMETERS


def body(**changes: object) -> dict[str, object]:
    return {
        "schema_version": 1,
        "expected_revision": 0,
        "title": "FAKE Agreement",
        "category": "agreement",
        **changes,
    }


@pytest.mark.parametrize(
    "invalid",
    [
        {"schema_version": 2},
        {"extra": "unknown"},
        {"expected_revision": True},
        {"expected_revision": "1"},
        {"expected_revision": -1},
        {"expected_revision": 2_147_483_647},
        {"title": "   "},
        {"title": "FAKE\x00Title"},
        {"title": "FAKE\nTitle"},
        {"title": "x" * 201},
        {"category": "contract"},
        {"archived": "false"},
        {"file_id": "not-a-uuid"},
        {"valid_from": "2026-02-01", "valid_until": "2026-01-31"},
    ],
)
def test_document_input_refuses_ambiguous_values(invalid: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        DocumentInput.model_validate(body(**invalid))


def test_document_input_trims_titles_and_allows_open_or_single_day_validity() -> None:
    parsed = DocumentInput.model_validate(
        body(title="  FAKE Agreement  ", valid_from="2026-01-01", valid_until="2026-01-01")
    )
    assert parsed.title == "FAKE Agreement"
    assert DocumentInput.model_validate(body(valid_until="2026-01-01")).valid_from is None


def test_link_commands_are_discriminated_and_unlink_needs_a_sequence() -> None:
    adapter: TypeAdapter[object] = TypeAdapter(DocumentLinkInput)
    link = {"schema_version": 1, "action": "link", "counterparty_id": str(uuid7())}
    assert type(adapter.validate_python(link)).__name__ == "LinkCounterpartyInput"
    unlink = {**link, "action": "unlink", "expected_sequence": 1}
    assert isinstance(adapter.validate_python(unlink), UnlinkCounterpartyInput)
    for invalid in (
        {**link, "action": "merge"},
        {**link, "expected_sequence": 1},
        {**unlink, "expected_sequence": 0},
        {**unlink, "expected_sequence": True},
        {k: v for k, v in unlink.items() if k != "expected_sequence"},
    ):
        with pytest.raises(ValidationError):
            adapter.validate_python(invalid)


def test_file_metadata_never_claims_a_scan_verdict() -> None:
    fields = {
        "file_id": uuid7(),
        "media_type": "application/pdf",
        "size_bytes": 1,
        "sha256": "0" * 64,
        "file_name": "FAKE.pdf",
        "validator_version": "v1",
        "uploaded_at": "2026-10-05T00:00:00Z",
    }
    assert FileMetadata.model_validate(fields).scan_status == "not_scanned"
    with pytest.raises(ValidationError):
        FileMetadata.model_validate({**fields, "scan_status": "clean"})
    with pytest.raises(ValidationError):
        FileMetadata.model_validate({**fields, "media_type": "text/html"})


@pytest.mark.parametrize(
    ("name", "fallback"),
    [
        ("FAKE Agreement.pdf", "FAKE Agreement.pdf"),
        ("Договор.pdf", "_______.pdf"),
        ('a"b;c\\d.pdf', "a_b_c_d.pdf"),
    ],
)
def test_downloads_are_attachments_with_an_ascii_fallback(name: str, fallback: str) -> None:
    header = _content_disposition(name)
    assert header.startswith(f"attachment; filename=\"{fallback}\"; filename*=UTF-8''")
    assert header.isascii()
    assert not {"\r", "\n"} & set(header)


def test_guard_binds_one_parameter_per_placeholder() -> None:
    placeholders = schema_guard._ACCESS_BOUNDARY.count("%s")
    assert placeholders == 5 * len(schema_guard._DEFINITIONS) + 8 + 6 * 5 + 1
    assert len(schema_guard._DEFINITIONS) == 61
    assert LEDGER_BOUNDARY.count("%s") == len(LEDGER_PARAMETERS)
    assert FINANCIAL_BOUNDARY.count("%s") == len(FINANCIAL_PARAMETERS)
    assert len(schema_guard._OCCUPANCY_TRIGGERS) == 5
    assert len(schema_guard._MODULE_TRIGGERS) == 19
    assert {module for _, _, module in schema_guard._MODULE_TRIGGERS} == {
        "counterparties",
        "documents",
        "finance",
    }
