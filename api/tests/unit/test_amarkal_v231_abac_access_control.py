"""Unit tests for AMARKAL v2.31.0 Matrix RBAC / ABAC Policy Engine & Field Masking."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest

import gorgona_booking
from gorgona_booking.api.abac_policies import CreateAbacPolicyRequest
from gorgona_booking.api.counterparties import _apply_counterparty_abac_masking
from gorgona_booking.auth.abac import (
    ABAC_PRESET_TEMPLATES,
    AbacPolicySpec,
    apply_abac_field_masking,
    evaluate_abac_access,
    mask_field_value,
    merge_abac_policies,
)
from gorgona_booking.auth.permissions import PERMISSIONS_VERSION, Permission
from gorgona_booking.business.counterparty_contracts import ContactView, CounterpartyView
from gorgona_booking.tenancy.authorization import TenantAccess


def _regional_manager_spec() -> AbacPolicySpec:
    return AbacPolicySpec(
        policy_code="regional-sales-manager-pii-guard",
        display_name="Regional Sales Manager",
        base_role="manager",
        denied_permissions=frozenset({"finance.close", "settings.manage"}),
        allowed_regions=frozenset({"Midwest", "IL", "OH"}),
        masked_fields=frozenset({"phone", "tax_id"}),
        write_window_enabled=True,
        write_window_timezone="America/Chicago",
        write_window_start_minute=9 * 60,  # 09:00
        write_window_end_minute=18 * 60,  # 18:00
        write_window_days=frozenset({1, 2, 3, 4, 5}),
        write_window_permissions=frozenset({"counterparties.manage", "documents.manage"}),
        max_financial_amount_cents=5_000_000,  # $50,000
    )


def test_permissions_version_invariant_and_presets_valid() -> None:
    assert PERMISSIONS_VERSION == 25
    assert len(ABAC_PRESET_TEMPLATES) == 4
    codes = set()
    for tpl in ABAC_PRESET_TEMPLATES:
        parsed = CreateAbacPolicyRequest.model_validate(tpl)
        codes.add(parsed.policy_code)
    assert len(codes) == 4


def test_time_window_enforces_local_business_hours_and_weekdays() -> None:
    overlay = merge_abac_policies([_regional_manager_spec()])
    assert overlay is not None

    # Wednesday 2026-11-25 14:30 CST (UTC-6 -> 20:30 UTC): inside 09:00-18:00
    allowed_dt = datetime(2026, 11, 25, 20, 30, tzinfo=UTC)
    ok = evaluate_abac_access(
        overlay,
        Permission.COUNTERPARTIES_MANAGE,
        at_utc=allowed_dt,
        record_region="Midwest",
        amount_cents=4_200_000,
    )
    assert ok.allowed is True
    assert ok.blocked_by is None
    assert ok.masked_fields == ("phone", "tax_id")

    # Wednesday 2026-11-25 18:05 CST (UTC-6 -> 2026-11-26 00:05 UTC): after 18:00 -> blocked
    after_hours = datetime(2026, 11, 26, 0, 5, tzinfo=UTC)
    denied = evaluate_abac_access(
        overlay,
        Permission.COUNTERPARTIES_MANAGE,
        at_utc=after_hours,
        record_region="Midwest",
    )
    assert denied.allowed is False
    assert denied.blocked_by == "time_window"
    assert "09:00-18:00 America/Chicago" in denied.reason

    # Read permission stays allowed after 18:00
    read_after_hours = evaluate_abac_access(
        overlay,
        Permission.COUNTERPARTIES_READ,
        at_utc=after_hours,
        record_region="IL",
    )
    assert read_after_hours.allowed is True

    # Saturday 2026-11-28 12:00 CST (18:00 UTC): weekend -> blocked
    weekend_dt = datetime(2026, 11, 28, 18, 0, tzinfo=UTC)
    denied_weekend = evaluate_abac_access(
        overlay,
        Permission.COUNTERPARTIES_MANAGE,
        at_utc=weekend_dt,
        record_region="OH",
    )
    assert denied_weekend.allowed is False
    assert denied_weekend.blocked_by == "time_window"


def test_region_scope_denied_permission_and_financial_limit() -> None:
    overlay = merge_abac_policies([_regional_manager_spec()])
    assert overlay is not None
    business_hour = datetime(2026, 11, 25, 18, 0, tzinfo=UTC)  # 12:00 CST

    # Denied permission
    res_perm = evaluate_abac_access(overlay, Permission.FINANCE_CLOSE, at_utc=business_hour)
    assert res_perm.allowed is False
    assert res_perm.blocked_by == "denied_permission"

    # Out-of-region counterparty
    res_region = evaluate_abac_access(
        overlay,
        Permission.COUNTERPARTIES_READ,
        at_utc=business_hour,
        record_region="California",
    )
    assert res_region.allowed is False
    assert res_region.blocked_by == "region_scope"

    # Over $50,000 financial cap
    res_amt = evaluate_abac_access(
        overlay,
        Permission.COUNTERPARTIES_MANAGE,
        at_utc=business_hour,
        record_region="Midwest",
        amount_cents=6_500_000,
    )
    assert res_amt.allowed is False
    assert res_amt.blocked_by == "financial_limit"


def test_least_privilege_policy_merge_and_disjoint_regions_fail_closed() -> None:
    p1 = _regional_manager_spec()
    p2 = AbacPolicySpec(
        policy_code="northeast-cap-10k",
        display_name="Northeast $10k",
        base_role="manager",
        denied_permissions=frozenset({"inventory.manage"}),
        allowed_regions=frozenset({"NY", "NJ"}),
        masked_fields=frozenset({"email"}),
        write_window_enabled=False,
        write_window_timezone="America/New_York",
        write_window_start_minute=540,
        write_window_end_minute=1080,
        write_window_days=frozenset({1, 2, 3, 4, 5}),
        write_window_permissions=frozenset(),
        max_financial_amount_cents=1_000_000,
    )
    merged = merge_abac_policies([p1, p2])
    assert merged is not None
    assert merged.region_conflict is True
    assert merged.max_financial_amount_cents == 1_000_000
    assert {"phone", "tax_id", "email"}.issubset(merged.masked_fields)
    assert "inventory.manage" in merged.denied_permissions
    assert "finance.close" in merged.denied_permissions

    decision = evaluate_abac_access(merged, Permission.COUNTERPARTIES_READ)
    assert decision.allowed is False
    assert decision.blocked_by == "region_conflict"


def test_pii_field_masking_and_counterparty_view_redaction() -> None:
    assert mask_field_value("phone", "+1 (312) 555-4821") == "***-***-4821"
    assert mask_field_value("email", "cfo@midweststeel.us") == "c***@midweststeel.us"
    assert mask_field_value("tax_id", "36-4829104") == "**-***9104"
    assert mask_field_value("bank_account", "US0988124321") == "••••4321"
    assert mask_field_value("compensation", 125000) == "[REDACTED]"

    sample = {
        "client": "Midwest Steel",
        "phone": "+1 312-555-4821",
        "contact": {"contact_email": "ops@midwest.us", "mobile": "3125559988"},
        "tax_id": "36-4829104",
        "contract_value_cents": 4_200_000,
    }
    masked = apply_abac_field_masking(sample, ["phone", "tax_id", "contract_value"])
    assert masked["phone"] == "***-***-4821"
    assert masked["tax_id"] == "**-***9104"
    assert masked["contract_value_cents"] == "[REDACTED]"
    assert masked["contact"]["mobile"] == "***-***-9988"
    assert masked["contact"]["contact_email"] == "ops@midwest.us"

    overlay = merge_abac_policies([_regional_manager_spec()])
    fake_access = cast(TenantAccess, SimpleNamespace(abac=overlay))
    view = CounterpartyView(
        business_id=uuid4(),
        counterparty_id=uuid4(),
        kind="organization",
        revision=1,
        display_name="Midwest Steel LLC",
        legal_name="Midwest Steel Fabricators LLC",
        tax_id="36-4829104",
        registration_number="IL-90012",
        email="cfo@midweststeel.us",
        phone="+1 (312) 555-4821",
        roles=("customer",),
        state="active",
        merged_into=None,
        contacts=(
            ContactView(
                position=1,
                name="Jane Doe",
                job_title="VP Procurement",
                email="jane@midweststeel.us",
                phone="+1 (312) 555-7744",
            ),
        ),
        created_at=datetime.now(UTC),
    )
    redacted = _apply_counterparty_abac_masking(view, fake_access)
    assert redacted.phone == "***-***-4821"
    assert redacted.tax_id == "**-***9104"
    assert redacted.email == "cfo@midweststeel.us"
    assert redacted.contacts[0].phone == "***-***-7744"
    assert redacted.contacts[0].email == "jane@midweststeel.us"


def test_create_abac_policy_request_validation_rejects_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="Unsupported IANA timezone"):
        CreateAbacPolicyRequest(
            policy_code="bad-tz-policy",
            display_name="Bad TZ",
            write_window_timezone="Mars/Olympus_Mons",
        )

    with pytest.raises(ValueError, match="Unknown permissions"):
        CreateAbacPolicyRequest(
            policy_code="bad-perm-policy",
            display_name="Bad Perm",
            denied_permissions=["root.drop_table"],
        )

    with pytest.raises(ValueError, match="Unsupported masked fields"):
        CreateAbacPolicyRequest(
            policy_code="bad-mask-policy",
            display_name="Bad Mask",
            masked_fields=["favorite_color"],
        )


def test_migration_0168_enforces_force_rls_without_security_definer() -> None:
    mig_path = (
        Path(gorgona_booking.__file__).parent
        / "db"
        / "migrations"
        / "0168_abac_matrix_access_control.sql"
    )
    sql = mig_path.read_text(encoding="utf-8")
    non_comment_sql = "\n".join(
        line for line in sql.splitlines() if not line.strip().startswith("--")
    )
    assert "ENABLE ROW LEVEL SECURITY" in non_comment_sql
    assert "FORCE ROW LEVEL SECURITY" in non_comment_sql
    assert "gba.abac_policies" in non_comment_sql
    assert "gba.abac_user_assignments" in non_comment_sql
    assert "SECURITY DEFINER" not in non_comment_sql.upper()
