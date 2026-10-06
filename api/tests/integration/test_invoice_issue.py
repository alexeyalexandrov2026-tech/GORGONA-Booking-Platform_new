"""H1 invoice persistence against real disposable PostgreSQL and API auth."""

import asyncio
from dataclasses import dataclass
from datetime import date
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest
from psycopg import sql

from gorgona_booking.business import financial_documents, ledger, modules
from gorgona_booking.business.financial_contracts import InvoiceDraftInput, InvoiceIssueInput
from gorgona_booking.business.readiness_registry import Readiness
from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import add_membership, owner_tenant_transaction
from tests.integration import test_ledger as ledger_shared
from tests.integration import test_management_api as shared
from tests.integration.booking_support import BookingWorld
from tests.integration.configuration_support import Config
from tests.integration.seed import FakeUser, seed_user
from tests.integration.test_counterparties import card
from tests.integration.test_ledger import LedgerWorld
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
manager_b = shared.manager_b
enabled = ledger_shared.enabled


@dataclass(frozen=True)
class InvoiceWorld:
    ledger: LedgerWorld
    party: UUID
    control: UUID
    counter: UUID

    @property
    def base(self) -> str:
        return (
            f"/v1/businesses/{self.ledger.business}/financial-documents/"
            f"books/{self.ledger.book}/invoices"
        )

    def draft_body(self, **changes: object) -> dict[str, object]:
        return {
            "schema_version": 1,
            "expected_revision": 0,
            "direction": "receivable",
            "counterparty_id": str(self.party),
            "counterparty_revision": 1,
            "currency": "USD",
            "invoice_date": "2026-10-01",
            "control_account_id": str(self.control),
            "title": "FAKE invoice",
            "number": "FAKE-001",
            "lines": [
                {
                    "line_id": str(uuid7()),
                    "counter_account_id": str(self.counter),
                    "description": "FAKE internal accrual",
                    "amount": "100.00",
                }
            ],
            **changes,
        }

    async def save(
        self,
        *,
        document: UUID | None = None,
        key: str | None = None,
        body: dict[str, object] | None = None,
    ) -> httpx.Response:
        return await self.ledger.client.put(
            f"{self.base}/{document or uuid7()}",
            json=body or self.draft_body(),
            headers=self.ledger.headers(key),
        )

    async def issue(
        self, document: UUID, *, key: str | None = None, **changes: object
    ) -> httpx.Response:
        return await self.ledger.client.post(
            f"{self.base}/{document}/issue",
            json={
                "schema_version": 1,
                "expected_revision": 1,
                "entry_date": "2026-10-01",
                "attestation": "confirmed_account_treatment",
                **changes,
            },
            headers=self.ledger.headers(key),
        )


@pytest.fixture
async def invoices(
    enabled: LedgerWorld, idp: FakeIdp, monkeypatch: pytest.MonkeyPatch, app_pool: RuntimePool
) -> InvoiceWorld:
    # TEST ONLY: H remains planned in the real registry. A separate negative
    # test withdraws this override while the positive publication remains.
    verified = tuple(
        m.model_copy(update={"readiness": Readiness.TECHNICALLY_VERIFIED, "enableable": True})
        if m.id == "finance_documents"
        else m
        for m in modules.MODULES
    )
    monkeypatch.setattr(modules, "MODULES", verified)
    monkeypatch.setattr(modules, "MODULES_BY_ID", {m.id: m for m in verified})
    monkeypatch.setattr(modules, "MODULE_CATALOG", modules.ModuleCatalog(modules=verified))
    config = Config(enabled.client, idp)
    await config.publish(
        enabled.user,
        enabled.business,
        1,
        ["booking_resources", "finance", "counterparties", "finance_documents"],
    )
    party = uuid7()
    response = await enabled.client.put(
        f"/v1/businesses/{enabled.business}/counterparties/{party}",
        json=card(),
        headers=enabled.headers(),
    )
    assert response.status_code == 200, response.text
    async with tenant_transaction(app_pool, enabled.business) as conn:
        accounts = await ledger.list_accounts(
            conn, enabled.business, enabled.book, after=None, limit=100
        )
    return InvoiceWorld(
        enabled,
        party,
        next(a.account_id for a in accounts.items if a.code == "1200"),
        next(a.account_id for a in accounts.items if a.type == "revenue"),
    )


