"""FIN-01 against real PostgreSQL; finance readiness override is TEST ONLY.

The production registry remains implemented until exact-SHA CI acceptance.
"""

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest
from psycopg import sql

from gorgona_booking.business import ledger, modules
from gorgona_booking.business.ledger_contracts import BookInput
from gorgona_booking.business.readiness_registry import Readiness
from gorgona_booking.db.pool import RuntimePool, set_tenant_context, tenant_transaction
from gorgona_booking.db.provisioning import (
    add_membership,
    grant_platform_admin,
    owner_tenant_transaction,
)
from tests.integration import test_management_api as shared
from tests.integration.booking_support import BookingWorld
from tests.integration.configuration_support import Config
from tests.integration.ledger_support import allow_finance_in_test
from tests.integration.seed import FakeUser, seed_user
from tests.integration.test_delegations import Parties
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
manager_b = shared.manager_b


@dataclass(frozen=True)
class LedgerWorld:
    client: httpx.AsyncClient
    business: UUID
    book: UUID
    user: FakeUser
    auth: dict[str, str]
    accounts: tuple[UUID, UUID]

    @property
    def base(self) -> str:
        return f"/v1/businesses/{self.business}/ledger/books/{self.book}"

    def headers(self, key: str | None = None) -> dict[str, str]:
        return {**self.auth, "Idempotency-Key": key or str(uuid7())}

    async def post(
        self, body: Mapping[str, object], *, entry: UUID | None = None, key: str | None = None
    ) -> httpx.Response:
        return await self.client.put(
            f"{self.base}/entries/{entry or uuid7()}", json=dict(body), headers=self.headers(key)
        )

    def entry(self, **changes: object) -> dict[str, object]:
        return {
            "schema_version": 1,
            "entry_date": "2026-10-01",
            "currency": "USD",
            "lines": [
                {"account_id": str(self.accounts[0]), "side": "debit", "amount": "12.30"},
                {"account_id": str(self.accounts[1]), "side": "credit", "amount": "12.30"},
            ],
            **changes,
        }


@pytest.fixture
async def enabled(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager_a: FakeUser,
    idp: FakeIdp,
    app_pool: RuntimePool,
    monkeypatch: pytest.MonkeyPatch,
) -> LedgerWorld:
    # Tests prove the implementation before its independent CI readiness promotion.
    allow_finance_in_test(monkeypatch)
    config = Config(client, idp)
    await config.profile(manager_a, world.a.tenant_id, 0, [1])
    await config.publish(manager_a, world.a.tenant_id, 0, ["booking_resources", "finance"])
    entity = uuid7()
    auth = config.auth(manager_a)
    response = await client.put(
        f"/v1/businesses/{world.a.tenant_id}/legal-entities/{entity}",
        json={"expected_revision": 0, "code": "FAKE", "legal_name": "FAKE Ledger LLC"},
        headers=config.headers(manager_a),
    )
    assert response.status_code == 200, response.text
    book = uuid7()
    async with tenant_transaction(app_pool, world.a.tenant_id) as conn:
        await ledger.save_book(
            conn,
            business_id=world.a.tenant_id,
            book_id=book,
            user_id=manager_a.user_id,
            actor=f"user:{manager_a.user_id}",
            key=str(uuid7()),
            body=BookInput(
                expected_revision=0,
                legal_entity_id=entity,
                base_currency="USD",
                fiscal_year_start_month=1,
                accounting_start=date(2026, 1, 1),
            ),
        )
        accounts = await ledger.list_accounts(conn, world.a.tenant_id, book, after=None, limit=100)
    return LedgerWorld(
        client,
        world.a.tenant_id,
        book,
        manager_a,
        auth,
        (accounts.items[0].account_id, accounts.items[-1].account_id),
    )


async def test_ledger_api_is_connected(enabled: LedgerWorld) -> None:
    response = await enabled.client.get(enabled.base, headers=enabled.auth)
    assert response.status_code == 200, response.text
    assert response.json()["book_id"] == str(enabled.book)
    posted = await enabled.post(enabled.entry())
    assert posted.status_code == 200, posted.text
    assert posted.json()["total"] == "12.30"


