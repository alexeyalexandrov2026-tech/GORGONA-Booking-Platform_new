"""K5b: the open findings 6, 8, 9, 12 and 15 of the K5a independent review.

Owner decision 2026-10-20: the real Stripe test run (K0c) is postponed and FIN-02 stays planned;
the findings that need no provider are fixed locally. Synthetic only: no provider account, real
key, network call or real money.
"""

import re
from uuid import uuid7

import psycopg
import pytest
from psycopg import sql

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from tests.integration import test_payment_corrections as correction_shared
from tests.integration import test_provider_payments as shared
from tests.integration.configuration_support import Config
from tests.integration.test_provider_links import link, manual
from tests.integration.test_provider_payments import Money, error, event
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
LINK = (
    "insert into gba.provider_payment_links "
    "(tenant_id,book_id,payment_id,operation_id,note,created_by) "
    "values (%s,%s,%s,%s,'FAKE linked by hand',%s)"
)


# 6 ------------------------------------------------------------------------


async def test_the_inbox_of_one_connection_is_found_through_an_index(
    owner_conn: psycopg.Connection,
) -> None:
    row = owner_conn.execute(
        "select pg_catalog.pg_get_indexdef(i.indexrelid) from pg_catalog.pg_index i "
        "join pg_catalog.pg_class c on c.oid=i.indexrelid "
        "where c.relnamespace='gba'::regnamespace and c.relname='provider_event_inbox_connection'"
    ).fetchone()
    assert row == (
        "CREATE INDEX provider_event_inbox_connection ON gba.provider_event_inbox "
        "USING btree (tenant_id, connection_id)",
    )
    # The operation list and the link check look up the events of one connection.
    query = sql.SQL(
        "explain select e.id from gba.provider_event_inbox e "
        "where e.tenant_id={} and e.connection_id={}"
    ).format(sql.Literal(uuid7()), sql.Literal(uuid7()))
    with owner_conn.transaction():
        owner_conn.execute("set local enable_seqscan=off")
        plan = "\n".join(str(r[0]) for r in owner_conn.execute(query).fetchall())
    assert "provider_event_inbox_connection" in plan


# 8 ------------------------------------------------------------------------


async def test_sql_cannot_link_while_the_finance_workflow_is_off(
    money: Money, app_pool: RuntimePool, idp: FakeIdp
) -> None:
    _, _, payment = await manual(money)
    await money.observe(event("payment_intent.succeeded"))
    operation = await money.operation()
    ledger = money.credits.ledger
    await Config(ledger.client, idp).publish(ledger.user, ledger.business, 2, ["booking_resources"])
    assert error(await link(money, operation, payment))[:2] == (409, "MODULE_DISABLED")
    with pytest.raises(psycopg.errors.Error) as gated:
        async with tenant_transaction(app_pool, ledger.business) as conn:
            await conn.execute(
                LINK, (ledger.business, ledger.book, payment, operation, ledger.user.user_id)
            )
    assert gated.value.sqlstate == "GBM01"
    assert await money.count(app_pool, "provider_payment_links") == 0


# 9 (IR-03) ----------------------------------------------------------------


async def test_only_the_receipt_writer_records_events(
    money: Money, app_pool: RuntimePool, owner_conn: psycopg.Connection
) -> None:
    for table in ("provider_event_inbox", "provider_event_deliveries"):
        assert owner_conn.execute(
            "select pg_catalog.has_table_privilege('gba_runtime',%s,'INSERT'), "
            "pg_catalog.has_any_column_privilege('gba_runtime',%s,'INSERT')",
            ("gba." + table, "gba." + table),
        ).fetchone() == (False, False)
    tenant = money.routed.tenant_id
    for statement, values in (
        (
            "insert into gba.provider_event_inbox (tenant_id,id,connection_id,facts) "
            "values (%s,%s,%s,'{}'::jsonb)",
            (tenant, uuid7(), money.routed.connection_id),
        ),
        (
            "insert into gba.provider_event_deliveries "
            "(tenant_id,event_id,delivery_sha256,facts) values (%s,%s,%s,'{}'::jsonb)",
            (tenant, uuid7(), "0" * 64),
        ),
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with tenant_transaction(app_pool, tenant) as conn:
                await conn.execute(statement, values)
    # The writer, the only production caller, still records and the worker decides.
    assert len(await money.observe(event("payment_intent.succeeded"))) == 1
    await money.operation()


# 12 -----------------------------------------------------------------------


async def test_a_partial_capture_applies_only_the_captured_amount(money: Money) -> None:
    obligation, settlement = await money.reserved("6.00")
    await money.observe(
        event("payment_intent.succeeded", amount=1000, amount_received=600),
        event("charge.succeeded", object_id="ch_FAKEcharge1", amount=1000, amount_captured=600),
    )
    applied = await money.apply(settlement, await money.operation(), [(obligation, "6.00")])
    assert applied.status_code == 200, applied.text
    assert (await money.world.balance(obligation))["paid"] == "6.00"


# 15 -----------------------------------------------------------------------


async def test_database_functions_call_only_the_catalog_abs(
    owner_conn: psycopg.Connection,
) -> None:
    rows = owner_conn.execute(
        "select p.proname, p.prosrc from pg_catalog.pg_proc p "
        "where p.pronamespace='gba'::regnamespace"
    ).fetchall()
    assert rows
    assert [name for name, source in rows if re.search(r"(?<![\w.])abs\s*\(", source)] == []