async def test_invoice_route_requires_authentication(client: httpx.AsyncClient) -> None:
    path = f"/v1/businesses/{uuid7()}/financial-documents/books/{uuid7()}/invoices/{uuid7()}"
    response = await client.get(path)
    assert response.status_code == 401, response.text


async def test_issue_is_one_invoice_obligation_and_exact_journal(
    invoices: InvoiceWorld,
    app_pool: RuntimePool,
) -> None:
    document, key = uuid7(), str(uuid7())
    saved = await invoices.save(document=document)
    assert saved.status_code == 200, saved.text
    assert saved.json()["state"] == "draft"
    assert saved.json()["entry_id"] is None
    issued = await invoices.issue(document, key=key)
    assert issued.status_code == 200, issued.text
    view = issued.json()
    assert view["state"] == "issued"
    assert view["revision"] == 2
    assert view["total"] == "100.00"
    assert view["entry_id"]
    assert view["obligation_id"]
    replay = await invoices.issue(document, key=key)
    assert replay.status_code == 200
    assert replay.json() == view
    async with tenant_transaction(app_pool, invoices.ledger.business) as conn:
        row = await (
            await conn.execute(
                "select principal_minor,source_id,source_revision "
                "from gba.financial_obligations where id=%s",
                (UUID(view["obligation_id"]),),
            )
        ).fetchone()
        assert row == (10000, document, 2)
        links = await (
            await conn.execute(
                "select count(*) from gba.financial_operation_entries where document_id=%s",
                (document,),
            )
        ).fetchone()
        assert links == (1,)
    entry_path = f"{invoices.ledger.base}/entries/{view['entry_id']}"
    old = await invoices.ledger.client.get(entry_path, headers=invoices.ledger.auth)
    assert old.status_code == 409
    assert old.json()["error"]["code"] == "JOURNAL_VERSION_REQUIRED"
    current = await invoices.ledger.client.get(
        entry_path, params={"schema_version": 2}, headers=invoices.ledger.auth
    )
    assert current.status_code == 200, current.text
    assert current.json()["schema_version"] == 2
    assert current.json()["source_kind"] == "invoice"
    assert [(r["account_id"], r["side"], r["amount"]) for r in current.json()["lines"]] == [
        (str(invoices.control), "debit", "100.00"),
        (str(invoices.counter), "credit", "100.00"),
    ]
    history = await invoices.ledger.client.get(
        f"{invoices.base}/{document}", params={"revision": 1}, headers=invoices.ledger.auth
    )
    assert history.status_code == 200
    assert history.json()["state"] == "draft"
    changed = await invoices.save(document=document, body=invoices.draft_body(expected_revision=2))
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "FINANCIAL_STATE_INVALID"


async def test_closed_period_rolls_back_every_issue_effect(
    invoices: InvoiceWorld,
    app_pool: RuntimePool,
) -> None:
    document = uuid7()
    saved = await invoices.save(document=document)
    assert saved.status_code == 200
    closed = await invoices.ledger.client.post(
        f"{invoices.ledger.base}/periods/2026-10/close",
        json={"schema_version": 1, "expected_sequence": 0},
        headers=invoices.ledger.headers(),
    )
    assert closed.status_code == 200, closed.text
    denied = await invoices.issue(document)
    assert denied.status_code == 409, denied.text
    assert denied.json()["error"]["code"] == "LEDGER_PERIOD_CLOSED"
    async with tenant_transaction(app_pool, invoices.ledger.business) as conn:
        for table in ("financial_obligations", "financial_operation_entries", "journal_entries"):
            row = await (
                await conn.execute(
                    sql.SQL("select count(*) from gba.{} where book_id=%s").format(
                        sql.Identifier(table)
                    ),
                    (invoices.ledger.book,),
                )
            ).fetchone()
            assert row == (0,)
        state = await (
            await conn.execute(
                "select max(revision) from gba.financial_document_versions where document_id=%s",
                (document,),
            )
        ).fetchone()
        assert state == (1,)


