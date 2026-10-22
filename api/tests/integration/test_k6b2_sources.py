"""K6b2: the screen shows how each delivery arrived and which operations wait too long.

Owner decisions 2026-10-21 (K6 design defaults, K6b item 5 and the detailed decision 8): every
delivery of an operation's events names its source (a signed webhook or the reconciler's call to the
provider's API), and an operation still `pending` or `not_final` whose latest event is more than 24
hours old shows since when. Synthetic only; no provider account, key, network or money.
"""

import json
import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
import pytest

from gorgona_booking.providers.authenticated_receipts import receive_retrieved_event
from tests.integration import test_provider_payments as shared
from tests.integration import test_provider_receipt_decisions as decided
from tests.integration.test_provider_payments import CREATED, Money, event
from tests.unit import test_stripe_event_boundary as signed

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
manager_b = shared.manager_b
enabled = shared.enabled
invoices = shared.invoices
payments = shared.payments
credits = shared.credits
inbox = shared.inbox
writer_pool = shared.writer_pool
routed = shared.routed
worker_pool = shared.worker_pool
money = shared.money


def recent(kind: str, **changes: Any) -> bytes:
    """An event created a minute ago."""
    value: dict[str, Any] = json.loads(decided.stripe(kind, **changes))
    value["created"] = int(time.time()) - 60
    return signed.body(value)


async def detail(money: Money, operation: UUID) -> dict[str, Any]:
    response = await money.http.get(
        f"{money.root}/provider-operations/{operation}", headers=money.credits.ledger.auth
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def listed(money: Money) -> dict[str, dict[str, Any]]:
    response: httpx.Response = await money.http.get(
        f"{money.root}/provider-operations",
        params={"limit": 100},
        headers=money.credits.ledger.auth,
    )
    assert response.status_code == 200, response.text
    return {item["provider_object_id"]: item for item in response.json()["items"]}


# S-01 -----------------------------------------------------------------------


async def test_each_delivery_names_how_it_arrived(money: Money) -> None:
    raw = event("payment_intent.succeeded")
    await money.observe(raw)
    retrieved = await receive_retrieved_event(
        money.writer, money.routed.ingress_id, json.loads(raw)
    )
    assert retrieved.disposition == "duplicate"
    (shown,) = (await detail(money, await money.operation()))["events"]
    assert sorted(d["source"] for d in shown["deliveries"]) == ["provider_api", "webhook"]
    assert all(d["matches_original"] for d in shown["deliveries"])


# S-02 -----------------------------------------------------------------------


async def test_an_operation_without_a_final_event_for_a_day_shows_since_when(
    money: Money,
) -> None:
    await money.observe(
        # Old and still processing: stalled since its latest event.
        event("payment_intent.processing", status="processing", object_id="pi_FAKEstalled1"),
        # Old but final: never stalled.
        event("payment_intent.succeeded", object_id="pi_FAKEfinal1"),
        # Processing, but its event is a minute old: not stalled yet.
        recent("payment_intent.processing", status="processing", object_id="pi_FAKEfresh1"),
    )
    # Received but never decided (pending), and old.
    await decided.receive_all(
        money.writer, money.routed, event("payment_intent.succeeded", object_id="pi_FAKEwaits1")
    )
    shown = await listed(money)
    assert shown["pi_FAKEstalled1"]["state"] == "not_final"
    assert shown["pi_FAKEstalled1"]["stalled_since"] == datetime.fromtimestamp(
        CREATED, UTC
    ).isoformat().replace("+00:00", "Z")
    assert shown["pi_FAKEfinal1"]["stalled_since"] is None
    assert shown["pi_FAKEfresh1"]["state"] == "not_final"
    assert shown["pi_FAKEfresh1"]["stalled_since"] is None
    assert "pi_FAKEwaits1" not in shown  # no operation until the worker decides an event


async def test_a_pending_operation_waiting_a_day_is_stalled(money: Money) -> None:
    await money.observe(
        event("payment_intent.processing", status="processing", object_id="pi_FAKEpending1")
    )
    # A later event of the same operation, received but not decided: the operation is pending.
    await decided.receive_all(
        money.writer, money.routed, event("payment_intent.succeeded", object_id="pi_FAKEpending1")
    )
    item = (await listed(money))["pi_FAKEpending1"]
    assert item["state"] == "pending"
    assert item["stalled_since"] is not None
    operation = await detail(money, await money.operation("pi_FAKEpending1"))
    assert operation["operation"]["stalled_since"] == item["stalled_since"]
