"""Unit tests for AMARKAL v2.19.0 Omnichannel Unified Client Inbox & Virtual PBX."""

from __future__ import annotations

import asyncio

from gorgona_booking.business.omnichannel_inbox import (
    DEFAULT_BUILTIN_CHANNELS,
    build_message_preview,
    dispatch_built_in_outbound,
    generate_inbox_webhook_token,
    hash_inbox_webhook_token,
    normalize_phone,
)


def test_inbox_webhook_tokens_and_phone_normalization() -> None:
    raw, prefix, digest = generate_inbox_webhook_token()
    assert raw.startswith("amk_inb_")
    assert raw.startswith(prefix)
    assert len(digest) == 64
    assert hash_inbox_webhook_token(raw) == digest

    assert normalize_phone("(312) 555-0190") == "+13125550190"
    assert normalize_phone("+1 312-555-0190") == "+13125550190"
    assert normalize_phone("   ") is None

    long_msg = "Hello   world\n\n" + ("A" * 220)
    preview = build_message_preview(long_msg, max_len=40)
    assert len(preview) <= 40
    assert preview.startswith("Hello world ")
    assert preview.endswith("…")

    types = [c[0] for c in DEFAULT_BUILTIN_CHANNELS]
    assert "email" in types
    assert "voice_pbx" in types
    assert "web_chat" in types


def test_built_in_outbound_dispatch_email_and_internal_note() -> None:
    st_note, msg_id_note, meta_note = asyncio.run(
        dispatch_built_in_outbound(
            channel_type="internal_note",
            recipient="",
            subject="",
            body="Confirmed rate card with ops director.",
            idempotency_key="note-1",
        )
    )
    assert st_note == "logged"
    assert msg_id_note is None
    assert meta_note["transport"] == "internal_note"

    st_email, msg_id_email, _ = asyncio.run(
        dispatch_built_in_outbound(
            channel_type="email",
            recipient="client@example.com",
            subject="Freight Quote Q-2026-01",
            body="Attached is your commercial quote.",
            idempotency_key="email-1",
        )
    )
    assert st_email == "sent"
    assert msg_id_email is not None
    assert len(msg_id_email) > 4
