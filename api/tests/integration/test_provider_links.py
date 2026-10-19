"""K3b: an earlier manual payment that names a provider ID is linked to that operation.

Owner decisions 2026-10-19: link only (no journal; a linked operation is never applied); amount,
currency and direction exactly equal, dates at most 3 days apart; one to one; the linked payment
may still be voided or corrected, the link stays and a void returns the operation to review.
Synthetic only: no provider account, real key, network call or real money.
"""

import asyncio
from typing import Any
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import add_membership
from tests.integration import test_payment_corrections as correction_shared
from tests.integration import test_provider_payments as shared
from tests.integration.booking_support import BookingWorld
from tests.integration.configuration_support import Config
from tests.integration.seed import FakeUser, seed_user
from tests.integration.test_payment_corrections import CorrectionWorld
from tests.integration.test_provider_payments import Money, error, event
from tests.integration.test_settlements import _wait_for_blocked
from tests.support.fake_idp import FakeIdp

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
backend = shared.backend
money = shared.money
corrections = correction_shared.corrections
NOTE = "FAKE the bank payout of this Stripe payment was recorded by hand"
REFERENCE = "FAKE Stripe pi_FAKEpayment1"


async def manual(
    money: Money, amount: str = "10.00", reference: str = REFERENCE, date: str = "2026-10-02"
) -> tuple[UUID, UUID, UUID]:
    """A reserved settlement confirmed by a manual payment: obligation, settlement, payment."""
    obligation, settlement = await money.reserved(amount)
    payment = uuid7()
    recorded = await money.credits.payments.confirm(
        settlement,
        3,
        [(obligation, amount)],
        amount,
        reference,
        payment=payment,
        changes={"actual_external_date": date},
    )
    assert recorded.status_code == 200, recorded.text
    return obligation, settlement, payment