async def test_sql_cannot_append_an_unbalanced_line_after_early_balance_check(
    enabled: LedgerWorld,
    app_pool: RuntimePool,
) -> None:
    entry = uuid7()
    with pytest.raises(psycopg.errors.CheckViolation):  # noqa: PT012 - deferred check at transaction exit
        async with tenant_transaction(app_pool, enabled.business) as conn:
            await conn.execute(
                "insert into gba.journal_entries "
                "(tenant_id, id, book_id, entry_date, currency, source_kind, "
                "source_id, created_by) "
                "values (%s,%s,%s,'2026-10-01','USD','manual',%s,%s)",
                (enabled.business, entry, enabled.book, str(entry), enabled.user.user_id),
            )
            for number, side, account in zip(
                (1, 2), ("debit", "credit"), enabled.accounts, strict=True
            ):
                await conn.execute(
                    "insert into gba.journal_lines "
                    "(tenant_id,entry_id,line_no,book_id,account_id,side,amount_minor) "
                    "values (%s,%s,%s,%s,%s,%s,100)",
                    (enabled.business, entry, number, enabled.book, account, side),
                )
            await conn.execute("set constraints gba.journal_entries_balanced immediate")
            await conn.execute("set constraints gba.journal_entries_balanced deferred")
            await conn.execute(
                "insert into gba.journal_lines "
                "(tenant_id,entry_id,line_no,book_id,account_id,side,amount_minor) "
                "values (%s,%s,3,%s,%s,'debit',1)",
                (enabled.business, entry, enabled.book, enabled.accounts[0]),
            )


async def test_replay_operation_uniqueness_reversal_and_currency_reports(
    enabled: LedgerWorld,
) -> None:
    entry, key = uuid7(), str(uuid7())
    body = enabled.entry(source_id="FAKE-operation-1", memo="FAKE private memo")
    original = await enabled.post(body, entry=entry, key=key)
    assert original.status_code == 200, original.text
    replay = await enabled.post(body, entry=entry, key=key)
    assert replay.json() == original.json()
    duplicate = await enabled.post(body)
    assert (duplicate.status_code, duplicate.json()["error"]["code"]) == (
        409,
        "LEDGER_OPERATION_POSTED",
    )
    different = await enabled.post(enabled.entry(source_id="different"), entry=entry, key=key)
    assert different.status_code == 422
    for currency, amount in [("JPY", "100"), ("KWD", "0.001")]:
        response = await enabled.post(
            enabled.entry(
                currency=currency,
                lines=[
                    {"account_id": str(a), "side": side, "amount": amount}
                    for a, side in zip(enabled.accounts, ("debit", "credit"), strict=True)
                ],
            )
        )
        assert response.status_code == 200, response.text
    report = await enabled.client.get(
        f"{enabled.base}/trial-balance",
        headers=enabled.auth,
        params={"period_from": "2026-10", "period_to": "2026-10", "currency": "USD"},
    )
    assert report.status_code == 200, report.text
    assert report.json()["totals"]["debit"] == report.json()["totals"]["credit"] == "12.30"
    assert report.json()["currencies"] == ["JPY", "KWD", "USD"]
    reversal_id = uuid7()
    reversed_entry = await enabled.client.post(
        f"{enabled.base}/entries/{entry}/reverse",
        json={"entry_date": "2026-10-02", "reversal_entry_id": str(reversal_id)},
        headers=enabled.headers(),
    )
    assert reversed_entry.status_code == 200, reversed_entry.text
    second = await enabled.client.post(
        f"{enabled.base}/entries/{entry}/reverse",
        json={"entry_date": "2026-10-02", "reversal_entry_id": str(uuid7())},
        headers=enabled.headers(),
    )
    assert (second.status_code, second.json()["error"]["code"]) == (409, "LEDGER_ENTRY_REVERSED")
    after = await enabled.client.get(
        f"{enabled.base}/trial-balance",
        headers=enabled.auth,
        params={"period_from": "2026-10", "period_to": "2026-10"},
    )
    assert (
        after.json()["totals"]["closing_debit"]
        == after.json()["totals"]["closing_credit"]
        == "0.00"
    )
    saved = await enabled.client.get(f"{enabled.base}/entries/{entry}", headers=enabled.auth)
    assert saved.json()["lines"] == original.json()["lines"]
    assert saved.json()["reversed_by_entry_id"] == str(reversal_id)


