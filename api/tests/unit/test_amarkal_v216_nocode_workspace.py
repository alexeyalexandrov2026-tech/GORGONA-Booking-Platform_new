"""Unit tests for AMARKAL v2.16.0: No-Code Workspace Studio (Custom Fields, Kanban, WCAG Theme)."""

from __future__ import annotations

import pytest

from gorgona_booking.business.workspace_studio import (
    _validate_lanes,
    validate_custom_field_value,
    validate_wcag_accent_hex,
    wcag_contrast_ratio,
)


def test_wcag_contrast_validation_enforces_aa_ratio() -> None:
    assert wcag_contrast_ratio("#000000", "#FFFFFF") == 21.0
    assert wcag_contrast_ratio("#111111", "#FFFFFF") >= 18.0
    clean, ratio = validate_wcag_accent_hex("#1d4ed8")
    assert clean == "#1D4ED8"
    assert ratio >= 4.5

    # Low-contrast pastel yellow MUST be rejected for white button text
    with pytest.raises(ValueError, match=r"WCAG 2\.1 AA requires at least 4\.5:1"):
        validate_wcag_accent_hex("#facc15")

    with pytest.raises(ValueError, match="6-digit hex code"):
        validate_wcag_accent_hex("not-a-color")


def test_typed_custom_field_value_validation() -> None:
    assert validate_custom_field_value("text", [], "  DOT-998811  ") == "DOT-998811"
    assert validate_custom_field_value("number", [], "42.5") == 42.5
    assert validate_custom_field_value("currency_usd", [], 125.456) == 125.46
    assert validate_custom_field_value("date", [], "2026-12-15") == "2026-12-15"
    assert validate_custom_field_value("boolean", [], "yes") is True
    assert validate_custom_field_value("boolean", [], False) is False
    assert validate_custom_field_value("select", ["Tier 1", "Tier 2"], "Tier 1") == "Tier 1"

    with pytest.raises(ValueError, match="ISO format"):
        validate_custom_field_value("date", [], "12/15/2026")
    with pytest.raises(ValueError, match="must be one of"):
        validate_custom_field_value("select", ["Tier 1", "Tier 2"], "Tier 9")
    with pytest.raises(ValueError, match="cannot be a boolean"):
        validate_custom_field_value("number", [], True)


def test_kanban_lane_validation() -> None:
    default_lanes = _validate_lanes(None)
    assert len(default_lanes) == 4
    assert [x["id"] for x in default_lanes] == ["backlog", "in_progress", "review", "done"]

    with pytest.raises(ValueError, match="between 2 and 8 lanes"):
        _validate_lanes([{"id": "only_one", "title": "Only One", "color_hex": "#111111"}])

    with pytest.raises(ValueError, match="Invalid or duplicate lane id"):
        _validate_lanes(
            [
                {"id": "todo", "title": "To Do", "color_hex": "#111111"},
                {"id": "todo", "title": "Duplicate", "color_hex": "#111111"},
            ]
        )
