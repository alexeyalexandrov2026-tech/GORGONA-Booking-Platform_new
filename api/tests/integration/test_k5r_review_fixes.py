"""K5r: fixes of the K5 final independent review (R1-R6, R9; R3 and R7 elsewhere).

Owner 2026-10-20: «делай, как ты считаешь нужным… я доверяю тебе» and «Да, запусти» for the review.
Synthetic only: no provider account, real key, network call or real money.
"""

import asyncio
import logging
import re
from uuid import uuid7

import psycopg
import pytest
from psycopg import sql

from gorgona_booking.business import provider_payments, provider_review
from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.providers import receipt_processes
from tests.integration import test_payment_corrections as correction_shared
from tests.integration import test_provider_payments as shared
from tests.integration import test_provider_receipt_processes as processes
from tests.integration.test_provider_connection_admissions import admit
from tests.integration.test_provider_links import REFERENCE, link, manual
from tests.integration.test_provider_payments import (
    ENTRY,
    Money,
    _refund_settlement,
    error,
    event,
)

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
logins = processes.logins
_SCAN = re.compile(r"lateral\s+gba\.provider_receipt_operation\(e\.facts\)")


# R1 -----------------------------------------------------------------------


async def test_the_events_of_one_operation_are_found_through_an_index(
    owner_conn: psycopg.Connection,
) -> None:
    tenant = uuid7()
    query = sql.SQL(
        "explain select e.id from gba.provider_event_inbox e where e.tenant_id={} "
        "and e.connection_id={} and e.operation_object_id={}"
    ).format(sql.Literal(tenant), sql.Literal(uuid7()), sql.Literal("pi_FAKEk5rIndex"))
    with owner_conn.transaction():
        # In a company's context, as every caller is (FORCE RLS would fold the plan otherwise).
        owner_conn.execute("select set_config('gba.tenant_id',%s,true)", (str(tenant),))
        owner_conn.execute("set local enable_seqscan=off")
        plan = "\n".join(str(r[0]) for r in owner_conn.execute(query).fetchall())
    assert "provider_event_inbox_operation" in plan
    # The key itself is an index condition under FORCE RLS, not a filter after the scan.
    condition = next(line for line in plan.splitlines() if "Index Cond" in line)
    assert "operation_object_id" in condition


async def test_no_money_check_decodes_every_event_of_a_connection(
    owner_conn: psycopg.Connection,
) -> None:
    rows = owner_conn.execute(
        "select p.proname, p.prosrc from pg_catalog.pg_proc p "
        "where p.pronamespace='gba'::regnamespace"
    ).fetchall()
    assert [name for name, source in rows if _SCAN.search(source)] == []
    assert not _SCAN.search(provider_payments._FACTS)


# R2 -----------------------------------------------------------------------


async def test_a_suspension_is_final_for_its_connection(
    money: Money, owner_conn: psycopg.Connection
) -> None:
    assert admit(owner_conn, money.routed, "suspended") == 2
    with pytest.raises(psycopg.errors.CheckViolation, match="suspended"):
        admit(owner_conn, money.routed)
    assert admit(owner_conn, money.routed, "suspended") == 3


# R4 -----------------------------------------------------------------------


async def test_sql_alone_cannot_link_for_a_suspended_connection(
    money: Money, app_pool: RuntimePool, owner_conn: psycopg.Connection
) -> None:
    _, _, payment = await manual(money)
    await money.observe(event("payment_intent.succeeded"))
    operation = await money.operation()
    admit(owner_conn, money.routed, "suspended")
    ledger = money.credits.ledger
    with pytest.raises(psycopg.errors.CheckViolation, match="admitted connection"):
        async with tenant_transaction(app_pool, ledger.business) as conn:
            await conn.execute(
                "insert into gba.provider_payment_links "
                "(tenant_id,book_id,payment_id,operation_id,note,created_by) "
                "values (%s,%s,%s,%s,'FAKE linked by hand',%s)",
                (ledger.business, ledger.book, payment, operation, ledger.user.user_id),
            )


async def test_sql_alone_cannot_record_provenance_for_a_suspended_connection(
    money: Money, app_pool: RuntimePool, owner_conn: psycopg.Connection
) -> None:
    await money.observe(event("payment_intent.succeeded"))
    operation = await money.operation()
    admit(owner_conn, money.routed, "suspended")
    ledger = money.credits.ledger
    with pytest.raises(psycopg.errors.CheckViolation, match="admitted connection"):
        async with tenant_transaction(app_pool, ledger.business) as conn:
            await conn.execute(
                "insert into gba.external_payment_provenance "
                "(tenant_id,book_id,payment_id,operation_id,created_by) values (%s,%s,%s,%s,%s)",
                (ledger.business, ledger.book, uuid7(), operation, ledger.user.user_id),
            )


# R5 -----------------------------------------------------------------------


