"""Unit contract checks for PROPERTY-01 6a move-out inputs."""

from uuid import uuid7

import pytest
from pydantic import ValidationError

from gorgona_booking.business.property_move_out import MoveOutInput


def _body(**changes: object) -> dict[str, object]:
    return {
        "schema_version": 1,
        "term_revision": 1,
        "moved_out_on": "2026-06-15",
        "condition_summary": "normal_wear",
        "note": "FAKE Clean handover",
        "report": {"document_id": str(uuid7()), "revision": 1},
        "photos": [{"document_id": str(uuid7()), "revision": 1}],
        **changes,
    }


def test_move_out_input_validates_and_trims() -> None:
    parsed = MoveOutInput.model_validate(
        _body(condition_summary="damage_noted", note="  FAKE Line 1\nLine 2  ")
    )
    assert parsed.condition_summary == "damage_noted"
    assert parsed.note == "FAKE Line 1\nLine 2"
    assert MoveOutInput.model_validate(_body(note=None)).note is None


@pytest.mark.parametrize(
    "bad",
    [
        {"schema_version": 2},
        {"extra": "field"},
        {"term_revision": 0},
        {"term_revision": True},
        {"condition_summary": "destroyed"},
        {"note": "   "},
        {"note": "FAKE\x00nul"},
        {"note": "x" * 2001},
        {"photos": []},
    ],
)
def test_move_out_input_rejects_invalid_values(bad: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        MoveOutInput.model_validate(_body(**bad))


def test_move_out_input_rejects_duplicate_photos() -> None:
    photo = {"document_id": str(uuid7()), "revision": 1}
    with pytest.raises(ValidationError):
        MoveOutInput.model_validate(_body(photos=[photo, photo]))