async def test_late_balanced_journal_pair_cannot_change_an_issued_invoice(
    invoices: InvoiceWorld,
    app_pool: RuntimePool,
) -> None:
    document = uuid7()
    assert (await invoices.save(document=document)).status_code == 200
    with pytest.raises(psycopg.errors.CheckViolation, match="complete issued lines"):  # noqa: PT012
        async with tenant_transaction(app_pool, invoices.ledger.business) as conn:
            issued = await financial_documents.issue_invoice(
                conn,
                business_id=invoices.ledger.business,
                book_id=invoices.ledger.book,
                document_id=document,
                user_id=invoices.ledger.user.user_id,
                actor=f"user:{invoices.ledger.user.user_id}",
                key=str(uuid7()),
                body=InvoiceIssueInput(
                    expected_revision=1,
                    entry_date=date(2026, 10, 1),
                    attestation="confirmed_account_treatment",
                ),
            )
            # _complete has already run SET CONSTRAINTS IMMEDIATE then DEFERRED.
            # This balanced extra pair would pass G balance alone.
            await conn.execute(
                "insert into gba.journal_lines "
                "(tenant_id,entry_id,line_no,book_id,account_id,side,amount_minor) values "
                "(%s,%s,3,%s,%s,'debit',1),(%s,%s,4,%s,%s,'credit',1)",
                (
                    invoices.ledger.business,
                    issued.entry_id,
                    invoices.ledger.book,
                    invoices.control,
                    invoices.ledger.business,
                    issued.entry_id,
                    invoices.ledger.book,
                    invoices.counter,
                ),
            )
            await conn.execute("set constraints all immediate")
    current = await invoices.ledger.client.get(
        f"{invoices.base}/{document}", headers=invoices.ledger.auth
    )
    assert current.json()["state"] == "draft"


async def test_late_draft_line_after_same_transaction_issue_is_rechecked(
    invoices: InvoiceWorld,
    app_pool: RuntimePool,
) -> None:
    document = uuid7()
    body = InvoiceDraftInput.model_validate(invoices.draft_body())
    with pytest.raises(psycopg.errors.CheckViolation, match="complete lines must match"):  # noqa: PT012
        async with tenant_transaction(app_pool, invoices.ledger.business) as conn:
            await financial_documents.save_draft(
                conn,
                business_id=invoices.ledger.business,
                book_id=invoices.ledger.book,
                document_id=document,
                user_id=invoices.ledger.user.user_id,
                actor=f"user:{invoices.ledger.user.user_id}",
                key=str(uuid7()),
                body=body,
            )
            await financial_documents.issue_invoice(
                conn,
                business_id=invoices.ledger.business,
                book_id=invoices.ledger.book,
                document_id=document,
                user_id=invoices.ledger.user.user_id,
                actor=f"user:{invoices.ledger.user.user_id}",
                key=str(uuid7()),
                body=InvoiceIssueInput(
                    expected_revision=1,
                    entry_date=date(2026, 10, 1),
                    attestation="confirmed_account_treatment",
                ),
            )
            await conn.execute(
                "insert into gba.financial_document_lines "
                "(tenant_id,book_id,document_id,revision,line_no,line_id,counter_account_id,"
                "description,amount_minor) values (%s,%s,%s,1,2,%s,%s,'FAKE late line',1)",
                (
                    invoices.ledger.business,
                    invoices.ledger.book,
                    document,
                    uuid7(),
                    invoices.counter,
                ),
            )
            await conn.execute("set constraints all immediate")
    missing = await invoices.ledger.client.get(
        f"{invoices.base}/{document}", headers=invoices.ledger.auth
    )
    assert missing.status_code == 404