async def test_the_refund_cap_counts_a_linked_refund(money: Money) -> None:
    # Invoice A is paid by the provider payment, invoice B by hand; both belong to one party.
    first, (first_line,) = await money.credits.invoice("10.00")
    paid = await money.world.reserved(first, "10.00")
    second, (second_line,) = await money.credits.invoice("10.00")
    by_hand = await money.world.reserved(second, "10.00")
    await money.observe(
        event("payment_intent.succeeded"),
        event("refund.updated", object_id="re_FAKEk5rLinked", amount=400),
        event("refund.updated", object_id="re_FAKEk5rOver", amount=700),
    )
    applied = await money.apply(paid, await money.operation(), [(first, "10.00")])
    assert applied.status_code == 200, applied.text
    bank = await money.credits.payments.confirm(
        by_hand, 3, [(second, "10.00")], "10.00", "FAKE bank transfer of invoice B", payment=uuid7()
    )
    assert bank.status_code == 200, bank.text
    # A refund of 4.00 recorded by hand and linked to its provider refund.
    refund, payable = await _refund_settlement(money, first, first_line, "4.00")
    linked = uuid7()
    recorded = await money.credits.payments.confirm(
        payable,
        3,
        [(refund, "4.00")],
        "4.00",
        "FAKE Stripe re_FAKEk5rLinked",
        payment=linked,
        changes={"actual_external_date": "2026-10-02", "entry_date": ENTRY},
    )
    assert recorded.status_code == 200, recorded.text
    done = await link(money, await money.operation("re_FAKEk5rLinked"), linked)
    assert done.status_code == 200, done.text
    # 4.00 linked + 7.00 would exceed the 10.00 the payment received.
    over, payable_2 = await _refund_settlement(money, second, second_line, "7.00")
    refused = await money.apply(
        payable_2, await money.operation("re_FAKEk5rOver"), [(over, "7.00")]
    )
    assert error(refused)[:2] == (409, "PROVIDER_PAYMENT_MISMATCH")
    assert error(refused)[2]["reason"] == "refund_cap"


# R6 -----------------------------------------------------------------------


async def test_a_refund_by_hand_naming_a_payment_does_not_block_it(money: Money) -> None:
    invoice, (line,) = await money.credits.invoice("10.00")
    settled = await money.world.reserved(invoice, "10.00")
    bank = await money.credits.payments.confirm(
        settled, 3, [(invoice, "10.00")], "10.00", "FAKE bank transfer", payment=uuid7()
    )
    assert bank.status_code == 200, bank.text
    refund, payable = await _refund_settlement(money, invoice, line, "2.00")
    payable_by_hand = await money.credits.payments.confirm(
        payable,
        3,
        [(refund, "2.00")],
        "2.00",
        "FAKE refund of pi_FAKEk5rDirection",
        payment=uuid7(),
        changes={"entry_date": ENTRY},
    )
    assert payable_by_hand.status_code == 200, payable_by_hand.text
    await money.observe(event("payment_intent.succeeded", object_id="pi_FAKEk5rDirection"))
    obligation, settlement = await money.reserved()
    applied = await money.apply(
        settlement, await money.operation("pi_FAKEk5rDirection"), [(obligation, "10.00")]
    )
    assert applied.status_code == 200, applied.text


async def test_a_refund_by_hand_may_name_an_applied_payment(money: Money) -> None:
    await money.observe(event("payment_intent.succeeded", object_id="pi_FAKEk5rApplied"))
    obligation, settlement = await money.reserved()
    applied = await money.apply(
        settlement, await money.operation("pi_FAKEk5rApplied"), [(obligation, "10.00")]
    )
    assert applied.status_code == 200, applied.text
    invoice, (line,) = await money.credits.invoice("10.00")
    settled = await money.world.reserved(invoice, "10.00")
    bank = await money.credits.payments.confirm(
        settled, 3, [(invoice, "10.00")], "10.00", "FAKE bank transfer", payment=uuid7()
    )
    assert bank.status_code == 200, bank.text
    refund, payable = await _refund_settlement(money, invoice, line, "2.00")
    named = await money.credits.payments.confirm(
        payable,
        3,
        [(refund, "2.00")],
        "2.00",
        "FAKE refund of pi_FAKEk5rApplied",
        payment=uuid7(),
        changes={"entry_date": ENTRY},
    )
    assert named.status_code == 200, named.text


async def test_a_receivable_naming_an_applied_payment_is_still_refused(money: Money) -> None:
    await money.observe(event("payment_intent.succeeded"))
    obligation, settlement = await money.reserved()
    applied = await money.apply(settlement, await money.operation(), [(obligation, "10.00")])
    assert applied.status_code == 200, applied.text
    other, other_settlement = await money.reserved()
    refused = await money.credits.payments.confirm(
        other_settlement, 3, [(other, "10.00")], "10.00", REFERENCE, payment=uuid7()
    )
    assert refused.status_code == 409, refused.text


# R3 -----------------------------------------------------------------------


async def test_the_worker_survives_a_failed_batch(
    logins: processes.Logins, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    calls = 0
    stop = asyncio.Event()

    async def flaky(pool: RuntimePool, **_: object) -> list[object]:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("FAKE transient failure")
        stop.set()
        return []

    monkeypatch.setattr(receipt_processes, "process_batch", flaky)
    settings = receipt_processes.worker_settings(
        {"GBA_RECEIPT_WORKER_DATABASE_URL": logins.worker}, ["--interval", "1"]
    )
    with caplog.at_level(logging.WARNING, logger=receipt_processes.logger.name):
        await asyncio.wait_for(receipt_processes.run_worker(settings, stop=stop), 30)
    assert calls == 2
    failed = [r for r in caplog.records if r.getMessage() == "provider receipt batch failed"]
    assert [r.__dict__.get("error") for r in failed] == ["RuntimeError"]
    assert "FAKE transient failure" not in caplog.text


# R9 -----------------------------------------------------------------------


def test_a_link_refused_for_admission_says_so() -> None:
    gate = psycopg.errors.CheckViolation(
        "provider money needs an admitted connection for this operation"
    )
    other = psycopg.errors.CheckViolation(
        "a linked manual payment must match its provider operation"
    )
    assert provider_review.link_refusal_reason(gate) == "not_admitted"
    assert provider_review.link_refusal_reason(other) == "facts"