async def test_period_close_reopen_and_reading_while_module_disabled(enabled: LedgerWorld) -> None:
    response = await enabled.client.post(
        f"{enabled.base}/periods/2026-10/close",
        json={"expected_sequence": 0},
        headers=enabled.headers(),
    )
    assert response.status_code == 200, response.text
    refused = await enabled.post(enabled.entry())
    assert (refused.status_code, refused.json()["error"]["code"]) == (409, "LEDGER_PERIOD_CLOSED")
    stale = await enabled.client.post(
        f"{enabled.base}/periods/2026-10/reopen",
        json={"expected_sequence": 2, "reason": "FAKE correction"},
        headers=enabled.headers(),
    )
    assert stale.status_code == 409
    reopened = await enabled.client.post(
        f"{enabled.base}/periods/2026-10/reopen",
        json={"expected_sequence": 1, "reason": "FAKE correction"},
        headers=enabled.headers(),
    )
    assert reopened.status_code == 200, reopened.text
    assert [e["action"] for e in reopened.json()["events"]] == ["reopened", "closed"]
    assert (await enabled.post(enabled.entry())).status_code == 200


@pytest.mark.parametrize("role", ["artist", "front_desk", "branch_manager", "outsider", "support"])
async def test_unauthorized_roles_cannot_read_or_write_finance(
    enabled: LedgerWorld,
    owner_conn: psycopg.Connection,
    world: BookingWorld,
    idp: FakeIdp,
    role: str,
) -> None:
    user = seed_user(owner_conn, f"ledger-denied-{uuid7()}")
    if role == "support":
        grant_platform_admin(owner_conn, user_id=user.user_id, granted_by="FAKE test operator")
    elif role != "outsider":
        add_membership(
            owner_conn,
            tenant_id=enabled.business,
            user_id=user.user_id,
            role="manager" if role == "branch_manager" else role,
            location_id=world.a.location_id if role == "branch_manager" else None,
        )
    auth = idp.bearer(user.subject, email=user.email)
    for response in (
        await enabled.client.get(enabled.base, headers=auth),
        await enabled.client.put(
            f"{enabled.base}/entries/{uuid7()}",
            json=enabled.entry(),
            headers={**auth, "Idempotency-Key": str(uuid7())},
        ),
        await enabled.client.post(
            f"{enabled.base}/periods/2026-10/close",
            json={"expected_sequence": 0},
            headers={**auth, "Idempotency-Key": str(uuid7())},
        ),
    ):
        assert response.status_code == 403, response.text


async def test_race_post_close_is_ordered(enabled: LedgerWorld) -> None:
    posted, closed = await asyncio.gather(
        enabled.post(enabled.entry()),
        enabled.client.post(
            f"{enabled.base}/periods/2026-10/close",
            json={"expected_sequence": 0},
            headers=enabled.headers(),
        ),
    )
    assert closed.status_code == 200, closed.text
    assert posted.status_code in (200, 409), posted.text
    if posted.status_code == 409:
        assert posted.json()["error"]["code"] == "LEDGER_PERIOD_CLOSED"
    assert (await enabled.post(enabled.entry())).status_code == 409


@pytest.mark.parametrize(
    ("table", "trigger"),
    [
        ("journal_entries", "journal_entries_balanced"),
        ("journal_lines", "journal_lines_balanced"),
        ("journal_entries", "journal_entries_check"),
        ("ledger_period_events", "ledger_period_events_next"),
        ("ledger_accounts", "ledger_accounts_immutable"),
        ("ledger_books", "ledger_books_require_module"),
    ],
)
async def test_damaged_finance_protection_fails_closed(
    enabled: LedgerWorld, owner_conn: psycopg.Connection, table: str, trigger: str
) -> None:
    statement = sql.SQL("alter table gba.{} {} trigger {}")
    owner_conn.execute(
        statement.format(sql.Identifier(table), sql.SQL("disable"), sql.Identifier(trigger))
    )
    try:
        response = await enabled.client.get(enabled.base, headers=enabled.auth)
        assert response.status_code == 503, response.text
    finally:
        owner_conn.execute(
            statement.format(sql.Identifier(table), sql.SQL("enable"), sql.Identifier(trigger))
        )


