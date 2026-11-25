"""Unit tests for AI Assistant multilingual intent parsing and growth notification templates."""

from __future__ import annotations

import http.client
import json
from datetime import date
from typing import Any

import pytest

from gorgona_booking.ai_assistant.service import (
    _call_cloudflare_sync,
    _strip_reasoning_tags,
    _synthesize_reply_sync,
    parse_assistant_intent,
)
from gorgona_booking.notifications.service import TEMPLATES, render_template


def test_parse_assistant_intent_english_tomorrow_afternoon_and_budget() -> None:
    intent = parse_assistant_intent(
        "Anything open tomorrow afternoon for a haircut under $65?",
        today=date(2026, 12, 1),
        max_day=date(2027, 1, 30),
    )
    assert intent["target_days"] == [date(2026, 12, 2)]
    assert intent["window"] == "afternoon"
    assert intent["max_price_cents"] == 6500
    assert intent["language"] == "en"
    assert "haircut" in intent["tokens"]


def test_parse_assistant_intent_russian_and_spanish() -> None:
    ru = parse_assistant_intent(
        "Есть свободное время завтра утром до 50?",
        today=date(2026, 12, 1),
        max_day=date(2027, 1, 30),
    )
    assert ru["target_days"] == [date(2026, 12, 2)]
    assert ru["window"] == "morning"
    assert ru["max_price_cents"] == 5000
    assert ru["language"] == "ru"

    es = parse_assistant_intent(
        "Hola, cita mañana tarde barato",
        today=date(2026, 12, 1),
        max_day=date(2027, 1, 30),
    )
    assert es["target_days"] == [date(2026, 12, 2)]
    assert es["window"] == "afternoon"
    assert es["sort_by"] == "price"
    assert es["language"] == "es"


def test_growth_notification_templates_render_cleanly() -> None:
    for code in (
        "waitlist_slot_available",
        "review_request",
        "rebooking_reminder",
        "gift_card_issued",
    ):
        assert code in TEMPLATES
        subject, body = render_template(
            code,
            {
                "business_name": "FAKE Studio",
                "service_name": "Signature Cut",
                "starts_at": "2026-12-05 14:00",
                "action_url": "https://example.test/book/",
                "amount": "$100.00",
                "reference": "GC-1001",
            },
        )
        assert "FAKE Studio" in subject or "FAKE Studio" in body
        assert len(body) > 10


def test_strip_reasoning_tags_cleans_think_blocks() -> None:
    raw = "<think>internal chain of thought</think>\nAvailable tomorrow at 2:00 PM."
    assert _strip_reasoning_tags(raw) == "Available tomorrow at 2:00 PM."


def test_cloudflare_workers_ai_synthesis_and_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class FakeResp:
        def __init__(self, status: int, payload: bytes) -> None:
            self.status = status
            self._payload = payload

        def read(self) -> bytes:
            return self._payload

    class FakeConn:
        def __init__(self, host: str, port: int, timeout: float = 15.0) -> None:
            captured["host"] = host
            captured["port"] = port

        def request(
            self,
            method: str,
            path: str,
            body: bytes | None = None,
            headers: dict[str, str] | None = None,
        ) -> None:
            captured["method"] = method
            captured["path"] = path
            captured["body"] = json.loads((body or b"{}").decode("utf-8"))
            captured["headers"] = headers or {}

        def getresponse(self) -> FakeResp:
            payload = json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": "Open slot tomorrow at 10:00 AM for USD 65.00.",
                            }
                        }
                    ]
                }
            ).encode("utf-8")
            return FakeResp(200, payload)

        def close(self) -> None:
            captured["closed"] = True

    monkeypatch.setenv("GBA_CF_ACCOUNT_ID", "acc-test-123")
    monkeypatch.setenv("GBA_CF_API_TOKEN", "tok-test-xyz")
    monkeypatch.setenv("GBA_CF_MODEL", "@cf/meta/llama-3.3-70b-instruct-fp8-fast")
    monkeypatch.delenv("GBA_GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GBA_AI_PROVIDER", "auto")
    monkeypatch.setattr(http.client, "HTTPSConnection", FakeConn)

    res = _synthesize_reply_sync("System prompt", {"customer_message": "Tomorrow?"})
    assert res == ("cloudflare", "Open slot tomorrow at 10:00 AM for USD 65.00.")
    assert captured["host"] == "api.cloudflare.com"
    assert captured["path"] == "/client/v4/accounts/acc-test-123/ai/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer tok-test-xyz"
    assert captured["body"]["model"] == "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
    assert captured["closed"] is True

    # Explicit grounded override bypasses remote synthesis cleanly
    monkeypatch.setenv("GBA_AI_PROVIDER", "grounded")
    assert _synthesize_reply_sync("System prompt", {"customer_message": "Tomorrow?"}) is None

    # Unconfigured credentials return None cleanly
    monkeypatch.delenv("GBA_CF_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("GBA_CF_API_TOKEN", raising=False)
    assert _call_cloudflare_sync("System prompt", {"customer_message": "Tomorrow?"}) is None
