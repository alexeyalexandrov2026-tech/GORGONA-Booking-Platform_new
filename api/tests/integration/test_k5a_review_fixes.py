"""K5a-fix: the verified findings of the K5a independent review, one or more cases each.

Owner decisions 2026-10-19: fix findings 1, 2, 3, 5, 7, 10, 11, 13 and 14 in one slice; for
finding 4 only a `compromise` revocation of a verification config blocks money, `rotation` and
`retired` do not. Synthetic only: no provider account, real key, network call or real money.
"""

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid7

import psycopg
import pytest

from gorgona_booking import observability
from gorgona_booking.business import provider_review, settlements
from gorgona_booking.business.settlement_contracts import ProviderAttentionItem
from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import owner_tenant_transaction
from tests.integration import test_payment_corrections as correction_shared
from tests.integration import test_provider_payments as shared
from tests.integration import test_provider_receipt_decisions as decided
from tests.integration.configuration_support import Config
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.seed import FakeUser
from tests.integration.test_payment_corrections import CorrectionWorld
from tests.integration.test_provider_links import REFERENCE, link, manual, state
from tests.integration.test_provider_payments import (
    ENTRY,
    Money,
    _refund_settlement,
    error,
    event,
)
from tests.integration.test_provider_review import Recorder, acknowledge
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
VOID = {
    "schema_version": 1,
    "entry_date": ENTRY,
    "attestation": "attested_erroneous_confirmation",
    "reason": "FAKE applied to the wrong obligation",
    "evidence_source": "FAKE finance review",
}


async def _manual(money: Money, reference: str, amount: str = "10.00") -> Any:
    """A manual confirmation of a new reserved settlement with this reference."""
    obligation, settlement = await money.reserved(amount)
    return await money.credits.payments.confirm(
        settlement, 3, [(obligation, amount)], amount, reference, payment=uuid7()
    )


async def _void(money: Money, settlement: object, payment: UUID, sequence: int) -> None:
    voided = await money.http.post(
        f"{money.root}/settlements/{settlement}/confirmations/{payment}/void",
        json={**VOID, "expected_sequence": sequence},
        headers=money.credits.ledger.headers(),
    )
    assert voided.status_code == 200, voided.text


# 1 --------------------------------------------------------------------------


async def test_a_manual_payment_cannot_name_an_applied_operation(
    money: Money, app_pool: RuntimePool
) -> None:
    _, _, payment = await money.paid()
    before = await money.count(app_pool, "external_payments")
    # Case and invisible characters do not hide the provider ID (finding 13).
    for reference in (REFERENCE, "FAKE Stripe PI_FAKEPAYMENT1", "FAKE Stripe pi_FAKE​payment1"):
        refused = await _manual(money, reference)
        assert error(refused)[:2] == (409, "PROVIDER_OPERATION_APPLIED"), refused.text
        assert error(refused)[2]["payment_id"] == str(payment)
        assert error(refused)[2]["operation_id"] == str(await money.operation())
    assert await money.count(app_pool, "external_payments") == before


async def test_sql_refuses_a_manual_payment_naming_an_applied_operation(
    money: Money, app_pool: RuntimePool, monkeypatch: pytest.MonkeyPatch
) -> None:
    await money.paid()
    before = await money.count(app_pool, "external_payments")

    async def skipped(*_: object, **__: object) -> None:
        return None

    # Without the service check the H trigger still refuses it, in the same transaction.
    monkeypatch.setattr(settlements, "_refuse_recorded_provider_id", skipped)
    refused = await _manual(money, REFERENCE)
    assert error(refused)[:2] == (409, "FINANCIAL_STATE_INVALID"), refused.text
    assert await money.count(app_pool, "external_payments") == before


async def test_a_manual_payment_cannot_name_a_linked_operation(
    money: Money, app_pool: RuntimePool
) -> None:
    _, _, first = await manual(money)
    await money.observe(event("payment_intent.succeeded"))
    assert (await link(money, await money.operation(), first)).status_code == 200
    # Another reference (the H identity refuses the same one) that names the same ID.
    refused = await _manual(money, "FAKE bank payout pi_FAKEpayment1")
    assert error(refused)[:2] == (409, "PROVIDER_OPERATION_LINKED"), refused.text
    assert error(refused)[2]["payment_id"] == str(first)
    assert await money.count(app_pool, "external_payments") == 1


