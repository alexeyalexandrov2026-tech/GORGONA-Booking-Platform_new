"""R5b: provider evidence for a rental card hold, sandbox only (FAKE data).

docs/plan/PACKAGE_R5B_DESIGN_2026-11-07.md: a recorded security event of a card hold names the
signature-checked test-mode receipt that shows it; the database checks the receipt's facts.
"""

from datetime import date
from typing import Any
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.business import ledger
from gorgona_booking.business.ledger_contracts import BookInput
from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import owner_tenant_transaction
from tests.integration import test_provider_receipt_attestations as attested
from tests.integration.configuration_support import Config
from tests.integration.seed import FakeUser, seed_other_branch
from tests.integration.test_r1_rental_catalog import (
    Rental,
    accepted,
    client,
    error,
    idp,
    manager_a,
    manager_b,
    rental,
)
from tests.integration.test_r4c_rental_extensions import agreed
from tests.integration.test_r5a_rental_security import DAMAGE, event, request
from tests.support.fake_idp import FakeIdp
from tests.unit import test_stripe_event_boundary as signed

pytestmark = pytest.mark.anyio
__all__ = ["accepted", "client", "idp", "manager_a", "manager_b", "rental", "writer_pool"]
writer_pool = attested.writer_pool
INTENT = "pi_FAKEhold1"


async def connect(rental: Rental, app_pool: RuntimePool, manager: FakeUser) -> attested.Routed:
    entity = uuid7()
    config = Config(rental.client, rental.idp)
    made = await rental.client.put(
        f"/v1/businesses/{rental.tenant}/legal-entities/{entity}",
        json={"expected_revision": 0, "code": "FAKE", "legal_name": "FAKE Rental LLC"},
        headers=config.headers(manager),
    )
    assert made.status_code == 200, made.text
    book = uuid7()
    async with tenant_transaction(app_pool, rental.tenant) as conn:
        await ledger.save_book(
            conn,
            business_id=rental.tenant,
            book_id=book,
            user_id=manager.user_id,
            actor=f"user:{manager.user_id}",
            key=str(uuid7()),
            body=BookInput(
                expected_revision=0,
                legal_entity_id=entity,
                base_currency="EUR",
                fiscal_year_start_month=1,
                accounting_start=date(2026, 1, 1),
            ),
        )
    connection = uuid7()
    namespace = "FAKE-rental-" + uuid7().hex
    with owner_tenant_transaction(rental.owner_conn, rental.tenant):
        rental.owner_conn.execute(
            "insert into gba.provider_receipt_connections "
            "(tenant_id,id,book_id,namespace,account_id,api_version) values (%s,%s,%s,%s,%s,%s)",
            (rental.tenant, connection, book, namespace, "acct_FAKEreceipt", "2026-09-30.endive"),
        )
    return attested.provision(
        rental.owner_conn,
        tenant_id=rental.tenant,
        connection_id=connection,
        book_id=book,
        namespace=namespace,
    )


def held_charge(amount: int = 20_000, *, intent: str = INTENT, **changes: Any) -> dict[str, Any]:
    value = signed.event("charge.succeeded")
    value["data"]["object"].update(
        {
            "id": "ch_FAKE" + uuid7().hex,
            "amount": amount,
            "amount_captured": 0,
            "amount_refunded": 0,
            "currency": "eur",
            "captured": False,
            "payment_intent": intent,
            **changes,
        }
    )
    return value


def intent_event(
    kind: str, received: int, *, amount: int = 20_000, intent: str = INTENT
) -> dict[str, Any]:
    value = signed.event(kind)
    value["data"]["object"].update(
        {
            "id": intent,
            "amount": amount,
            "amount_received": received,
            "currency": "eur",
            "status": "succeeded" if kind == "payment_intent.succeeded" else "canceled",
        }
    )
    return value


async def receipt(writer: RuntimePool, routed: attested.Routed, value: dict[str, Any]) -> UUID:
    value["id"] = "evt_FAKE" + uuid7().hex
    value["account"] = "acct_FAKEreceipt"
    result = await attested.receive(writer, routed, signed.body(value))
    assert result.disposition == "recorded", result
    return result.event_id