@pytest.mark.parametrize("delta", [0, 1])
async def test_sql_rejects_empty_or_unbalanced_entries(
    enabled: LedgerWorld, app_pool: RuntimePool, delta: int
) -> None:
    with pytest.raises(psycopg.errors.CheckViolation):  # noqa: PT012 - deferred check at transaction exit
        async with tenant_transaction(app_pool, enabled.business) as conn:
            entry = uuid7()
            await conn.execute(
                "insert into gba.journal_entries "
                "(tenant_id,id,book_id,entry_date,currency,source_kind,source_id,created_by) "
                "values (%s,%s,%s,'2026-10-01','USD','manual',%s,%s)",
                (enabled.business, entry, enabled.book, str(entry), enabled.user.user_id),
            )
            if delta:
                await conn.execute(
                    "insert into gba.journal_lines "
                    "(tenant_id,entry_id,line_no,book_id,account_id,side,amount_minor) "
                    "values (%s,%s,1,%s,%s,'debit',1)",
                    (enabled.business, entry, enabled.book, enabled.accounts[0]),
                )


async def test_history_is_immutable_and_cross_tenant_rows_invisible(
    enabled: LedgerWorld, owner_conn: psycopg.Connection, app_pool: RuntimePool, world: BookingWorld
) -> None:
    assert (await enabled.post(enabled.entry())).status_code == 200
    with (
        owner_tenant_transaction(owner_conn, enabled.business),
        pytest.raises(psycopg.errors.CheckViolation),
        owner_conn.transaction(),
    ):
        owner_conn.execute(
            "delete from gba.journal_entries where tenant_id=%s", (enabled.business,)
        )
    async with tenant_transaction(app_pool, world.b.tenant_id) as conn:
        for table in (
            "ledger_books",
            "ledger_book_versions",
            "ledger_accounts",
            "ledger_account_versions",
            "journal_entries",
            "journal_lines",
            "ledger_period_events",
        ):
            rows = await (
                await conn.execute(
                    sql.SQL("select * from gba.{} where tenant_id=%s").format(
                        sql.Identifier(table)
                    ),
                    (enabled.business,),
                )
            ).fetchall()
            assert rows == []


async def test_production_registry_does_not_enable_unaccepted_finance(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager_a: FakeUser,
    idp: FakeIdp,
) -> None:
    assert modules.MODULES_BY_ID["finance"].readiness == Readiness.IMPLEMENTED
    assert not modules.MODULES_BY_ID["finance"].enableable
    config = Config(client, idp)
    await config.profile(manager_a, world.a.tenant_id, 0, [1])
    drafted = await config.draft(manager_a, world.a.tenant_id, 0, ["finance"])
    assert drafted.status_code == 200, drafted.text
    refused = await config.step(manager_a, world.a.tenant_id, 1, "validate", 1)
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"]["details"]["problems"][0]["code"] == "MODULE_NOT_READY"
    response = await client.put(
        f"/v1/businesses/{world.a.tenant_id}/ledger/books/{uuid7()}",
        json={
            "expected_revision": 0,
            "legal_entity_id": str(uuid7()),
            "base_currency": "USD",
            "fiscal_year_start_month": 1,
            "accounting_start": "2026-01-01",
        },
        headers=config.headers(manager_a),
    )
    assert (response.status_code, response.json()["error"]["code"]) == (409, "MODULE_DISABLED")