async def test_after_a_void_the_money_may_be_recorded_by_hand(money: Money) -> None:
    _, settlement, payment = await money.paid()
    await _void(money, settlement, payment, 4)
    # The voided provider payment no longer counts, so a manual record is no duplicate.
    recorded = await _manual(money, REFERENCE)
    assert recorded.status_code == 200, recorded.text


# 2 --------------------------------------------------------------------------


async def test_a_refund_failure_after_its_success_is_a_conflict(money: Money) -> None:
    invoice, (line,) = await money.credits.invoice("10.00")
    settlement = await money.world.reserved(invoice, "10.00")
    await money.observe(
        event("payment_intent.succeeded"),
        event("refund.updated", object_id="re_FAKEk5aLate", amount=400),
    )
    paid = await money.apply(settlement, await money.operation(), [(invoice, "10.00")])
    assert paid.status_code == 200, paid.text
    refund, payable = await _refund_settlement(money, invoice, line, "4.00")
    applied = await money.apply(
        payable, await money.operation("re_FAKEk5aLate"), [(refund, "4.00")]
    )
    assert applied.status_code == 200, applied.text
    await money.observe(
        event("refund.failed", object_id="re_FAKEk5aLate", amount=400, status="failed")
    )
    assert await state(money, "re_FAKEk5aLate") == "applied_with_conflict"


async def test_a_refund_success_after_its_failure_is_a_conflict(money: Money) -> None:
    invoice, (line,) = await money.credits.invoice("10.00")
    settlement = await money.world.reserved(invoice, "10.00")
    await money.observe(event("payment_intent.succeeded"))
    paid = await money.apply(settlement, await money.operation(), [(invoice, "10.00")])
    assert paid.status_code == 200, paid.text
    await money.observe(
        event("refund.updated", object_id="re_FAKEk5aEarly", amount=400, status="canceled")
    )
    await money.observe(event("refund.updated", object_id="re_FAKEk5aEarly", amount=400))
    assert await state(money, "re_FAKEk5aEarly") == "needs_review"
    refund, payable = await _refund_settlement(money, invoice, line, "4.00")
    refused = await money.apply(
        payable, await money.operation("re_FAKEk5aEarly"), [(refund, "4.00")]
    )
    assert error(refused)[:2] == (409, "PROVIDER_OPERATION_NOT_READY"), refused.text
    assert error(refused)[2]["reason"] == "needs_review"


# 3 --------------------------------------------------------------------------


async def test_a_refused_foreign_application_is_not_counted(
    money: Money, manager_b: FakeUser, idp: FakeIdp, monkeypatch: pytest.MonkeyPatch
) -> None:
    applications = Recorder()
    monkeypatch.setattr(observability, "_provider_applications", applications)
    obligation, settlement = await money.reserved()
    await money.observe(event("payment_intent.succeeded"))
    operation = await money.operation()
    foreign = await money.apply(
        settlement,
        operation,
        [(obligation, "10.00")],
        headers=Config(money.http, idp).headers(manager_b),
    )
    assert foreign.status_code in (403, 404), foreign.text
    for _ in range(3):
        stranger = await money.http.post(
            money.root.replace(str(money.routed.tenant_id), str(uuid7()))
            + f"/settlements/{settlement}/provider-confirmations/{uuid7()}",
            json=money.body(operation, [(obligation, "10.00")]),
            headers=money.credits.ledger.headers(),
        )
        assert stranger.status_code in (403, 404), stranger.text
    assert applications.points == []
    applied = await money.apply(settlement, operation, [(obligation, "10.00")])
    assert applied.status_code == 200, applied.text
    tenant = str(money.routed.tenant_id)
    assert applications.points == [(1, {"result": "applied", "tenant_id": tenant})]


# 4 --------------------------------------------------------------------------


