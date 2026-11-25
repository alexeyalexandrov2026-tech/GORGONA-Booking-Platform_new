"""Unit tests for AI Assistant multilingual intent parsing and growth notification templates."""

from __future__ import annotations

from datetime import date

from gorgona_booking.ai_assistant.service import parse_assistant_intent
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