async def test_sql_rejects_orphan_invoice_origin_and_unissued_obligation(
    invoices: InvoiceWorld,
    app_pool: RuntimePool,
) -> None:
    with pytest.raises(psycopg.errors.CheckViolation, match="issued version"):
        async with tenant_transaction(app_pool, invoices.ledger.business) as conn:
            await conn.execute(
                "insert into gba.journal_entries "
                "(tenant_id,id,book_id,entry_date,currency,source_kind,source_id,created_by) "
                "values (%s,%s,%s,'2026-10-01','USD','invoice',%s,%s)",
                (
                    invoices.ledger.business,
                    uuid7(),
                    invoices.ledger.book,
                    str(uuid7()),
                    invoices.ledger.user.user_id,
                ),
            )
    document = uuid7()
    assert (await invoices.save(document=document)).status_code == 200
    with pytest.raises(psycopg.errors.CheckViolation, match="issued invoice"):  # noqa: PT012
        async with tenant_transaction(app_pool, invoices.ledger.business) as conn:
            await conn.execute(
                "insert into gba.financial_obligations "
                "(tenant_id,book_id,id,source_kind,source_id,source_revision,component,"
                "counterparty_id,counterparty_revision,direction,currency,control_account_id,"
                "principal_minor,created_by) "
                "values (%s,%s,%s,'invoice',%s,1,'principal',%s,1,'receivable','USD',%s,10000,%s)",
                (
                    invoices.ledger.business,
                    invoices.ledger.book,
                    uuid7(),
                    document,
                    invoices.party,
                    invoices.control,
                    invoices.ledger.user.user_id,
                ),
            )
            await conn.execute("set constraints all immediate")


async def test_generic_api_and_sql_reversal_refuse_h_owned_journal(
    invoices: InvoiceWorld,
    app_pool: RuntimePool,
) -> None:
    document = uuid7()
    assert (await invoices.save(document=document)).status_code == 200
    issued = await invoices.issue(document)
    assert issued.status_code == 200
    entry = UUID(issued.json()["entry_id"])
    denied = await invoices.ledger.client.post(
        f"{invoices.ledger.base}/entries/{entry}/reverse",
        json={"schema_version": 1, "reversal_entry_id": str(uuid7()), "entry_date": "2026-10-02"},
        headers=invoices.ledger.headers(),
    )
    assert denied.status_code == 409
    assert denied.json()["error"]["code"] == "LEDGER_STATE_INVALID"
    with pytest.raises(psycopg.errors.CheckViolation, match="H-owned journal correction"):
        async with tenant_transaction(app_pool, invoices.ledger.business) as conn:
            await conn.execute(
                "insert into gba.journal_entries (tenant_id,id,book_id,entry_date,currency,"
                "source_kind,source_id,reverses_entry_id,created_by) "
                "values (%s,%s,%s,'2026-10-02','USD','reversal',%s,%s,%s)",
                (
                    invoices.ledger.business,
                    uuid7(),
                    invoices.ledger.book,
                    str(entry),
                    entry,
                    invoices.ledger.user.user_id,
                ),
            )


async def test_replay_and_minimal_recovery_survive_receipt_cleanup(
    invoices: InvoiceWorld,
    owner_conn: psycopg.Connection,
) -> None:
    document, key = uuid7(), str(uuid7())
    assert (await invoices.save(document=document)).status_code == 200
    issued = await invoices.issue(document, key=key)
    assert issued.status_code == 200
    with owner_tenant_transaction(owner_conn, invoices.ledger.business):
        owner_conn.execute(
            "delete from gba.idempotency_keys where tenant_id=%s "
            "and operation='business.finance.invoice_issue' and idempotency_key=%s",
            (invoices.ledger.business, key),
        )
    command_base = f"/v1/businesses/{invoices.ledger.business}/financial-documents/commands/{key}"
    reference = {
        "schema_version": 1,
        "operation": "invoice_issue",
        "book_id": str(invoices.ledger.book),
        "subject_id": str(document),
        "revision": 2,
    }
    resolved = await invoices.ledger.client.post(
        command_base + "/resolve", json=reference, headers=invoices.ledger.auth
    )
    assert resolved.status_code == 200
    assert resolved.json()["state"] == "committed"
    replay = await invoices.issue(document, key=key)
    assert replay.status_code == 200
    assert replay.json() == issued.json()
    different = await invoices.issue(document, key=key, entry_date="2026-10-02")
    assert different.status_code == 422
    assert different.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    other_key = await invoices.issue(document)
    assert other_key.status_code == 409
    wrong = await invoices.ledger.client.post(
        command_base + "/resolve",
        json={**reference, "subject_id": str(uuid7())},
        headers=invoices.ledger.auth,
    )
    assert wrong.status_code == 422
    with owner_tenant_transaction(owner_conn, invoices.ledger.business):
        row = owner_conn.execute(
            "select response_body from gba.idempotency_keys "
            "where tenant_id=%s and operation='business.finance.invoice_issue' "
            "and idempotency_key=%s",
            (invoices.ledger.business, key),
        ).fetchone()
    assert row is not None
    assert set(row[0]) == {"book_id", "document_id", "revision"}