def _revoke(
    owner_conn: psycopg.Connection, tenant: UUID, table: str, target: UUID, reason: str
) -> None:
    with owner_tenant_transaction(owner_conn, tenant):
        owner_conn.execute(
            f"update gba.{table} set revoked=true,revoked_reason=%s where tenant_id=%s and id=%s",
            (reason, tenant, target),
        )


def _revoke_config(owner_conn: psycopg.Connection, money: Money, reason: str) -> None:
    _revoke(
        owner_conn,
        money.routed.tenant_id,
        "provider_verification_configs",
        money.routed.verification_config_id,
        reason,
    )


@pytest.mark.parametrize("reason", ["rotation", "retired"])
async def test_a_routine_key_revocation_keeps_earlier_operations_usable(
    money: Money, owner_conn: psycopg.Connection, reason: str
) -> None:
    obligation, settlement = await money.reserved()
    await money.observe(event("payment_intent.succeeded"))
    _revoke_config(owner_conn, money, reason)
    assert await state(money) == "observed"
    applied = await money.apply(settlement, await money.operation(), [(obligation, "10.00")])
    assert applied.status_code == 200, applied.text


async def test_a_routine_key_revocation_keeps_linking_possible(
    money: Money, owner_conn: psycopg.Connection
) -> None:
    _, _, payment = await manual(money)
    await money.observe(event("payment_intent.succeeded"))
    _revoke_config(owner_conn, money, "rotation")
    linked = await link(money, await money.operation(), payment)
    assert linked.status_code == 200, linked.text


async def test_a_compromised_key_still_blocks_linking(
    money: Money, owner_conn: psycopg.Connection
) -> None:
    _, _, payment = await manual(money)
    await money.observe(event("payment_intent.succeeded"))
    _revoke_config(owner_conn, money, "compromise")
    assert await state(money) == "revoked"
    refused = await link(money, await money.operation(), payment)
    assert error(refused)[:2] == (409, "PROVIDER_OPERATION_NOT_READY"), refused.text
    assert error(refused)[2]["reason"] == "revoked"


# 5 --------------------------------------------------------------------------


async def test_a_voided_manual_payment_no_longer_blocks_the_operation(
    money: Money, corrections: CorrectionWorld, app_pool: RuntimePool
) -> None:
    _, settlement, payment = await manual(money)
    voided = await corrections.void(settlement, payment, 4)
    assert voided.status_code == 200, voided.text
    await money.observe(event("payment_intent.succeeded"))
    assert await state(money) == "observed"
    obligation, other = await money.reserved()
    applied = await money.apply(other, await money.operation(), [(obligation, "10.00")])
    assert applied.status_code == 200, applied.text
    assert await money.count(app_pool, "external_payment_provenance") == 1


# 7 --------------------------------------------------------------------------


@pytest.mark.parametrize("table", ["provider_receipt_connections", "provider_verification_configs"])
async def test_a_revocation_waits_for_an_application_in_progress(
    money: Money,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
    test_database: ProvisionedDatabase,
    table: str,
) -> None:
    obligation, settlement = await money.reserved()
    await money.observe(event("payment_intent.succeeded"))
    tenant = money.routed.tenant_id
    target = (
        money.routed.connection_id
        if table == "provider_receipt_connections"
        else money.routed.verification_config_id
    )
    monitor = await psycopg.AsyncConnection.connect(
        test_database.admin_dsn, dbname=test_database.name, autocommit=True
    )
    revocation = None
    try:
        # Every application and link holds the company ledger lock until it commits.
        async with tenant_transaction(app_pool, tenant) as conn:
            await conn.execute("select gba.lock_ledger(%s)", (tenant,))
            revocation = asyncio.create_task(
                asyncio.to_thread(_revoke, owner_conn, tenant, table, target, "compromise")
            )
            await decided.blocked_by(monitor, await backend(conn), f"update gba.{table}")
            assert not revocation.done()
        await asyncio.wait_for(revocation, 15)
    finally:
        if revocation is not None and not revocation.done():
            await asyncio.wait_for(revocation, 15)
        await monitor.close()
    refused = await money.apply(settlement, await money.operation(), [(obligation, "10.00")])
    assert error(refused)[:2] == (409, "PROVIDER_OPERATION_NOT_READY"), refused.text
    assert error(refused)[2]["reason"] == "revoked"


