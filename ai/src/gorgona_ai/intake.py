"""Event intake: move evidence messages from a queue into the durable job store.

At-least-once and idempotent: a message is acknowledged only after its job run is
committed; a redelivered message maps to the same idempotency key (SHA-256 of the
body). A body that is not a JSON object is dead-lettered and never retried.
"""

import base64
import hashlib
import http.client
import json
import os
import time
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Protocol

import psycopg

from gorgona_ai.jobs.runtime import enqueue


@dataclass(frozen=True, slots=True)
class Message:
    body: bytes
    handle: Any = None


class MessageSource(Protocol):
    def receive(self, max_messages: int) -> list[Message]: ...
    def complete(self, message: Message) -> None: ...
    def dead_letter(self, message: Message, reason: str) -> None: ...


def pump(
    conn: psycopg.Connection, source: MessageSource, *, batch: int = 50, max_batches: int = 20
) -> dict[str, int]:
    counts = {"queued": 0, "duplicate": 0, "dead_lettered": 0}
    for _ in range(max_batches):
        messages = source.receive(batch)
        if not messages:
            break
        for message in messages:
            try:
                raw = json.loads(message.body)
                if not isinstance(raw, dict):
                    raise ValueError("not an object")
            except ValueError, UnicodeDecodeError:
                source.dead_letter(message, "malformed_json")
                counts["dead_lettered"] += 1
                continue
            key = "ingest:" + hashlib.sha256(message.body).hexdigest()
            with conn.transaction():
                created = enqueue(conn, "ingest", key, payload=raw)
            source.complete(message)
            counts["queued" if created else "duplicate"] += 1
    return counts


class ServiceBusSource:
    """Azure Service Bus queue receiver authenticated with the job's managed identity."""

    def __init__(self, fully_qualified_namespace: str, queue: str, client_id: str | None) -> None:
        from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
        from azure.servicebus import ServiceBusClient

        credential = (
            ManagedIdentityCredential(client_id=client_id)
            if client_id
            else DefaultAzureCredential()
        )
        self._client = ServiceBusClient(fully_qualified_namespace, credential=credential)
        self._receiver = self._client.get_queue_receiver(queue_name=queue, max_wait_time=5)

    def receive(self, max_messages: int) -> list[Message]:
        return [
            Message(b"".join(bytes(part) for part in m.body), m)
            for m in self._receiver.receive_messages(
                max_message_count=max_messages, max_wait_time=5
            )
        ]

    def complete(self, message: Message) -> None:
        self._receiver.complete_message(message.handle)

    def dead_letter(self, message: Message, reason: str) -> None:
        self._receiver.dead_letter_message(message.handle, reason=reason)

    def close(self) -> None:
        self._receiver.close()
        self._client.close()


class PubSubSource:
    """Google Cloud Pub/Sub pull receiver authenticated via GCP Metadata Server or token.

    Uses the standard library HTTPS client so the AI worker image needs no extra cloud SDK
    dependencies. Suitable for Cloud Run Jobs running with a least-privilege service account
    granted ``roles/pubsub.subscriber`` on the target subscription.
    """

    def __init__(
        self,
        project: str,
        subscription: str,
        *,
        access_token: str | None = None,
        api_host: str = "pubsub.googleapis.com",
        timeout: float = 15.0,
    ) -> None:
        self._project = project.strip()
        self._subscription = subscription.strip()
        self._static_token = access_token or os.environ.get("GAI_PUBSUB_ACCESS_TOKEN")
        self._cached_token: str | None = None
        self._cached_token_expires_at: float = 0.0
        self._api_host = api_host
        self._timeout = timeout
        if not self._project or not self._subscription:
            raise ValueError("PubSubSource requires non-empty project and subscription")

    @property
    def _subscription_path(self) -> str:
        return f"/v1/projects/{self._project}/subscriptions/{self._subscription}"

    def _bearer_token(self) -> str:
        if self._static_token:
            return self._static_token
        now = time.monotonic()
        if self._cached_token and now < self._cached_token_expires_at:
            return self._cached_token
        conn = http.client.HTTPConnection("metadata.google.internal", 80, timeout=5.0)
        try:
            conn.request(
                "GET",
                "/computeMetadata/v1/instance/service-accounts/default/token",
                headers={"Metadata-Flavor": "Google"},
            )
            resp = conn.getresponse()
            raw = resp.read()
            if resp.status != 200:
                raise RuntimeError(f"GCP metadata token request failed with HTTP {resp.status}")
            payload = json.loads(raw.decode("utf-8"))
            token = str(payload["access_token"])
            expires_in = float(payload.get("expires_in", 300))
            self._cached_token = token
            self._cached_token_expires_at = now + max(30.0, expires_in - 60.0)
            return token
        finally:
            conn.close()

    def _post_json(self, suffix: str, body: dict[str, Any]) -> dict[str, Any]:
        conn = http.client.HTTPSConnection(self._api_host, 443, timeout=self._timeout)
        try:
            conn.request(
                "POST",
                f"{self._subscription_path}:{suffix}",
                body=json.dumps(body).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {self._bearer_token()}",
                    "Content-Type": "application/json",
                },
            )
            resp = conn.getresponse()
            raw = resp.read()
            if resp.status >= 400:
                raise RuntimeError(f"Pub/Sub {suffix} failed with HTTP {resp.status}")
            if not raw:
                return {}
            parsed = json.loads(raw.decode("utf-8"))
            return parsed if isinstance(parsed, dict) else {}
        finally:
            conn.close()

    def receive(self, max_messages: int) -> list[Message]:
        data = self._post_json("pull", {"maxMessages": max(1, int(max_messages))})
        items = data.get("receivedMessages")
        if not isinstance(items, list):
            return []
        messages: list[Message] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            ack_id = item.get("ackId")
            msg = item.get("message")
            if not isinstance(ack_id, str) or not isinstance(msg, dict):
                continue
            encoded = msg.get("data", "")
            raw_bytes = base64.b64decode(encoded) if isinstance(encoded, str) and encoded else b""
            messages.append(Message(raw_bytes, handle=ack_id))
        return messages

    def complete(self, message: Message) -> None:
        if isinstance(message.handle, str) and message.handle:
            self._post_json("acknowledge", {"ackIds": [message.handle]})

    def dead_letter(self, message: Message, reason: str) -> None:
        # Malformed payloads are never retried; acknowledge to stop poison-pill loops.
        # Subscription-level dead-letter policies handle delivery-failure retries upstream.
        _ = reason
        self.complete(message)

    def close(self) -> None:
        return None


class ListSource:
    """In-memory source with the same semantics (local runs and tests)."""

    def __init__(self, bodies: Iterable[bytes]) -> None:
        self.pending = [Message(b) for b in bodies]
        self.completed: list[Message] = []
        self.dead: list[tuple[Message, str]] = []

    def receive(self, max_messages: int) -> list[Message]:
        taken, self.pending = self.pending[:max_messages], self.pending[max_messages:]
        return taken

    def complete(self, message: Message) -> None:
        self.completed.append(message)

    def dead_letter(self, message: Message, reason: str) -> None:
        self.dead.append((message, reason))
