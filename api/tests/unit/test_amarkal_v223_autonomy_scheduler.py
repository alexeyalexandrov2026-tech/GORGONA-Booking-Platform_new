"""Unit tests for AMARKAL v2.23.0 autonomous weekly predictive brief scheduler."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from gorgona_booking.ai_assistant.autonomy import AutonomyPolicyView, default_autonomy_policy
from gorgona_booking.ai_assistant.scheduler import (
    is_weekly_brief_due,
    parse_target_tenant_ids,
    utc_weekday_name,
)


def _policy(
    *,
    auto_send: bool = True,
    day: str = "monday",
    email: str | None = "owner@amarkal.us",
) -> AutonomyPolicyView:
    base = default_autonomy_policy(uuid4())
    return AutonomyPolicyView(
        tenant_id=base.tenant_id,
        autonomy_level="safe_autopilot",
        auto_confirm_open_bookings=False,
        auto_send_invoice_reminders=True,
        auto_offer_waitlist_slots=False,
        auto_send_weekly_brief=auto_send,
        weekly_brief_day=day,  # type: ignore[arg-type]
        weekly_brief_email=email,
        require_human_approval_over_cents=0,
        updated_at=None,
    )


def test_weekly_brief_due_matches_weekday_and_enforces_six_day_idempotency() -> None:
    monday = datetime(2026, 11, 30, 14, 0, tzinfo=UTC)
    assert utc_weekday_name(monday) == "monday"

    pol = _policy(auto_send=True, day="monday")
    due_first, reason_first = is_weekly_brief_due(pol, last_report_at=None, now_utc=monday)
    assert due_first is True
    assert "monday" in reason_first

    # Already sent 2 days ago -> MUST NOT duplicate
    due_recent, reason_recent = is_weekly_brief_due(
        pol, last_report_at=monday - timedelta(days=2), now_utc=monday
    )
    assert due_recent is False
    assert "6 days" in reason_recent

    # Sent 7 days ago -> due again!
    due_again, _ = is_weekly_brief_due(
        pol, last_report_at=monday - timedelta(days=7), now_utc=monday
    )
    assert due_again is True


def test_weekly_brief_respects_disabled_toggle_and_wrong_weekday() -> None:
    tuesday = datetime(2026, 12, 1, 10, 0, tzinfo=UTC)
    assert utc_weekday_name(tuesday) == "tuesday"

    due_wrong_day, reason_day = is_weekly_brief_due(
        _policy(auto_send=True, day="monday"), last_report_at=None, now_utc=tuesday
    )
    assert due_wrong_day is False
    assert "monday" in reason_day

    due_disabled, reason_off = is_weekly_brief_due(
        _policy(auto_send=False, day="tuesday"), last_report_at=None, now_utc=tuesday
    )
    assert due_disabled is False
    assert "disabled" in reason_off


def test_parse_target_tenant_ids_deduplicates_cli_and_env() -> None:
    first = uuid4()
    second = uuid4()
    parsed = parse_target_tenant_ids([str(first)], f" {first} , {second} ")
    assert parsed == [first, second]
