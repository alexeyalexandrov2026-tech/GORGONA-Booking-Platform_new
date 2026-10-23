"""L9a: the published fee policy for late cancellations and no-shows (package L, BEAUTY-01).

Design docs/plan/PACKAGE_L9_DESIGN_2026-10-23.md decisions 76-79; FAKE data only.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
import psycopg
import pytest

from gorgona_booking.booking.models import ReservationRequest
from gorgona_booking.booking.service import BookingService
from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from tests.integration import test_l4_billing as shared
from tests.integration.booking_support import BookingWorld
from tests.integration.fee_policy_support import publish_fee_policy, soon_visit
from tests.integration.test_external_payments import PaymentWorld
from tests.integration.test_l4_billing import bill, fee, post, visit
from tests.integration.test_l8a_review_fixes import confirmed, seed_variant

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
manager_b = shared.manager_b
enabled = shared.enabled
invoices = shared.invoices
payments = shared.payments
__all__ = ["client", "enabled", "idp", "invoices", "manager_a", "manager_b", "payments"]


def salon(payments: PaymentWorld) -> str:
    return f"/v1/salons/{payments.ledger.business}"


async def publish(payments: PaymentWorld, **changes: Any) -> httpx.Response:
    return await publish_fee_policy(
        payments.ledger.client, payments.ledger.business, payments.ledger.headers(), **changes
    )


def code(response: httpx.Response) -> tuple[int, str]:
    return response.status_code, response.json()["error"]["code"]


def lines(response: httpx.Response) -> list[tuple[str, str]]:
    assert response.status_code == 200, response.text
    return [(line["description"], line["amount"]) for line in response.json()["invoice"]["lines"]]


async def past_visit(world: BookingWorld, pool: RuntimePool, *, hours_ago: int = 3) -> UUID:
    """A confirmed visit (base 50.00 + massage 20.00) that started `hours_ago` hours ago."""
    start = datetime.now(UTC).replace(second=0, microsecond=0) - timedelta(hours=hours_ago)
    result = await BookingService(pool).create_confirmed_booking(
        world.a.tenant_id,
        ReservationRequest(
            resource_id=world.artist_a1,
            variant_id=world.catalog_a.base_variant_id,
            starts_at=start,
            add_on_ids=(world.catalog_a.massage_add_on_id,),
        ),
        actor="test:l9a",
        idempotency_key=None,
    )
    return result.booking_id


async def no_show(
    payments: PaymentWorld, booking: UUID, *, key: str | None = None
) -> httpx.Response:
    return await payments.ledger.client.post(
        f"{salon(payments)}/bookings/{booking}/no-show",
        json={},
        headers=payments.ledger.headers(key),
    )


async def _count(pool: RuntimePool, tenant: UUID, statement: str) -> int:
    async with tenant_transaction(pool, tenant) as conn:
        row = await (await conn.execute(statement)).fetchone()
    assert row is not None
    return int(row[0])


# L9-01 (decision 76) ----------------------------------------------------------------


async def test_fee_policy_versions_are_insert_only_and_company_scoped(
    payments: PaymentWorld, world: BookingWorld, app_pool: RuntimePool
) -> None:
    first = await publish(payments, late={"percent": "50.00"})
    assert first.status_code == 200, first.text
    assert first.json()["version"] == 1
    assert code(await publish(payments, expected_version=0)) == (
        409,
        "VISIT_FEE_POLICY_VERSION_CONFLICT",
    )
    second = await publish(
        payments, expected_version=1, free_minutes=60, no_show={"amount": "20.00"}
    )
    assert second.status_code == 200, second.text
    assert second.json()["version"] == 2
    read = await payments.ledger.client.get(
        f"{salon(payments)}/visit-fee-policy", headers=payments.ledger.headers()
    )
    assert read.status_code == 200, read.text
    versions = read.json()["versions"]
    assert [v["version"] for v in versions] == [2, 1]
    assert versions[0]["free_cancellation_minutes"] == 60
    assert versions[0]["no_show_fee"] == {"amount": "20.00"}
    assert versions[0]["late_cancellation_fee"] is None
    assert versions[1]["late_cancellation_fee"] == {"percent": "50.00"}
    for wrong in ({"percent": "100.01"}, {"percent": "10.00", "amount": "1.00"}, {}):
        refused = await publish(payments, expected_version=2, late=wrong)
        assert refused.status_code == 422, refused.text
    for statement in (
        "update gba.visit_fee_policies set late_fee_bp = 0",
        "delete from gba.visit_fee_policies",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with tenant_transaction(app_pool, world.a.tenant_id) as conn:
                await conn.execute(statement)
    count = "select count(*) from gba.visit_fee_policies"
    assert await _count(app_pool, world.a.tenant_id, count) == 2
    assert await _count(app_pool, world.b.tenant_id, count) == 0


# L9-02 (decision 77) ----------------------------------------------------------------


async def test_a_visit_uses_the_version_in_force_when_it_was_booked(
    payments: PaymentWorld, world: BookingWorld, app_pool: RuntimePool
) -> None:
    before = await soon_visit(world, app_pool, hours=2, cancel=True)
    assert (await publish(payments, late={"percent": "33.35"})).status_code == 200
    booking = await soon_visit(world, app_pool, hours=4, cancel=True)
    later = await publish(payments, expected_version=1, late={"percent": "10.00"})
    assert later.status_code == 200, later.text
    # 33.35 % of 70.00 is 23.345: half up to 23.35; the later 10 % does not apply.
    assert lines(await post(payments, booking, bill(payments))) == [
        ("Late cancellation fee", "23.35")
    ]
    # Booked before any policy: there is no fee to bill.
    assert code(await post(payments, before, bill(payments))) == (409, "VISIT_NOT_BILLABLE")


# L9-03 (decision 79) ----------------------------------------------------------------


async def test_a_late_cancellation_is_billed_its_fee_in_every_currency(
    payments: PaymentWorld,
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    app_pool: RuntimePool,
) -> None:
    assert (await publish(payments, late={"amount": "15.00"})).status_code == 200
    yen = seed_variant(owner_conn, world, "FAKE_YEN_FEE", "JPY", 500000)
    dinar = seed_variant(owner_conn, world, "FAKE_DINAR_FEE", "KWD", 1000)
    service = BookingService(app_pool)
    for hours, variant, amount in ((2, None, "15.00"), (4, yen, "15"), (6, dinar, "15.000")):
        booking = await soon_visit(
            world, app_pool, hours=hours, variant=variant, add_ons=(), cancel=True
        )
        assert lines(await post(payments, booking, bill(payments))) == [
            ("Late cancellation fee", amount)
        ]
    # The old booking of a reschedule is not a cancellation of the visit.
    moved = await soon_visit(world, app_pool, hours=8, add_ons=())
    await service.cancel(
        world.a.tenant_id, moved, actor="test:l9a", reason="rescheduled_to_new_booking"
    )
    assert code(await post(payments, moved, bill(payments))) == (409, "VISIT_NOT_BILLABLE")
    # Cancelled inside the free window of a later version: no fee.
    early_policy = await publish(
        payments, expected_version=1, free_minutes=0, late={"amount": "15.00"}
    )
    assert early_policy.status_code == 200, early_policy.text
    early = await soon_visit(world, app_pool, hours=10, add_ons=(), cancel=True)
    assert code(await post(payments, early, bill(payments))) == (409, "VISIT_NOT_BILLABLE")


# L9-04 (decision 78) ----------------------------------------------------------------


async def test_a_no_show_is_recorded_once_and_billed_its_fee(
    payments: PaymentWorld, world: BookingWorld, app_pool: RuntimePool
) -> None:
    assert (await publish(payments, no_show={"percent": "50.00"})).status_code == 200
    booking = await past_visit(world, app_pool)
    first = await no_show(payments, booking, key="l9a-no-show-1")
    assert first.status_code == 200, first.text
    view = first.json()
    assert (view["booking_id"], view["policy_version"], view["fee"]) == (str(booking), 1, "35.00")
    for key in ("l9a-no-show-1", "l9a-no-show-2"):
        again = await no_show(payments, booking, key=key)
        assert again.status_code == 200, again.text
        assert again.json() == view
    read = await payments.ledger.client.get(
        f"{salon(payments)}/bookings/{booking}/no-show", headers=payments.ledger.headers()
    )
    assert read.status_code == 200, read.text
    assert read.json() == view
    assert lines(await post(payments, booking, bill(payments))) == [("No-show fee", "35.00")]
    base = f"{salon(payments)}/bookings/{booking}"
    completed = await payments.ledger.client.post(
        f"{base}/complete", json={}, headers=payments.ledger.headers()
    )
    assert code(completed) == (409, "VISIT_NO_SHOW")
    cancelled = await payments.ledger.client.post(
        f"{base}/cancel", json={}, headers=payments.ledger.headers()
    )
    assert code(cancelled) == (409, "VISIT_ALREADY_RECORDED")
    # Not yet started, or already completed: no no-show.
    future = await visit(world, app_pool)
    assert code(await no_show(payments, future)) == (409, "VISIT_NOT_STARTED")
    attended = await past_visit(world, app_pool, hours_ago=6)
    done = await payments.ledger.client.post(
        f"{salon(payments)}/bookings/{attended}/complete",
        json={},
        headers=payments.ledger.headers(),
    )
    assert done.status_code == 200, done.text
    assert code(await no_show(payments, attended)) == (409, "VISIT_ALREADY_COMPLETED")
    unread = await payments.ledger.client.get(
        f"{salon(payments)}/bookings/{attended}/no-show", headers=payments.ledger.headers()
    )
    assert unread.status_code == 404, unread.text
    for statement in (
        "update gba.visit_no_shows set policy_version = null",
        "delete from gba.visit_no_shows",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with tenant_transaction(app_pool, world.a.tenant_id) as conn:
                await conn.execute(statement)
    count = "select count(*) from gba.visit_no_shows"
    assert await _count(app_pool, world.a.tenant_id, count) == 1
    assert await _count(app_pool, world.b.tenant_id, count) == 0


# L9-05 (decision 79) ----------------------------------------------------------------


async def test_typed_fees_only_on_an_attended_visit(
    payments: PaymentWorld, world: BookingWorld, app_pool: RuntimePool
) -> None:
    published = await publish(payments, late={"amount": "15.00"}, no_show={"amount": "20.00"})
    assert published.status_code == 200, published.text
    cancelled = await soon_visit(world, app_pool, hours=2, cancel=True)
    typed = bill(payments, fee_lines=[fee(payments)])
    assert code(await post(payments, cancelled, typed)) == (422, "VISIT_FEE_FROM_POLICY")
    missed = await past_visit(world, app_pool)
    assert (await no_show(payments, missed)).status_code == 200
    assert code(await post(payments, missed, typed)) == (422, "VISIT_FEE_FROM_POLICY")
    attended = await confirmed(app_pool, world, 13)
    billed = lines(await post(payments, attended, bill(payments, fee_lines=[fee(payments)])))
    assert billed[-1] == ("FAKE late cancellation fee", "5.00")
    assert len(billed) == 2