async def test_books_and_entities_do_not_share_accounts_or_operations(enabled: LedgerWorld) -> None:
    entity, book = uuid7(), uuid7()
    business_base = f"/v1/businesses/{enabled.business}"
    response = await enabled.client.put(
        f"{business_base}/legal-entities/{entity}",
        json={"expected_revision": 0, "code": "FAKE_OTHER", "legal_name": "FAKE Other LLC"},
        headers=enabled.headers(),
    )
    assert response.status_code == 200, response.text
    settings = {
        "expected_revision": 0,
        "legal_entity_id": str(entity),
        "base_currency": "JPY",
        "fiscal_year_start_month": 4,
        "accounting_start": "2026-01-01",
    }
    saved = await enabled.client.put(
        f"{business_base}/ledger/books/{book}", json=settings, headers=enabled.headers()
    )
    assert saved.status_code == 200, saved.text
    duplicate = await enabled.client.put(
        f"{business_base}/ledger/books/{uuid7()}", json=settings, headers=enabled.headers()
    )
    assert duplicate.status_code == 409
    accounts = (
        await enabled.client.get(
            f"{business_base}/ledger/books/{book}/accounts", headers=enabled.auth
        )
    ).json()["items"]
    crossed = await enabled.post(
        enabled.entry(
            lines=[
                {"account_id": str(enabled.accounts[0]), "side": "debit", "amount": "1.00"},
                {"account_id": accounts[0]["account_id"], "side": "credit", "amount": "1.00"},
            ]
        )
    )
    assert crossed.status_code == 422, crossed.text
    posted = await enabled.post(enabled.entry(source_id="FAKE-shared-operation"))
    assert posted.status_code == 200, posted.text
    other_body = enabled.entry(
        source_id="FAKE-shared-operation",
        currency="JPY",
        lines=[
            {"account_id": a["account_id"], "side": side, "amount": "1"}
            for a, side in zip((accounts[0], accounts[-1]), ("debit", "credit"), strict=True)
        ],
    )
    other = await enabled.client.put(
        f"{business_base}/ledger/books/{book}/entries/{uuid7()}",
        json=other_body,
        headers=enabled.headers(),
    )
    assert other.status_code == 200, other.text
    report = await enabled.client.get(
        f"{business_base}/ledger/books/{book}/trial-balance",
        params={"period_from": "2026-10", "period_to": "2026-10"},
        headers=enabled.auth,
    )
    assert report.json()["totals"]["debit"] == report.json()["totals"]["credit"] == "1"
    updated = await enabled.client.put(
        f"{enabled.base}",
        json={
            **settings,
            "expected_revision": 1,
            "legal_entity_id": saved.json()["legal_entity_id"],
        },
        headers=enabled.headers(),
    )
    assert updated.status_code == 422


async def test_disabled_finance_keeps_reports_and_history_readable(
    enabled: LedgerWorld, idp: FakeIdp
) -> None:
    assert (await enabled.post(enabled.entry())).status_code == 200
    config = Config(enabled.client, idp)
    await config.publish(enabled.user, enabled.business, 1, ["booking_resources"])
    assert (await enabled.post(enabled.entry())).status_code == 409
    for suffix, params in [
        ("/entries", {}),
        ("/accounts", {}),
        ("/periods/2026-10", {}),
        ("/trial-balance", {"period_from": "2026-10", "period_to": "2026-10"}),
    ]:
        response = await enabled.client.get(
            enabled.base + suffix, headers=enabled.auth, params=params
        )
        assert response.status_code == 200, response.text


async def test_active_booking_delegation_never_grants_finance(
    enabled: LedgerWorld, owner_conn: psycopg.Connection, world: BookingWorld, idp: FakeIdp
) -> None:
    owner_a = seed_user(owner_conn, f"FAKE-ledger-owner-{uuid7()}")
    owner_b = seed_user(owner_conn, f"FAKE-ledger-servicer-{uuid7()}")
    add_membership(owner_conn, tenant_id=enabled.business, user_id=owner_a.user_id, role="owner")
    add_membership(owner_conn, tenant_id=world.b.tenant_id, user_id=owner_b.user_id, role="owner")
    parties = Parties(enabled.client, idp, world)
    await parties.active_grant(owner_a, owner_b, [owner_b])
    auth = idp.bearer(owner_b.subject, email=owner_b.email)
    assert (await enabled.client.get(enabled.base, headers=auth)).status_code == 403


async def test_tenant_policy_tampering_fails_readiness(
    enabled: LedgerWorld, owner_conn: psycopg.Connection
) -> None:
    owner_conn.execute(
        "alter policy journal_entries_tenant_isolation on gba.journal_entries "
        "using (true) with check (true)"
    )
    try:
        response = await enabled.client.get(enabled.base, headers=enabled.auth)
        assert response.status_code == 503, response.text
    finally:
        owner_conn.execute(
            "alter policy journal_entries_tenant_isolation on gba.journal_entries "
            "using (tenant_id=gba.current_tenant_id()) "
            "with check (tenant_id=gba.current_tenant_id())"
        )


