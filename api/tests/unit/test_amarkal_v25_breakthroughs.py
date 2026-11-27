"""Unit tests for AMARKAL Platform v2.5 breakthroughs and hardening fixes."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from gorgona_booking.ai_assistant.service import (
    CopilotContext,
    CopilotInsight,
    synthesize_owner_copilot,
)
from gorgona_booking.api.self_service import (
    _BLUEPRINT_HITS,
    _BLUEPRINT_MAX_PER_WINDOW,
    _enforce_blueprint_rate_limit,
)

pytestmark = pytest.mark.anyio


def _fake_request(env: str, ip: str) -> object:
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(settings=SimpleNamespace(environment=env))),
        headers={"x-forwarded-for": ip},
        client=SimpleNamespace(host=ip),
    )


def test_ai_blueprint_rate_limit_enforced_in_production_and_bypassed_in_test() -> None:
    _BLUEPRINT_HITS.clear()
    req_test = _fake_request("test", "203.0.113.10")
    for _ in range(_BLUEPRINT_MAX_PER_WINDOW + 5):
        _enforce_blueprint_rate_limit(req_test)  # type: ignore[arg-type]

    req_prod = _fake_request("production", "203.0.113.42")
    for _ in range(_BLUEPRINT_MAX_PER_WINDOW):
        _enforce_blueprint_rate_limit(req_prod)  # type: ignore[arg-type]
    with pytest.raises(HTTPException) as exc_info:
        _enforce_blueprint_rate_limit(req_prod)  # type: ignore[arg-type]
    assert exc_info.value.status_code == 429
    _BLUEPRINT_HITS.clear()


async def test_synthesize_owner_copilot_runs_outside_db_with_grounded_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GBA_CF_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("GBA_CF_API_TOKEN", raising=False)
    monkeypatch.delenv("GBA_GEMINI_API_KEY", raising=False)
    ctx = CopilotContext(
        business_name="Austin Smile Care",
        metrics={
            "upcoming_7d_confirmed_bookings": 4,
            "upcoming_7d_booked_value_cents": 68000,
            "stripe_30d_paid_cents": 125000,
            "waiting_waitlist_count": 2,
            "waitlist_recoverable_value_cents": 32000,
            "bookable_services_count": 5,
            "active_staff_count": 3,
        },
        insights=[
            CopilotInsight(
                priority="high",
                category="revenue_recovery",
                title="Recover $320.00 from 2 waitlisted client(s)",
                detail="Notify waitlisted clients.",
                action_path="/settings/",
            )
        ],
    )
    res_en = await synthesize_owner_copilot(ctx, question="What is our top priority?")
    assert res_en.engine == "grounded"
    assert "$1,250.00" in res_en.reply
    assert "$680.00" in res_en.reply

    res_ru = await synthesize_owner_copilot(ctx, question="Какой главный приоритет?")
    assert res_ru.engine == "grounded"
    assert "Austin Smile Care" in res_ru.reply
    assert "$1,250.00" in res_ru.reply
