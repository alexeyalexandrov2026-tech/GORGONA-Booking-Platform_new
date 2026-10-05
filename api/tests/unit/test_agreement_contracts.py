"""Contract commands reject ambiguous input; signing is only attested."""

from datetime import UTC, datetime, timedelta
from uuid import uuid7

import pytest
from pydantic import ValidationError

from gorgona_booking.business.agreement_contracts import (
    AgreeInput,
    AgreementDraftInput,
    AgreementRevision,
    AgreementSummary,
    AgreementView,
    TerminateInput,
)
from gorgona_booking.business.agreements import latest_calendar_day


def body(**changes: object) -> dict[str, object]:
    return {
        "schema_version": 1,
        "expected_revision": 0,
        "counterparty_id": str(uuid7()),
        "title": "FAKE Contract",
        **changes,
    }


@pytest.mark.parametrize(
    "invalid",
    [
        {"schema_version": 2},
        {"state": "agreed"},
        {"signed_on": "2026-01-01"},
        {"expected_revision": True},
        {"expected_revision": -1},
        {"title": " "},
        {"title": "x" * 201},
        {"number": "FAKE\n1"},
        {"number": "x" * 65},
        {"title": "FAKE" + chr(0x85) + "line"},
        {"number": "FAKE" + chr(0x9F)},
        {"summary": "FAKE" + chr(0x80)},
        {"summary": "FAKE\x00"},
        {"summary": "x" * 2001},
        {"effective_from": "2026-02-01", "effective_until": "2026-01-31"},
        {"document": {"document_id": str(uuid7())}},
        {"document": {"document_id": str(uuid7()), "revision": 0}},
        {"counterparty_id": None},
    ],
)
def test_drafts_refuse_ambiguous_values(invalid: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        AgreementDraftInput.model_validate(body(**invalid))


def test_drafts_keep_multiline_summaries_and_trim_titles() -> None:
    parsed = AgreementDraftInput.model_validate(
        body(title="  FAKE Contract ", summary=" FAKE line 1\n\tFAKE line 2 ", number=" A-1 ")
    )
    assert (parsed.title, parsed.summary, parsed.number) == (
        "FAKE Contract",
        "FAKE line 1\n\tFAKE line 2",
        "A-1",
    )


def test_agree_and_terminate_need_revisions_and_dates() -> None:
    with pytest.raises(ValidationError):
        AgreeInput.model_validate({"schema_version": 1, "expected_revision": 0, "signed_on": "x"})
    assert (
        AgreeInput.model_validate(
            {"schema_version": 1, "expected_revision": 1, "signed_on": "2026-10-01"}
        ).attestation
        is None
    )
    with pytest.raises(ValidationError):
        TerminateInput.model_validate({"schema_version": 1, "expected_revision": 1})


def test_terminations_may_take_effect_later_and_views_name_the_version_in_force() -> None:
    later = (datetime.now(UTC) + timedelta(days=400)).date().isoformat()
    parsed = TerminateInput.model_validate(
        {"schema_version": 1, "expected_revision": 3, "terminated_on": later}
    )
    assert parsed.terminated_on.isoformat() == later
    for field in ("in_force_revision", "terminates_revision"):
        assert AgreementView.model_fields[field].is_required()
    assert AgreementRevision.model_fields["abandoned"].is_required()
    assert AgreementSummary.model_fields["in_force"].is_required()


def test_views_only_name_the_outside_signing_attestation() -> None:
    assert "signed_outside_platform" in str(AgreementView.model_json_schema())
    assert "signature" not in AgreementView.model_fields


def test_latest_calendar_day_allows_every_time_zone_but_not_tomorrow_everywhere() -> None:
    utc_today = datetime.now(UTC).date()
    assert utc_today <= latest_calendar_day() <= utc_today + timedelta(days=1)