@pytest.mark.parametrize("first_action", ["post", "close"])
async def test_raw_sql_close_and_post_share_one_lock_and_fresh_snapshot(
    enabled: LedgerWorld,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
    first_action: str,
) -> None:
    held, release = asyncio.Event(), asyncio.Event()
    entry = uuid7()

    async def act(action: str, first: bool) -> str:
        try:
            async with tenant_transaction(app_pool, enabled.business) as conn:
                if first:
                    await conn.execute("select gba.lock_ledger(%s)", (enabled.business,))
                if action == "close":
                    await conn.execute(
                        "insert into gba.ledger_period_events "
                        "(tenant_id,book_id,period,sequence,action,decided_by) "
                        "values (%s,%s,'2026-10-01',1,'closed',%s)",
                        (enabled.business, enabled.book, enabled.user.user_id),
                    )
                else:
                    await conn.execute(
                        "insert into gba.journal_entries "
                        "(tenant_id,id,book_id,entry_date,currency,source_kind,"
                        "source_id,created_by) "
                        "values (%s,%s,%s,'2026-10-01','USD','manual',%s,%s)",
                        (enabled.business, entry, enabled.book, str(entry), enabled.user.user_id),
                    )
                    for i, side, account in zip(
                        (1, 2), ("debit", "credit"), enabled.accounts, strict=True
                    ):
                        await conn.execute(
                            "insert into gba.journal_lines "
                            "(tenant_id,entry_id,line_no,book_id,account_id,side,amount_minor) "
                            "values (%s,%s,%s,%s,%s,%s,100)",
                            (enabled.business, entry, i, enabled.book, account, side),
                        )
                if first:
                    held.set()
                    await release.wait()
            return "saved"
        except psycopg.errors.CheckViolation as exc:
            return "closed" if "closed" in str(exc) else str(exc)

    leading = asyncio.create_task(act(first_action, True))
    await asyncio.wait_for(held.wait(), timeout=5)
    following = asyncio.create_task(act("close" if first_action == "post" else "post", False))
    try:
        # Observe the second raw statement actually waiting on PostgreSQL's lock.
        for _ in range(100):
            await asyncio.sleep(0.01)
            row = owner_conn.execute(
                "select count(*) from pg_catalog.pg_locks where locktype='advisory' and not granted"
            ).fetchone()
            if row and row[0] > 0:
                break
        else:
            pytest.fail("The second statement did not wait on the ledger lock")
    finally:
        release.set()
    result = await asyncio.gather(leading, following)
    assert tuple(result) == (("saved", "closed") if first_action == "close" else ("saved", "saved"))
    async with tenant_transaction(app_pool, enabled.business) as conn:
        count = await (
            await conn.execute(
                "select count(*) from gba.journal_entries where book_id=%s", (enabled.book,)
            )
        ).fetchone()
        assert count == (0 if first_action == "close" else 1,)


async def test_sql_cannot_change_the_original_after_checking_its_reversal(
    enabled: LedgerWorld,
    app_pool: RuntimePool,
) -> None:
    original, reversal = uuid7(), uuid7()
    with pytest.raises(psycopg.errors.CheckViolation):  # noqa: PT012 - SQL invariant at commit/insert
        async with tenant_transaction(app_pool, enabled.business) as conn:
            for entry, reverses, source in [
                (original, None, "manual"),
                (reversal, original, "reversal"),
            ]:
                await conn.execute(
                    "insert into gba.journal_entries "
                    "(tenant_id,id,book_id,entry_date,currency,source_kind,source_id,"
                    "reverses_entry_id,created_by) "
                    "values (%s,%s,%s,'2026-10-01','USD',%s,%s,%s,%s)",
                    (
                        enabled.business,
                        entry,
                        enabled.book,
                        source,
                        str(entry),
                        reverses,
                        enabled.user.user_id,
                    ),
                )
                sides = ("debit", "credit") if reverses is None else ("credit", "debit")
                for i, side, account in zip((1, 2), sides, enabled.accounts, strict=True):
                    await conn.execute(
                        "insert into gba.journal_lines "
                        "(tenant_id,entry_id,line_no,book_id,account_id,side,amount_minor) "
                        "values (%s,%s,%s,%s,%s,%s,100)",
                        (enabled.business, entry, i, enabled.book, account, side),
                    )
            await conn.execute(
                "set constraints gba.journal_entries_balanced, gba.journal_lines_balanced immediate"
            )
            await conn.execute(
                "set constraints gba.journal_entries_balanced, gba.journal_lines_balanced deferred"
            )
            for i, side, account in zip((3, 4), ("debit", "credit"), enabled.accounts, strict=True):
                await conn.execute(
                    "insert into gba.journal_lines "
                    "(tenant_id,entry_id,line_no,book_id,account_id,side,amount_minor) "
                    "values (%s,%s,%s,%s,%s,%s,1)",
                    (enabled.business, original, i, enabled.book, account, side),
                )