async def link(
    rental: Rental,
    booking: str,
    sequence: int,
    receipt_id: UUID,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    return await rental.client.post(
        f"{rental.base}/bookings/{booking}/security/events/{sequence}/provider",
        json={"schema_version": 1, "receipt_id": str(receipt_id)},
        headers={**(headers or rental.headers), "Idempotency-Key": str(uuid7())},
    )


async def held(rental: Rental) -> str:
    _, _, _, booking = await agreed(rental, 1)
    assert (await request(rental, booking)).status_code == 200
    assert (await event(rental, booking, "held", 20_000, reference=INTENT)).is_success
    return booking


# R5b-01 -----------------------------------------------------------------------------


async def test_a_card_hold_links_to_its_sandbox_receipts(
    rental: Rental, app_pool: RuntimePool, writer_pool: RuntimePool, manager_a: FakeUser
) -> None:
    routed = await connect(rental, app_pool, manager_a)
    booking = await held(rental)
    charge = await receipt(writer_pool, routed, held_charge())
    linked = await link(rental, booking, 1, charge)
    assert linked.status_code == 200, linked.text
    assert (await event(rental, booking, "captured", 5_000, basis=DAMAGE)).is_success
    success = await receipt(writer_pool, routed, intent_event("payment_intent.succeeded", 5_000))
    assert (await link(rental, booking, 2, success)).status_code == 200
    assert (await event(rental, booking, "released", 15_000)).is_success
    freed = await link(rental, booking, 3, success)
    assert freed.status_code == 200, freed.text
    view = (await rental.get(f"/bookings/{booking}/security")).json()
    evidence = [(e["provider"]["receipt_id"], e["provider"]["intent"]) for e in view["events"]]
    assert evidence == [(str(charge), INTENT), (str(success), INTENT), (str(success), INTENT)]


# R5b-02 -----------------------------------------------------------------------------


async def test_receipts_that_do_not_show_the_event_are_refused(
    rental: Rental, app_pool: RuntimePool, writer_pool: RuntimePool, manager_a: FakeUser
) -> None:
    routed = await connect(rental, app_pool, manager_a)
    booking = await held(rental)
    for value in (
        held_charge(amount_captured=1_000),
        held_charge(currency="usd"),
        held_charge(captured=True, amount_captured=20_000),
        intent_event("payment_intent.canceled", 0),
    ):
        refused = await link(rental, booking, 1, await receipt(writer_pool, routed, value))
        assert error(refused) == (409, "RENTAL_SECURITY_EVIDENCE"), refused.text
    charge = await receipt(writer_pool, routed, held_charge())
    assert (await link(rental, booking, 1, charge)).status_code == 200
    twice = await link(rental, booking, 1, charge)
    assert error(twice) == (409, "RENTAL_SECURITY_EVIDENCE"), twice.text
    assert error(await link(rental, booking, 9, charge)) == (404, "NOT_FOUND")
    assert (await event(rental, booking, "captured", 5_000, basis=DAMAGE)).is_success
    other = intent_event("payment_intent.succeeded", 5_000, intent="pi_FAKEother1")
    stranger = await link(rental, booking, 2, await receipt(writer_pool, routed, other))
    assert error(stranger) == (409, "RENTAL_SECURITY_EVIDENCE"), stranger.text
    small = intent_event("payment_intent.succeeded", 5_000, amount=19_000)
    short = await link(rental, booking, 2, await receipt(writer_pool, routed, small))
    assert error(short) == (409, "RENTAL_SECURITY_EVIDENCE"), short.text
    more = intent_event("payment_intent.succeeded", 6_000)
    wrong = await link(rental, booking, 2, await receipt(writer_pool, routed, more))
    assert error(wrong) == (409, "RENTAL_SECURITY_EVIDENCE"), wrong.text
    _, _, _, cash = await agreed(rental, 1)
    assert (await request(rental, cash, method="cash")).status_code == 200
    assert (await event(rental, cash, "held", 20_000, reference="FAKE-cash")).is_success
    second = await receipt(writer_pool, routed, held_charge(intent="pi_FAKEhold2"))
    not_card = await link(rental, cash, 1, second)
    assert error(not_card) == (409, "RENTAL_SECURITY_EVIDENCE"), not_card.text


# R5b-03 -----------------------------------------------------------------------------


async def test_revoked_connections_and_permissions(
    rental: Rental, app_pool: RuntimePool, writer_pool: RuntimePool, manager_a: FakeUser
) -> None:
    routed = await connect(rental, app_pool, manager_a)
    booking = await held(rental)
    charge = await receipt(writer_pool, routed, held_charge())
    assert (await link(rental, booking, 1, charge)).status_code == 200
    assert (await event(rental, booking, "captured", 5_000, basis=DAMAGE)).is_success
    success = await receipt(writer_pool, routed, intent_event("payment_intent.succeeded", 5_000))
    desk = rental.member("front_desk", rental.world.a.location_id)
    assert (await link(rental, booking, 2, success, headers=desk)).status_code == 403
    async with tenant_transaction(app_pool, rental.tenant) as conn:
        await conn.execute(
            "update gba.provider_receipt_connections set revoked = true, "
            "revoked_reason = 'retired' where id = %s",
            (routed.connection_id,),
        )
    revoked = await link(rental, booking, 2, success)
    assert error(revoked) == (409, "RENTAL_SECURITY_EVIDENCE"), revoked.text
    assert error(await link(rental, booking, 2, uuid7())) == (404, "NOT_FOUND")


# R5b-04 -----------------------------------------------------------------------------


async def test_sql_keeps_links_whole(
    rental: Rental, app_pool: RuntimePool, writer_pool: RuntimePool, manager_a: FakeUser
) -> None:
    routed = await connect(rental, app_pool, manager_a)
    booking = await held(rental)
    charge = await receipt(writer_pool, routed, held_charge())
    assert (await link(rental, booking, 1, charge)).status_code == 200
    canceled = await receipt(writer_pool, routed, intent_event("payment_intent.canceled", 0))
    tenant = rental.tenant
    for statement in (
        "update gba.rental_security_provider_links set receipt_id = receipt_id",
        "delete from gba.rental_security_provider_links",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with tenant_transaction(app_pool, tenant) as conn:
                await conn.execute(statement)
    assert (await event(rental, booking, "captured", 5_000, basis=DAMAGE)).is_success
    forged = (
        "insert into gba.rental_security_provider_links (tenant_id, security_id, sequence, "
        "receipt_id, intent, linked_by) select tenant_id, security_id, 2, %s, intent, linked_by "
        "from gba.rental_security_provider_links where sequence = 1"
    )
    with pytest.raises(psycopg.errors.CheckViolation):
        async with tenant_transaction(app_pool, tenant) as conn:
            await conn.execute(forged, (canceled,))
    view = (await rental.get(f"/bookings/{booking}/security")).json()
    assert [e["provider"] is None for e in view["events"]] == [False, True]


async def test_scope_module_and_another_company(
    rental: Rental,
    app_pool: RuntimePool,
    writer_pool: RuntimePool,
    idp: FakeIdp,
    manager_a: FakeUser,
    manager_b: FakeUser,
) -> None:
    routed = await connect(rental, app_pool, manager_a)
    away, _ = seed_other_branch(rental.owner_conn, rental.world.a)
    booking = await held(rental)
    charge = await receipt(writer_pool, routed, held_charge())
    branch = rental.member("manager", away)
    assert error(await link(rental, booking, 1, charge, headers=branch)) == (404, "NOT_FOUND")
    other = idp.bearer(manager_b.subject, email=manager_b.email)
    assert (await link(rental, booking, 1, charge, headers=other)).status_code in (403, 404)
    await Config(rental.client, idp).publish(
        manager_a, rental.tenant, 1, ["booking_resources", "counterparties", "finance"]
    )
    off = await link(rental, booking, 1, charge)
    assert error(off) == (409, "MODULE_DISABLED"), off.text
    count = "select count(*) from gba.rental_security_provider_links"
    async with tenant_transaction(app_pool, rental.tenant) as conn:
        mine = await (await conn.execute(count)).fetchone()
    assert mine == (0,)
    async with tenant_transaction(app_pool, rental.world.b.tenant_id) as conn:
        row = await (await conn.execute(count)).fetchone()
    assert row == (0,)