# 10 -------------------------------------------------------------------------


async def test_a_link_refused_by_sql_is_a_typed_refusal(
    money: Money, app_pool: RuntimePool, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, payment = await manual(money, amount="9.00")
    await money.observe(event("payment_intent.succeeded"))
    # The service believes the amounts agree; the SQL trigger still compares them.
    monkeypatch.setattr(provider_review, "to_minor", lambda *_: 1000)
    refused = await link(money, await money.operation(), payment)
    assert error(refused)[:2] == (409, "PROVIDER_LINK_MISMATCH"), refused.text
    assert error(refused)[2]["reason"] == "facts"
    assert await money.count(app_pool, "provider_payment_links") == 0


async def test_an_acknowledgement_refused_by_sql_is_a_typed_refusal(
    money: Money, monkeypatch: pytest.MonkeyPatch
) -> None:
    (raw,) = await money.observe(event("payment_intent.succeeded"))

    async def pretended(*_: object) -> ProviderAttentionItem:
        # The service is told the event has no operation; it does have one.
        return ProviderAttentionItem(
            event_id=raw,
            connection_id=money.routed.connection_id,
            kind="no_operation",
            event_type="payment_intent.succeeded",
            object_id="pi_FAKEpayment1",
            created=datetime(2026, 10, 5, 12, tzinfo=UTC),
            reason="unkeyed_operation",
            acknowledgement=None,
        )

    monkeypatch.setattr(provider_review, "_attention_item", pretended)
    refused = await acknowledge(money, str(raw))
    assert error(refused)[:2] == (409, "PROVIDER_ATTENTION_NOT_NEEDED"), refused.text
    assert error(refused)[2]["reason"] == "facts"


# 11 -------------------------------------------------------------------------


async def test_the_refund_cap_follows_the_corrected_parent(
    money: Money, corrections: CorrectionWorld
) -> None:
    invoice, _ = await money.credits.invoice("10.00")
    settlement = await money.world.reserved(invoice, "10.00")
    await money.observe(
        event("payment_intent.succeeded"),
        event("refund.updated", object_id="re_FAKEk5aCap", amount=700),
    )
    parent = uuid7()
    paid = await money.apply(
        settlement, await money.operation(), [(invoice, "10.00")], payment=parent
    )
    assert paid.status_code == 200, paid.text
    # The finance user attests that only 6.00 was received (no credit depends on it yet).
    corrected = await corrections.correct(
        settlement,
        parent,
        4,
        [(invoice, "6.00")],
        "6.00",
        cash_account_id=str(money.clearing),
        entry_date="2026-10-07",
    )
    assert corrected.status_code == 200, corrected.text
    # A refund obligation of the same party, from another paid invoice.
    other, (line,) = await money.credits.invoice("10.00")
    await money.credits.paid(other, "10.00", "FAKE-K5A-MANUAL-OTHER")
    refund, payable = await _refund_settlement(money, other, line, "7.00")
    over = await money.apply(payable, await money.operation("re_FAKEk5aCap"), [(refund, "7.00")])
    assert error(over)[:2] == (409, "PROVIDER_PAYMENT_MISMATCH"), over.text
    assert error(over)[2]["reason"] == "refund_cap"


# 14 -------------------------------------------------------------------------


async def test_the_overview_names_the_business_time_zone(
    money: Money, owner_conn: psycopg.Connection
) -> None:
    overview = await money.http.get(
        money.root.split("/books/")[0] + "/overview", headers=money.credits.ledger.auth
    )
    assert overview.status_code == 200, overview.text
    # In the company's context: FORCE RLS hides its locations from a bare owner session.
    with owner_tenant_transaction(owner_conn, money.routed.tenant_id):
        row = owner_conn.execute(
            "select gba.business_timezone(%s)", (money.routed.tenant_id,)
        ).fetchone()
    assert row is not None
    assert overview.json()["timezone"] == row[0]