async def test_old_snapshot_cannot_post_after_period_was_closed(
    enabled: LedgerWorld,
    app_pool: RuntimePool,
) -> None:
    with pytest.raises(psycopg.errors.SerializationFailure):  # noqa: PT012 - transaction-level invariant
        async with app_pool.connection() as conn, conn.transaction():
            await conn.execute("set transaction isolation level repeatable read")
            await set_tenant_context(conn, enabled.business)
            result = await (
                await conn.execute(
                    "select gba.ledger_period_closed(%s,%s,'2026-10-01')",
                    (enabled.business, enabled.book),
                )
            ).fetchone()
            assert result == (False,)
            closed = await enabled.client.post(
                f"{enabled.base}/periods/2026-10/close",
                json={"expected_sequence": 0},
                headers=enabled.headers(),
            )
            assert closed.status_code == 200, closed.text
            entry = uuid7()
            await conn.execute(
                "insert into gba.journal_entries "
                "(tenant_id,id,book_id,entry_date,currency,source_kind,source_id,created_by) "
                "values (%s,%s,%s,'2026-10-01','USD','manual',%s,%s)",
                (enabled.business, entry, enabled.book, str(entry), enabled.user.user_id),
            )
            for i, side, account in zip((1, 2), ("debit", "credit"), enabled.accounts, strict=True):
                await conn.execute(
                    "insert into gba.journal_lines "
                    "(tenant_id,entry_id,line_no,book_id,account_id,side,amount_minor) "
                    "values (%s,%s,%s,%s,%s,%s,100)",
                    (enabled.business, entry, i, enabled.book, account, side),
                )


@pytest.mark.parametrize(
    ("function", "before", "after"),
    [
        ("gba.ledger_period_closed(uuid,uuid,date)", "e.action = 'closed'", "e.action = 'closed '"),
        (
            "gba.require_enabled_module()",
            "'gba:business-configuration:'",
            "'gba:business- configuration:'",
        ),
    ],
)
async def test_meaningful_sql_literal_whitespace_is_not_ignored(
    enabled: LedgerWorld,
    owner_conn: psycopg.Connection,
    function: str,
    before: str,
    after: str,
) -> None:
    row = owner_conn.execute(
        "select pg_catalog.pg_get_functiondef(%s::regprocedure)",
        (function,),
    ).fetchone()
    assert row is not None
    original = str(row[0])
    modified = original.replace(before, after)
    assert modified != original
    owner_conn.execute(modified)
    try:
        response = await enabled.client.get(enabled.base, headers=enabled.auth)
        assert response.status_code == 503, response.text
    finally:
        owner_conn.execute(original)


def recovery_reference(enabled: LedgerWorld, entry: UUID) -> dict[str, object]:
    return {
        "schema_version": 1,
        "operation": "entry",
        "book_id": str(enabled.book),
        "subject_id": str(entry),
        "revision": None,
        "period": None,
        "sequence": None,
    }


async def recovery_call(
    enabled: LedgerWorld, key: str, body: dict[str, object], action: str = "resolve"
) -> httpx.Response:
    return await enabled.client.post(
        f"/v1/businesses/{enabled.business}/ledger/commands/{key}/{action}",
        json=body,
        headers=enabled.auth,
    )