async def link(
    money: Money,
    operation: UUID,
    payment: UUID,
    note: object = NOTE,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    return await money.http.put(
        f"{money.root}/provider-operations/{operation}/link",
        json={"schema_version": 1, "payment_id": str(payment), "note": note},
        headers=headers or money.credits.ledger.headers(),
    )


async def state(money: Money, object_id: str = "pi_FAKEpayment1") -> str:
    (item,) = [x for x in await money.listed() if x["provider_object_id"] == object_id]
    value: str = item["state"]
    return value


async def detail(money: Money, operation: UUID) -> dict[str, Any]:
    response = await money.http.get(
        f"{money.root}/provider-operations/{operation}", headers=money.credits.ledger.auth
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


# L-01 -----------------------------------------------------------------------


async def test_a_blocked_operation_is_listed_as_needs_link(money: Money) -> None:
    await manual(money)
    await money.observe(event("payment_intent.succeeded"))
    assert await state(money) == "needs_link"
    response = await money.http.get(
        f"{money.root}/provider-operations",
        params={"state": "needs_link", "limit": 1},
        headers=money.credits.ledger.auth,
    )
    assert response.status_code == 200, response.text
    assert [x["provider_object_id"] for x in response.json()["items"]] == ["pi_FAKEpayment1"]
    assert response.json()["next_cursor"] is None


# L-02 -----------------------------------------------------------------------


async def test_linking_moves_no_money_and_marks_the_operation_linked(
    money: Money, app_pool: RuntimePool
) -> None:
    obligation, _, payment = await manual(money)
    await money.observe(event("payment_intent.succeeded"))
    operation = await money.operation()
    before = {
        table: await money.count(app_pool, table)
        for table in ("journal_entries", "external_payments", "external_payment_revisions")
    }
    balance = await money.world.balance(obligation)
    candidates = (await detail(money, operation))["manual_payments"]
    assert [(x["payment_id"], x["amount"], x["state"]) for x in candidates] == [
        (str(payment), "10.00", "confirmed")
    ]
    linked = await link(money, operation, payment)
    assert linked.status_code == 200, linked.text
    body = linked.json()
    assert body["operation"]["state"] == "linked"
    assert (body["link"]["payment_id"], body["link"]["note"]) == (str(payment), NOTE)
    assert body["link"]["linked_by"] == str(money.credits.ledger.user.user_id)
    assert (await link(money, operation, payment)).json() == body
    assert await state(money) == "linked"
    assert (await detail(money, operation))["link"] == body["link"]
    assert {table: await money.count(app_pool, table) for table in before} == before
    assert await money.world.balance(obligation) == balance


# L-03 -----------------------------------------------------------------------

_MISMATCH = [
    ("amount", {"amount": "9.00"}),
    ("date", {"date": "2026-10-01"}),
    ("reference", {"reference": "FAKE bank transfer 42"}),
]


@pytest.mark.parametrize(("reason", "changes"), _MISMATCH, ids=[r for r, _ in _MISMATCH])
async def test_a_payment_that_does_not_match_is_not_linked(
    money: Money, app_pool: RuntimePool, reason: str, changes: dict[str, str]
) -> None:
    _, _, payment = await manual(money, **changes)
    await money.observe(event("payment_intent.succeeded"))
    refused = await link(money, await money.operation(), payment)
    assert error(refused)[:2] == (409, "PROVIDER_LINK_MISMATCH"), refused.text
    assert error(refused)[2]["reason"] == reason
    assert await money.count(app_pool, "provider_payment_links") == 0


async def test_a_voided_payment_is_not_linked(
    money: Money, corrections: CorrectionWorld, app_pool: RuntimePool
) -> None:
    _, settlement, payment = await manual(money)
    voided = await corrections.void(settlement, payment, 4)
    assert voided.status_code == 200, voided.text
    await money.observe(event("payment_intent.succeeded"))
    refused = await link(money, await money.operation(), payment)
    assert error(refused)[:2] == (409, "PROVIDER_LINK_MISMATCH"), refused.text
    assert error(refused)[2]["reason"] == "voided"
    assert await money.count(app_pool, "provider_payment_links") == 0


async def test_an_operation_that_is_not_observed_is_not_linked(money: Money) -> None:
    _, _, payment = await manual(money)
    await money.observe(event("payment_intent.processing", status="processing"))
    refused = await link(money, await money.operation(), payment)
    assert error(refused)[:2] == (409, "PROVIDER_OPERATION_NOT_READY"), refused.text
    assert error(refused)[2]["reason"] == "not_final"
    assert (await link(money, uuid7(), payment)).status_code == 404


async def test_an_applied_operation_is_not_linked(money: Money) -> None:
    _, _, applied = await money.paid()
    _, _, payment = await manual(money)
    refused = await link(money, await money.operation(), payment)
    assert error(refused)[:2] == (409, "PROVIDER_OPERATION_APPLIED"), refused.text
    assert error(refused)[2]["payment_id"] == str(applied)


# L-04, L-05 -----------------------------------------------------------------


async def test_an_operation_links_to_one_payment_only(money: Money) -> None:
    _, _, first = await manual(money)
    # H keeps one payment per alias and reference: the second one names the ID differently.
    _, _, second = await manual(money, reference="FAKE second Stripe pi_FAKEpayment1")
    await money.observe(event("payment_intent.succeeded"))
    operation = await money.operation()
    assert (await link(money, operation, first)).status_code == 200
    refused = await link(money, operation, second)
    assert error(refused)[:2] == (409, "PROVIDER_OPERATION_LINKED"), refused.text
    assert error(refused)[2]["payment_id"] == str(first)
    other = await link(money, operation, first, "FAKE another note")
    assert error(other)[:2] == (409, "PROVIDER_OPERATION_LINKED"), other.text


async def test_two_links_of_one_operation_wait_and_one_wins(
    money: Money, app_pool: RuntimePool, owner_conn: psycopg.Connection
) -> None:
    payments = [
        (await manual(money, reference=f"FAKE Stripe pi_FAKEpayment1 copy {n}"))[2]
        for n in range(2)
    ]
    await money.observe(event("payment_intent.succeeded"))
    operation = await money.operation()
    business = money.credits.ledger.business
    async with tenant_transaction(app_pool, business) as conn:
        await conn.execute("select gba.lock_ledger(%s)", (business,))
        pending = [asyncio.create_task(link(money, operation, payment)) for payment in payments]
        try:
            await _wait_for_blocked(owner_conn, 2)
        except BaseException:
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            raise
    results = await asyncio.gather(*pending)
    assert sorted(r.status_code for r in results) == [200, 409]
    loser = next(r for r in results if r.status_code == 409)
    assert error(loser)[1] == "PROVIDER_OPERATION_LINKED"
    assert await money.count(app_pool, "provider_payment_links") == 1


async def test_a_linked_operation_is_never_applied(money: Money, app_pool: RuntimePool) -> None:
    _, _, payment = await manual(money)
    await money.observe(event("payment_intent.succeeded"))
    operation = await money.operation()
    assert (await link(money, operation, payment)).status_code == 200
    obligation, settlement = await money.reserved()
    refused = await money.apply(settlement, operation, [(obligation, "10.00")])
    assert error(refused)[:2] == (409, "PROVIDER_OPERATION_LINKED"), refused.text
    assert await money.count(app_pool, "external_payment_provenance") == 0


# L-06 -----------------------------------------------------------------------


async def test_sql_cannot_forge_or_change_a_link(
    money: Money, app_pool: RuntimePool, owner_conn: psycopg.Connection
) -> None:
    _, _, payment = await manual(money)
    _, _, short = await manual(money, amount="9.00", reference="FAKE short Stripe pi_FAKEpayment1")
    await money.observe(event("payment_intent.succeeded"))
    operation = await money.operation()
    assert (await link(money, operation, payment)).status_code == 200
    business = money.credits.ledger.business
    book = money.credits.ledger.book
    user = money.credits.ledger.user.user_id
    for statement in (
        "update gba.provider_payment_links set note='FAKE rewritten'",
        "delete from gba.provider_payment_links",
    ):
        with pytest.raises(psycopg.errors.Error):
            async with tenant_transaction(app_pool, business) as conn:
                await conn.execute(statement)
    with pytest.raises(psycopg.errors.Error):
        async with tenant_transaction(app_pool, business) as conn:
            # Another payment for a linked operation, of the wrong amount: refused in SQL.
            await conn.execute(
                "insert into gba.provider_payment_links "
                "(tenant_id,book_id,payment_id,operation_id,note,created_by) "
                "values (%s,%s,%s,%s,'FAKE forged',%s)",
                (business, book, short, operation, user),
            )
    with pytest.raises(psycopg.errors.Error):
        async with tenant_transaction(app_pool, business) as conn:
            await conn.execute("truncate gba.provider_payment_links")
    assert await money.count(app_pool, "provider_payment_links") == 1


async def test_sql_cannot_link_a_payment_that_does_not_match(
    money: Money, app_pool: RuntimePool
) -> None:
    _, _, short = await manual(money, amount="9.00")
    await money.observe(event("payment_intent.succeeded"))
    operation = await money.operation()
    ledger = money.credits.ledger
    with pytest.raises(psycopg.errors.Error):
        async with tenant_transaction(app_pool, ledger.business) as conn:
            await conn.execute(
                "insert into gba.provider_payment_links "
                "(tenant_id,book_id,payment_id,operation_id,note,created_by) "
                "values (%s,%s,%s,%s,'FAKE forged',%s)",
                (ledger.business, ledger.book, short, operation, ledger.user.user_id),
            )
    assert await money.count(app_pool, "provider_payment_links") == 0


# L-07 -----------------------------------------------------------------------


async def test_a_voided_linked_payment_returns_the_operation_to_review(
    money: Money, corrections: CorrectionWorld, app_pool: RuntimePool
) -> None:
    _, settlement, payment = await manual(money)
    await money.observe(event("payment_intent.succeeded"))
    operation = await money.operation()
    assert (await link(money, operation, payment)).status_code == 200
    voided = await corrections.void(settlement, payment, 4)
    assert voided.status_code == 200, voided.text
    assert await state(money) == "needs_review"
    assert (await detail(money, operation))["link"]["payment_id"] == str(payment)
    assert await money.count(app_pool, "provider_payment_links") == 1
    obligation, other = await money.reserved()
    refused = await money.apply(other, operation, [(obligation, "10.00")])
    assert error(refused)[:2] == (409, "PROVIDER_OPERATION_LINKED"), refused.text


# L-08 -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("role", "branch", "expected"),
    [
        ("owner", False, 200),
        ("front_desk", False, 403),
        ("artist", False, 403),
        ("manager", True, 403),
    ],
)
async def test_linking_keeps_company_finance_permissions(
    money: Money,
    owner_conn: psycopg.Connection,
    world: BookingWorld,
    idp: FakeIdp,
    role: str,
    branch: bool,
    expected: int,
) -> None:
    _, _, payment = await manual(money)
    await money.observe(event("payment_intent.succeeded"))
    member = seed_user(owner_conn, f"FAKE-K3b-{role}-{uuid7()}")
    add_membership(
        owner_conn,
        tenant_id=money.credits.ledger.business,
        user_id=member.user_id,
        role=role,
        location_id=world.a.location_id if branch else None,
    )
    auth = idp.bearer(member.subject, email=member.email)
    given = await link(money, await money.operation(), payment, headers=auth)
    assert given.status_code == expected, given.text


async def test_another_company_cannot_link(money: Money, manager_b: FakeUser, idp: FakeIdp) -> None:
    _, _, payment = await manual(money)
    await money.observe(event("payment_intent.succeeded"))
    refused = await link(
        money, await money.operation(), payment, headers=Config(money.http, idp).headers(manager_b)
    )
    assert refused.status_code in (403, 404), refused.text


# Guard ----------------------------------------------------------------------


async def test_a_damaged_link_control_fails_with_503(
    money: Money, owner_conn: psycopg.Connection
) -> None:
    _, _, payment = await manual(money)
    await money.observe(event("payment_intent.succeeded"))
    operation = await money.operation()
    owner_conn.execute(
        "alter table gba.provider_payment_links disable trigger provider_payment_links_check"
    )
    try:
        refused = await link(money, operation, payment)
        assert error(refused)[:2] == (503, "DATABASE_UNAVAILABLE"), refused.text
    finally:
        owner_conn.execute(
            "alter table gba.provider_payment_links enable trigger provider_payment_links_check"
        )
    assert (await link(money, operation, payment)).status_code == 200
