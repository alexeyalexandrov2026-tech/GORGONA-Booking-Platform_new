"""Unit tests for Google Cloud Pub/Sub intake adapter."""

from __future__ import annotations

import base64
import json
from typing import Any

import pytest

from gorgona_ai.intake import Message, PubSubSource


class _StubPubSubSource(PubSubSource):
    def __init__(self, payloads: list[dict[str, Any]]) -> None:
        super().__init__("gorgona-platform-gcp", "gorgona-ai-intake-sub", access_token="test-tok")
        self._payloads = list(payloads)
        self.acked: list[str] = []

    def _post_json(self, suffix: str, body: dict[str, Any]) -> dict[str, Any]:
        if suffix == "pull":
            limit = int(body["maxMessages"])
            batch, self._payloads = self._payloads[:limit], self._payloads[limit:]
            return {"receivedMessages": batch}
        if suffix == "acknowledge":
            self.acked.extend(body["ackIds"])
            return {}
        raise AssertionError(f"unexpected suffix: {suffix}")


def test_pubsub_source_decodes_base64_and_acknowledges() -> None:
    sample = json.dumps(
        {"tenant_id": "11111111-1111-1111-1111-111111111111", "kind": "booking"}
    ).encode()
    src = _StubPubSubSource(
        [
            {"ackId": "ack-1", "message": {"data": base64.b64encode(sample).decode()}},
            {"ackId": "ack-2", "message": {"data": base64.b64encode(b"not-json").decode()}},
        ]
    )
    msgs = src.receive(10)
    assert len(msgs) == 2
    assert msgs[0] == Message(sample, handle="ack-1")
    assert msgs[1] == Message(b"not-json", handle="ack-2")
    src.complete(msgs[0])
    src.dead_letter(msgs[1], "malformed_json")
    assert src.acked == ["ack-1", "ack-2"]
    src.close()


def test_pubsub_source_rejects_empty_config() -> None:
    with pytest.raises(ValueError, match="project and subscription"):
        PubSubSource("", "sub", access_token="tok")