async def test_recovery_seals_unreceived_request_and_refuses_delayed_original(
    enabled: LedgerWorld,
) -> None:
    entry, key = uuid7(), str(uuid7())
    reference = recovery_reference(enabled, entry)
    unknown = await recovery_call(enabled, key, reference)
    assert unknown.status_code == 200, unknown.text
    assert unknown.json()["state"] == "unresolved"
    sealed = await recovery_call(enabled, key, reference, "cancel")
    assert sealed.status_code == 200, sealed.text
    assert sealed.json()["state"] == "cancelled"
    duplicate = await recovery_call(enabled, key, reference, "cancel")
    assert duplicate.json() == sealed.json()
    delayed = await enabled.post(enabled.entry(), entry=entry, key=key)
    assert (delayed.status_code, delayed.json()["error"]["code"]) == (
        409,
        "LEDGER_COMMAND_CANCELLED",
    )


async def test_recovery_never_cancels_a_committed_entry_even_after_receipt_expiry(
    enabled: LedgerWorld,
    owner_conn: psycopg.Connection,
) -> None:
    entry, key = uuid7(), str(uuid7())
    assert (await enabled.post(enabled.entry(), entry=entry, key=key)).status_code == 200
    reference = recovery_reference(enabled, entry)
    for step in range(2):
        crossed = await recovery_call(enabled, key, {**reference, "book_id": str(uuid7())})
        assert crossed.status_code == 422, crossed.text
        if step:
            with owner_tenant_transaction(owner_conn, enabled.business):
                owner_conn.execute(
                    "delete from gba.idempotency_keys where tenant_id=%s and idempotency_key=%s",
                    (enabled.business, key),
                )
        result = await recovery_call(enabled, key, reference, "cancel")
        assert result.status_code == 200, result.text
        assert result.json()["state"] == "committed"
    with owner_tenant_transaction(owner_conn, enabled.business):
        assert owner_conn.execute(
            "select count(*) from gba.ledger_command_cancellations"
        ).fetchone() == (0,)
        assert owner_conn.execute("select count(*) from gba.journal_entries").fetchone() == (1,)


async def test_post_and_cancel_recovery_have_one_consistent_order(enabled: LedgerWorld) -> None:
    entry, key = uuid7(), str(uuid7())
    posted, cancelled = await asyncio.gather(
        enabled.post(enabled.entry(), entry=entry, key=key),
        recovery_call(enabled, key, recovery_reference(enabled, entry), "cancel"),
    )
    assert cancelled.status_code == 200, cancelled.text
    if cancelled.json()["state"] == "committed":
        assert posted.status_code == 200, posted.text
    else:
        assert cancelled.json()["state"] == "cancelled"
        assert (posted.status_code, posted.json()["error"]["code"]) == (
            409,
            "LEDGER_COMMAND_CANCELLED",
        )


async def test_recovery_is_scoped_to_actor_and_continues_when_module_is_off(
    enabled: LedgerWorld,
    owner_conn: psycopg.Connection,
    idp: FakeIdp,
) -> None:
    user = seed_user(owner_conn, f"FAKE-recovery-other-{uuid7()}")
    add_membership(owner_conn, tenant_id=enabled.business, user_id=user.user_id, role="manager")
    entry, key = uuid7(), str(uuid7())
    assert (await enabled.post(enabled.entry(), entry=entry, key=key)).status_code == 200
    other = LedgerWorld(
        enabled.client,
        enabled.business,
        enabled.book,
        user,
        idp.bearer(user.subject, email=user.email),
        enabled.accounts,
    )
    result = await recovery_call(other, key, recovery_reference(other, entry), "cancel")
    assert result.json()["state"] == "cancelled"
    original = await enabled.post(enabled.entry(), entry=entry, key=key)
    assert original.status_code == 200, original.text
    config = Config(enabled.client, idp)
    await config.publish(enabled.user, enabled.business, 1, ["booking_resources"])
    unknown = await recovery_call(
        enabled, str(uuid7()), recovery_reference(enabled, uuid7()), "cancel"
    )
    assert unknown.status_code == 200, unknown.text
    assert unknown.json()["state"] == "cancelled"
