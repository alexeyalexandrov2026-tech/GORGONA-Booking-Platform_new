"""K6a (K-05): every arrival order of one payment and its refund converges; synthetic only.

The K2a rules treat states as a set of observations, so no order may change a decision, add an
operation or hide a success. Each permutation uses its own provider objects in one company, so all
orders are checked in one database; the worker decides them in arrival order.
No provider account, real key, network call or money is involved.
"""

import json
from itertools import permutations
from typing import Any
from uuid import UUID

import pytest

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.providers import receipt_worker as worker
from tests.integration import test_provider_receipt_decisions as decided
from tests.integration.test_provider_receipt_attestations import Routed
from tests.unit import test_stripe_event_boundary as signed

pytestmark = pytest.mark.anyio
client = decided.client
idp = decided.idp
manager_a = decided.manager_a
manager_b = decided.manager_b
enabled = decided.enabled
inbox = decided.inbox
writer_pool = decided.writer_pool
routed = decided.routed
worker_pool = decided.worker_pool
CREATED = signed.NOW - 100_000

# One payment and its refund: (event type, status, created offset, expected decision reason).
LIFE = (
    ("payment_intent.processing", "processing", 0, "not_final"),
    ("payment_intent.succeeded", "succeeded", 10, "success"),
    ("charge.succeeded", "succeeded", 11, "success"),
    ("refund.created", "pending", 20, "not_final"),
    ("refund.updated", "succeeded", 30, "success"),
    # A stale snapshot: an older processing state delivered again under a new event ID.
    ("payment_intent.processing", "processing", 1, "not_final"),
)


def shaped(n: int, kind: str, status: str, created: int) -> bytes:
    payment = f"pi_FAKEperm{n}"
    if kind.startswith("payment_intent."):
        raw = decided.stripe(kind, status=status, object_id=payment)
    elif kind.startswith("charge."):
        raw = decided.stripe(
            kind, status=status, object_id=f"ch_FAKEperm{n}", payment_intent=payment
        )
    else:
        raw = decided.stripe(
            kind,
            status=status,
            object_id=f"re_FAKEperm{n}",
            payment_intent=payment,
            amount=400,
            charge=f"ch_FAKEperm{n}",
        )
    value: dict[str, Any] = json.loads(raw)
    value["created"] = created
    return signed.body(value)


async def decide_all(pool: RuntimePool, tenant: UUID) -> None:
    for _ in range(100):
        if not await worker.process_batch(pool, tenant_id=tenant, limit=worker.MAX_BATCH):
            return
    pytest.fail("the worker never finished")


async def outcomes(
    pool: RuntimePool, tenant: UUID
) -> tuple[dict[UUID, tuple[str, str]], dict[UUID, tuple[str, str, str | None]]]:
    async with tenant_transaction(pool, tenant) as conn:
        found = await (
            await conn.execute(
                "select d.event_id,d.outcome,d.reason,o.kind,o.provider_object_id,"
                "o.parent_object_id from gba.provider_event_decisions d "
                "left join gba.provider_operations o "
                "on o.tenant_id=d.tenant_id and o.id=d.operation_id where d.tenant_id=%s",
                (tenant,),
            )
        ).fetchall()
    return (
        {row[0]: (row[1], row[2]) for row in found},
        {row[0]: (row[3], row[4], row[5]) for row in found},
    )


async def run_orders(
    routed: Routed,
    writer_pool: RuntimePool,
    worker_pool: RuntimePool,
    life: tuple[tuple[str, str, int, str], ...],
) -> int:
    expected: dict[UUID, tuple[str, str]] = {}
    keys: dict[UUID, tuple[str, str, str | None]] = {}
    orders = list(permutations(range(len(life))))
    for n, order in enumerate(orders):
        raws = [shaped(n, *life[i][:2], CREATED + life[i][2]) for i in order]
        events = await decided.receive_all(writer_pool, routed, *raws)
        for i, event_id in zip(order, events, strict=True):
            kind, _, _, reason = life[i]
            expected[event_id] = ("observed", reason)
            keys[event_id] = (
                ("refund", f"re_FAKEperm{n}", f"pi_FAKEperm{n}")
                if kind.startswith("refund.")
                else ("payment", f"pi_FAKEperm{n}", None)
            )
    await decide_all(worker_pool, routed.tenant_id)
    decisions, operations = await outcomes(worker_pool, routed.tenant_id)
    assert decisions == expected
    assert operations == keys
    async with tenant_transaction(worker_pool, routed.tenant_id) as conn:
        row = await (
            await conn.execute(
                "select count(*) from gba.provider_operations where tenant_id=%s",
                (routed.tenant_id,),
            )
        ).fetchone()
    assert row is not None
    refunds = sum(1 for kind, *_ in life if kind.startswith("refund."))
    assert row[0] == len(orders) * (1 + (refunds > 0))
    return len(orders)


async def test_every_order_of_a_payment_and_its_refund_converges(
    routed: Routed, writer_pool: RuntimePool, worker_pool: RuntimePool
) -> None:
    assert await run_orders(routed, writer_pool, worker_pool, LIFE) == 720


async def test_equal_creation_times_converge_in_every_order(
    routed: Routed, writer_pool: RuntimePool, worker_pool: RuntimePool
) -> None:
    equal = tuple((kind, status, 0, reason) for kind, status, _, reason in LIFE[:3])
    assert await run_orders(routed, writer_pool, worker_pool, equal) == 6