async def test_off_preserves_history_replay_and_permanent_safe_cancel(
    invoices: InvoiceWorld,
    idp: FakeIdp,
) -> None:
    document, issue_key = uuid7(), str(uuid7())
    assert (await invoices.save(document=document)).status_code == 200
    issued = await invoices.issue(document, key=issue_key)
    assert issued.status_code == 200
    config = Config(invoices.ledger.client, idp)
    await config.publish(
        invoices.ledger.user, invoices.ledger.business, 2, ["booking_resources", "counterparties"]
    )
    history = await invoices.ledger.client.get(
        f"{invoices.base}/{document}", headers=invoices.ledger.auth
    )
    assert history.status_code == 200
    assert (await invoices.issue(document, key=issue_key)).json() == issued.json()
    denied = await invoices.save()
    assert denied.json()["error"]["code"] == "MODULE_DISABLED"
    late, key = uuid7(), str(uuid7())
    reference = {
        "schema_version": 1,
        "operation": "invoice_draft",
        "book_id": str(invoices.ledger.book),
        "subject_id": str(late),
        "revision": 1,
    }
    path = f"/v1/businesses/{invoices.ledger.business}/financial-documents/commands/{key}"
    cancelled = await invoices.ledger.client.post(
        path + "/cancel", json=reference, headers=invoices.ledger.auth
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["state"] == "cancelled"
    repeated = await invoices.ledger.client.post(
        path + "/cancel", json=reference, headers=invoices.ledger.auth
    )
    assert repeated.json()["state"] == "cancelled"
    blocked = await invoices.save(document=late, key=key)
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "FINANCIAL_COMMAND_CANCELLED"
    unresolved = await invoices.ledger.client.post(
        path + "/resolve", json=reference, headers=invoices.ledger.auth
    )
    assert unresolved.json()["state"] == "cancelled"


async def test_published_h_snapshot_cannot_bypass_withdrawn_current_readiness(
    invoices: InvoiceWorld,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    feature = modules.MODULES_BY_ID["finance_documents"]
    monkeypatch.setitem(
        modules.MODULES_BY_ID,
        "finance_documents",
        feature.model_copy(update={"enableable": False, "readiness": Readiness.PLANNED}),
    )
    denied = await invoices.save()
    assert denied.status_code == 409
    assert denied.json()["error"]["code"] == "MODULE_NOT_READY"
    unchanged_g = await invoices.ledger.post(invoices.ledger.entry())
    assert unchanged_g.status_code == 200, unchanged_g.text


async def test_book_list_requires_v2_without_omitting_invoice_and_trial_balance_includes_it(
    invoices: InvoiceWorld,
) -> None:
    document = uuid7()
    assert (await invoices.save(document=document)).status_code == 200
    assert (await invoices.issue(document)).status_code == 200
    legacy = await invoices.ledger.client.get(
        invoices.ledger.base + "/entries", headers=invoices.ledger.auth
    )
    assert legacy.status_code == 409
    assert legacy.json()["error"]["code"] == "JOURNAL_VERSION_REQUIRED"
    modern = await invoices.ledger.client.get(
        invoices.ledger.base + "/entries",
        params={"schema_version": 2, "limit": 1},
        headers=invoices.ledger.auth,
    )
    assert modern.status_code == 200
    assert modern.json()["items"][0]["source_kind"] == "invoice"
    report = await invoices.ledger.client.get(
        invoices.ledger.base + "/trial-balance",
        params={"period_from": "2026-10", "period_to": "2026-10", "currency": "USD"},
        headers=invoices.ledger.auth,
    )
    assert report.status_code == 200
    assert report.json()["totals"]["debit"] == "100.00"
    assert report.json()["totals"]["credit"] == "100.00"


async def test_two_issue_requests_wait_on_real_lock_and_only_one_commits(
    invoices: InvoiceWorld,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
) -> None:
    document = uuid7()
    assert (await invoices.save(document=document)).status_code == 200
    async with tenant_transaction(app_pool, invoices.ledger.business) as conn:
        await conn.execute("select gba.lock_ledger(%s)", (invoices.ledger.business,))
        pending = [asyncio.create_task(invoices.issue(document)) for _ in range(2)]
        try:
            for _ in range(200):
                await asyncio.sleep(0.01)
                row = owner_conn.execute(
                    "select count(*) from pg_catalog.pg_locks "
                    "where locktype='advisory' and not granted"
                ).fetchone()
                if row and row[0] >= 2:
                    break
            else:
                pytest.fail(
                    "Both invoice requests must be observed waiting on the held ledger lock"
                )
        except BaseException:
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            raise
    results = await asyncio.gather(*pending)
    assert sorted(r.status_code for r in results) == [200, 409]
    async with tenant_transaction(app_pool, invoices.ledger.business) as conn:
        row = await (
            await conn.execute(
                "select count(*) from gba.financial_obligations where source_id=%s", (document,)
            )
        ).fetchone()
        assert row == (1,)


@pytest.mark.parametrize(
    "table",
    [
        "financial_documents",
        "financial_document_versions",
        "financial_document_lines",
        "financial_obligations",
        "financial_operation_entries",
        "financial_command_receipts",
    ],
)
async def test_sql_history_stays_insert_only(
    invoices: InvoiceWorld,
    owner_conn: psycopg.Connection,
    table: str,
) -> None:
    document = uuid7()
    assert (await invoices.save(document=document)).status_code == 200
    assert (await invoices.issue(document)).status_code == 200
    with (
        pytest.raises(psycopg.errors.CheckViolation, match="kept unchanged"),
        owner_tenant_transaction(owner_conn, invoices.ledger.business),
    ):
        owner_conn.execute(
            sql.SQL("update gba.{} set book_id=book_id where book_id=%s").format(
                sql.Identifier(table)
            ),
            (invoices.ledger.book,),
        )


@pytest.mark.parametrize(
    ("change", "restore"),
    [
        (
            "alter table gba.financial_document_lines "
            "disable trigger financial_document_lines_consistent",
            "alter table gba.financial_document_lines "
            "enable trigger financial_document_lines_consistent",
        ),
        (
            "alter table gba.journal_lines disable trigger journal_lines_invoice_consistent",
            "alter table gba.journal_lines enable trigger journal_lines_invoice_consistent",
        ),
        (
            "alter table gba.financial_documents no force row level security",
            "alter table gba.financial_documents force row level security",
        ),
        (
            "alter policy financial_obligations_unrestricted_scope on gba.financial_obligations "
            "using (true) with check (true)",
            "alter policy financial_obligations_unrestricted_scope on gba.financial_obligations "
            "using (gba.current_location_id() is null) "
            "with check (gba.current_location_id() is null)",
        ),
        (
            "create policy extra_financial_grant on gba.financial_documents "
            "using (true) with check (true)",
            "drop policy extra_financial_grant on gba.financial_documents",
        ),
        (
            "alter table gba.financial_command_receipts "
            "drop constraint financial_command_receipts_pkey",
            "alter table gba.financial_command_receipts "
            "add constraint financial_command_receipts_pkey "
            "primary key(tenant_id,actor_key,operation,idempotency_key)",
        ),
        (
            "alter table gba.financial_document_versions "
            "drop constraint financial_versions_control_fk",
            "alter table gba.financial_document_versions "
            "add constraint financial_versions_control_fk "
            "foreign key(tenant_id,book_id,control_account_id) "
            "references gba.ledger_accounts(tenant_id,book_id,id)",
        ),
        (
            "grant insert(created_transaction) on gba.financial_document_versions to gba_runtime",
            "revoke insert(created_transaction) on gba.financial_document_versions "
            "from gba_runtime",
        ),
    ],
)
async def test_damaged_financial_controls_fail_readiness_with_503(
    invoices: InvoiceWorld,
    owner_conn: psycopg.Connection,
    change: str,
    restore: str,
) -> None:
    owner_conn.execute(change)
    try:
        result = await invoices.ledger.client.get(
            invoices.ledger.base, headers=invoices.ledger.auth
        )
        assert result.status_code == 503, result.text
        assert result.json()["error"]["code"] == "DATABASE_UNAVAILABLE"
    finally:
        owner_conn.execute(restore)
    healthy = await invoices.ledger.client.get(invoices.ledger.base, headers=invoices.ledger.auth)
    assert healthy.status_code == 200, healthy.text


@pytest.mark.parametrize(
    ("role", "branch", "expected"),
    [
        ("owner", False, 200),
        ("front_desk", False, 403),
        ("artist", False, 403),
        ("manager", True, 403),
    ],
)
async def test_invoice_routes_keep_company_finance_permissions(
    invoices: InvoiceWorld,
    owner_conn: psycopg.Connection,
    world: BookingWorld,
    idp: FakeIdp,
    role: str,
    branch: bool,
    expected: int,
) -> None:
    document = uuid7()
    assert (await invoices.save(document=document)).status_code == 200
    member = seed_user(owner_conn, f"FAKE-H1-{role}-{uuid7()}")
    add_membership(
        owner_conn,
        tenant_id=invoices.ledger.business,
        user_id=member.user_id,
        role=role,
        location_id=world.a.location_id if branch else None,
    )
    auth = idp.bearer(member.subject, email=member.email)
    response = await invoices.ledger.client.get(f"{invoices.base}/{document}", headers=auth)
    assert response.status_code == expected, response.text
    if expected != 200:
        save = await invoices.ledger.client.put(
            f"{invoices.base}/{uuid7()}",
            json=invoices.draft_body(),
            headers={**auth, "Idempotency-Key": str(uuid7())},
        )
        assert save.status_code == 403


async def test_foreign_party_and_book_never_form_an_invoice(
    invoices: InvoiceWorld,
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    manager_b: FakeUser,
    idp: FakeIdp,
) -> None:
    config = Config(invoices.ledger.client, idp)
    await config.profile(manager_b, world.b.tenant_id, 0, [1])
    await config.publish(manager_b, world.b.tenant_id, 0, ["booking_resources", "counterparties"])
    foreign = uuid7()
    created = await invoices.ledger.client.put(
        f"/v1/businesses/{world.b.tenant_id}/counterparties/{foreign}",
        json=card(),
        headers=config.headers(manager_b),
    )
    assert created.status_code == 200
    document = uuid7()
    refused = await invoices.save(
        document=document, body=invoices.draft_body(counterparty_id=str(foreign))
    )
    assert refused.status_code == 409
    with owner_tenant_transaction(owner_conn, invoices.ledger.business):
        assert owner_conn.execute(
            "select count(*) from gba.financial_documents where id=%s", (document,)
        ).fetchone() == (0,)
    foreign_read = await invoices.ledger.client.get(
        f"{invoices.base}/{document}", headers=config.auth(manager_b)
    )
    assert foreign_read.status_code == 403
    bad_book = (
        f"/v1/businesses/{invoices.ledger.business}/financial-documents/"
        f"books/{uuid7()}/invoices/{uuid7()}"
    )
    refused_book = await invoices.ledger.client.put(
        bad_book, json=invoices.draft_body(), headers=invoices.ledger.headers()
    )
    assert refused_book.status_code == 404


@pytest.mark.parametrize(
    ("currency", "amount", "minor"),
    [
        ("USD", "0.01", 1),
        ("JPY", "1", 1),
        ("KWD", "0.001", 1),
    ],
)
async def test_invoice_and_journal_share_actual_currency_scale(
    invoices: InvoiceWorld,
    app_pool: RuntimePool,
    currency: str,
    amount: str,
    minor: int,
) -> None:
    document = uuid7()
    body = invoices.draft_body(currency=currency)
    body["lines"] = [
        {
            "line_id": str(uuid7()),
            "counter_account_id": str(invoices.counter),
            "description": "FAKE exact currency",
            "amount": amount,
        }
    ]
    saved = await invoices.save(document=document, body=body)
    assert saved.status_code == 200, saved.text
    issued = await invoices.issue(document)
    assert issued.status_code == 200
    assert issued.json()["total"] == amount
    async with tenant_transaction(app_pool, invoices.ledger.business) as conn:
        row = await (
            await conn.execute(
                "select currency,principal_minor from gba.financial_obligations where source_id=%s",
                (document,),
            )
        ).fetchone()
        assert row == (currency, minor)


async def test_payable_issue_posts_explicit_expense_against_control_liability(
    invoices: InvoiceWorld,
    app_pool: RuntimePool,
) -> None:
    async with tenant_transaction(app_pool, invoices.ledger.business) as conn:
        chart = await ledger.list_accounts(
            conn, invoices.ledger.business, invoices.ledger.book, after=None, limit=100
        )
    control = next(a.account_id for a in chart.items if a.code == "2000")
    expense = next(a.account_id for a in chart.items if a.type == "expense")
    document = uuid7()
    body = invoices.draft_body(direction="payable", control_account_id=str(control))
    body["lines"] = [
        {
            "line_id": str(uuid7()),
            "counter_account_id": str(expense),
            "description": "FAKE explicitly recognized expense",
            "amount": "100.00",
        }
    ]
    saved = await invoices.save(document=document, body=body)
    assert saved.status_code == 200, saved.text
    issued = await invoices.issue(document)
    assert issued.status_code == 200, issued.text
    current = await invoices.ledger.client.get(
        f"{invoices.ledger.base}/entries/{issued.json()['entry_id']}",
        params={"schema_version": 2},
        headers=invoices.ledger.auth,
    )
    assert [(line["account_id"], line["side"]) for line in current.json()["lines"]] == [
        (str(control), "credit"),
        (str(expense), "debit"),
    ]


async def test_deferred_income_choice_and_exact_multi_line_total(
    invoices: InvoiceWorld,
    app_pool: RuntimePool,
) -> None:
    async with tenant_transaction(app_pool, invoices.ledger.business) as conn:
        chart = await ledger.list_accounts(
            conn, invoices.ledger.business, invoices.ledger.book, after=None, limit=100
        )
    deferred = next(a.account_id for a in chart.items if a.code == "2100")
    document = uuid7()
    body = invoices.draft_body()
    body["lines"] = [
        {
            "line_id": str(uuid7()),
            "counter_account_id": str(deferred),
            "description": "FAKE deferred treatment",
            "amount": amount,
        }
        for amount in ("0.10", "0.20")
    ]
    saved = await invoices.save(document=document, body=body)
    assert saved.status_code == 200
    assert saved.json()["total"] == "0.30"
    issued = await invoices.issue(document)
    assert issued.status_code == 200
    async with tenant_transaction(app_pool, invoices.ledger.business) as conn:
        lines = await (
            await conn.execute(
                "select account_id,side,amount_minor from gba.journal_lines "
                "where entry_id=%s order by line_no",
                (UUID(issued.json()["entry_id"]),),
            )
        ).fetchall()
        assert lines == [
            (invoices.control, "debit", 30),
            (deferred, "credit", 10),
            (deferred, "credit", 20),
        ]


async def test_issue_requires_attestation_and_history_cannot_be_filled_later(
    invoices: InvoiceWorld,
    app_pool: RuntimePool,
) -> None:
    document = uuid7()
    assert (await invoices.save(document=document)).status_code == 200
    invalid = await invoices.ledger.client.post(
        f"{invoices.base}/{document}/issue",
        json={"expected_revision": 1, "entry_date": "2026-10-01"},
        headers=invoices.ledger.headers(),
    )
    assert invalid.status_code == 422
    with pytest.raises(psycopg.errors.CheckViolation, match="written with their version"):
        async with tenant_transaction(app_pool, invoices.ledger.business) as conn:
            await conn.execute(
                "insert into gba.financial_document_lines "
                "(tenant_id,book_id,document_id,revision,line_no,line_id,counter_account_id,"
                "description,amount_minor) values (%s,%s,%s,1,2,%s,%s,'FAKE later insert',1)",
                (
                    invoices.ledger.business,
                    invoices.ledger.book,
                    document,
                    uuid7(),
                    invoices.counter,
                ),
            )
