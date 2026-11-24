"""OPS-01 integration drill against real PostgreSQL 18:
1. Seed multi-currency double-entry ledger entries (USD + EUR) and counterparties.
2. Execute real pg_dump -> pg_restore into a fresh PG18 database and measure RTO.
3. Reconcile all 148 migration checksums, all gba.* table counts, and balanced ledgers.
4. Verify schema_guard & location_scope_ready under gba_runtime on the restored DB.
5. Replay previously committed idempotent mutations on the restored DB -> zero double-posting.
6. Verify reverse switchback back to the source DB with clean post-switchback writes.
"""

import secrets
from datetime import date
from uuid import uuid7

import httpx
import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo
from tools.ops_recovery_drill import (
    capture_reconciliation_snapshot,
    reconcile_snapshots,
    verify_pg_dump_restore,
)

from gorgona_booking.business import ledger
from gorgona_booking.business.ledger_contracts import BookInput, EntryInput, LineInput
from gorgona_booking.db.migrate import apply_migrations, load_migrations
from gorgona_booking.db.pool import RuntimePool, create_runtime_pool, tenant_transaction
from gorgona_booking.db.schema_guard import assert_location_scope_ready
from tests.integration import test_management_api as shared
from tests.integration.booking_support import BookingWorld
from tests.integration.configuration_support import Config
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.seed import FakeUser
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a


async def test_ops01_pg_dump_restore_reconciliation_replay_and_switchback(
    client: httpx.AsyncClient,
    idp: FakeIdp,
    world: BookingWorld,
    manager_a: FakeUser,
    app_pool: RuntimePool,
    test_database: ProvisionedDatabase,
) -> None:
    tenant_id = world.a.tenant_id
    cfg = Config(client, idp)
    await cfg.profile(manager_a, tenant_id, 0, [1, 25])
    await cfg.publish(manager_a, tenant_id, 0, ["booking_resources", "finance"])

    le_id = uuid7()
    res_le = await client.put(
        f"/v1/businesses/{tenant_id}/legal-entities/{le_id}",
        json={"expected_revision": 0, "code": "OPS01", "legal_name": "FAKE OPS01 Recovery LLC"},
        headers=cfg.headers(manager_a),
    )
    assert res_le.status_code == 200, res_le.text

    book_id = uuid7()
    usd_entry_id = uuid7()
    eur_entry_id = uuid7()
    usd_key = f"ops01-usd-{uuid7()}"
    eur_key = f"ops01-eur-{uuid7()}"

    async with tenant_transaction(app_pool, tenant_id) as conn:
        await ledger.save_book(
            conn,
            business_id=tenant_id,
            book_id=book_id,
            user_id=manager_a.user_id,
            actor=f"user:{manager_a.user_id}",
            key=f"ops01-book-{uuid7()}",
            body=BookInput(
                expected_revision=0,
                legal_entity_id=le_id,
                base_currency="USD",
                fiscal_year_start_month=1,
                accounting_start=date(2026, 1, 1),
            ),
        )
        accounts = await ledger.list_accounts(conn, tenant_id, book_id, after=None, limit=100)
        debit_acc, credit_acc = accounts.items[0].account_id, accounts.items[-1].account_id
        usd_body = EntryInput(
            entry_date=date(2026, 10, 15),
            currency="USD",
            lines=(
                LineInput(account_id=debit_acc, side="debit", amount="150.00"),
                LineInput(account_id=credit_acc, side="credit", amount="150.00"),
            ),
        )
        eur_body = EntryInput(
            entry_date=date(2026, 10, 15),
            currency="EUR",
            lines=(
                LineInput(account_id=debit_acc, side="debit", amount="80.50"),
                LineInput(account_id=credit_acc, side="credit", amount="80.50"),
            ),
        )
        posted_usd = await ledger.post_entry(
            conn,
            business_id=tenant_id,
            book_id=book_id,
            entry_id=usd_entry_id,
            user_id=manager_a.user_id,
            actor=f"user:{manager_a.user_id}",
            key=usd_key,
            body=usd_body,
        )
        posted_eur = await ledger.post_entry(
            conn,
            business_id=tenant_id,
            book_id=book_id,
            entry_id=eur_entry_id,
            user_id=manager_a.user_id,
            actor=f"user:{manager_a.user_id}",
            key=eur_key,
            body=eur_body,
        )

    # 1. Execute real pg_dump -> pg_restore into a clean PG18 database & reconcile
    target_db = f"gba_ops01_restore_{secrets.token_hex(4)}"
    target_owner_dsn = make_conninfo(test_database.owner_dsn, dbname=target_db)
    target_app_dsn = make_conninfo(test_database.app_dsn, dbname=target_db)
    try:
        drill = verify_pg_dump_restore(
            admin_dsn=test_database.admin_dsn,
            source_database=test_database.name,
            source_owner_dsn=test_database.owner_dsn,
            target_database=target_db,
        )
        assert drill.dump_bytes > 0
        assert drill.dump_seconds >= 0
        assert drill.restore_seconds >= 0
        assert drill.reconciliation.matched is True, drill.reconciliation
        assert drill.reconciliation.unbalanced_ledgers == ()

        # 2. Restored DB has all 148 migrations applied cleanly (apply_migrations is a no-op)
        assert apply_migrations(target_owner_dsn) == []

        # 3. Verify runtime schema_guard & location_scope_ready + idempotent replay on restored DB
        async with (
            create_runtime_pool(target_app_dsn, min_size=1, max_size=2) as restored_pool,
            tenant_transaction(restored_pool, tenant_id) as rconn,
        ):
            await assert_location_scope_ready(rconn)
            replayed_usd = await ledger.post_entry(
                rconn,
                business_id=tenant_id,
                book_id=book_id,
                entry_id=usd_entry_id,
                user_id=manager_a.user_id,
                actor=f"user:{manager_a.user_id}",
                key=usd_key,
                body=usd_body,
            )
            replayed_eur = await ledger.post_entry(
                rconn,
                business_id=tenant_id,
                book_id=book_id,
                entry_id=eur_entry_id,
                user_id=manager_a.user_id,
                actor=f"user:{manager_a.user_id}",
                key=eur_key,
                body=eur_body,
            )
            assert replayed_usd.entry_id == posted_usd.entry_id
            assert replayed_eur.entry_id == posted_eur.entry_id

        # 4. After duplicate replay on restored DB, row counts & balances stay 100% identical
        source_admin_dsn = make_conninfo(test_database.admin_dsn, dbname=test_database.name)
        target_admin_dsn = make_conninfo(test_database.admin_dsn, dbname=target_db)
        src_snap = capture_reconciliation_snapshot(source_admin_dsn)
        dst_snap = capture_reconciliation_snapshot(target_admin_dsn)
        assert src_snap.migration_count == len(load_migrations())
        assert src_snap.table_counts["tenants"] >= 1
        assert src_snap.table_counts["journal_entries"] >= 2
        assert reconcile_snapshots(src_snap, dst_snap).matched is True
        assert any(
            b.currency == "USD" and b.total_debit_minor == 15000 and b.balanced
            for b in dst_snap.ledger_balances
        )
        assert any(
            b.currency == "EUR" and b.total_debit_minor == 8050 and b.balanced
            for b in dst_snap.ledger_balances
        )

        # 5. Reverse switchback: resume writes on source DB without divergence
        async with tenant_transaction(app_pool, tenant_id) as conn:
            await ledger.post_entry(
                conn,
                business_id=tenant_id,
                book_id=book_id,
                entry_id=uuid7(),
                user_id=manager_a.user_id,
                actor=f"user:{manager_a.user_id}",
                key=f"ops01-switchback-{uuid7()}",
                body=EntryInput(
                    entry_date=date(2026, 10, 16),
                    currency="USD",
                    lines=(
                        LineInput(account_id=debit_acc, side="debit", amount="25.00"),
                        LineInput(account_id=credit_acc, side="credit", amount="25.00"),
                    ),
                ),
            )
        after_switchback = capture_reconciliation_snapshot(source_admin_dsn)
        assert (
            after_switchback.table_counts["journal_entries"]
            == src_snap.table_counts["journal_entries"] + 1
        )
        usd_bal = next(
            b
            for b in after_switchback.ledger_balances
            if b.book_id == book_id and b.currency == "USD"
        )
        assert usd_bal.total_debit_minor == 17500
        assert usd_bal.balanced is True
    finally:
        with psycopg.connect(test_database.admin_dsn, autocommit=True) as conn:
            conn.execute(
                sql.SQL("drop database if exists {} with (force)").format(sql.Identifier(target_db))
            )
