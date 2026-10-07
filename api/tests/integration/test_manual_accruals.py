"""H2 manual accruals: a new obligation and G accrual, never a link to an old entry."""

import asyncio
from dataclasses import dataclass
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest
from psycopg import sql

from gorgona_booking.business import ledger, modules
from gorgona_booking.business.readiness_registry import Readiness
from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import add_membership, owner_tenant_transaction
from tests.integration import test_invoice_issue as invoice_shared
from tests.integration.booking_support import BookingWorld
from tests.integration.configuration_support import Config
from tests.integration.seed import seed_user
from tests.integration.test_invoice_issue import (
    InvoiceWorld,
    approved_check,
    packaged_function,
    widened_check,
)
from tests.integration.test_ledger import LedgerWorld
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = invoice_shared.client
idp = invoice_shared.idp
manager_a = invoice_shared.manager_a
manager_b = invoice_shared.manager_b
enabled = invoice_shared.enabled
invoices = invoice_shared.invoices


@dataclass(frozen=True)
class AccrualWorld:
    invoices: InvoiceWorld

    @property
    def ledger(self) -> LedgerWorld:
        return self.invoices.ledger

    @property
    def base(self) -> str:
        return (
            f"/v1/businesses/{self.ledger.business}/financial-documents/"
            f"books/{self.ledger.book}/accruals"
        )

    def body(self, **changes: object) -> dict[str, object]:
        return self.invoices.draft_body(
            **{"title": "FAKE manual accrual", "number": "FAKE-ACC-001", **changes}
        )

    async def save(
        self,
        *,
        document: UUID | None = None,
        key: str | None = None,
        body: dict[str, object] | None = None,
    ) -> httpx.Response:
        return await self.ledger.client.put(
            f"{self.base}/{document or uuid7()}",
            json=body or self.body(),
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
def accruals(invoices: InvoiceWorld) -> AccrualWorld:
    return AccrualWorld(invoices)


async def test_accrual_route_requires_authentication(client: httpx.AsyncClient) -> None:
    path = f"/v1/businesses/{uuid7()}/financial-documents/books/{uuid7()}/accruals/{uuid7()}"
    assert (await client.get(path)).status_code == 401


async def test_manual_accrual_is_one_new_obligation_and_exact_journal(
    accruals: AccrualWorld,
    app_pool: RuntimePool,
) -> None:
    document, key = uuid7(), str(uuid7())
    saved = await accruals.save(document=document)
    assert saved.status_code == 200, saved.text
    assert (saved.json()["kind"], saved.json()["state"]) == ("manual_accrual", "draft")
    assert saved.json()["entry_id"] is None
    issued = await accruals.issue(document, key=key)
    assert issued.status_code == 200, issued.text
    view = issued.json()
    assert (view["kind"], view["state"], view["revision"], view["total"]) == (
        "manual_accrual",
        "issued",
        2,
        "100.00",
    )
    replay = await accruals.issue(document, key=key)
    assert replay.status_code == 200
    assert replay.json() == view
    async with tenant_transaction(app_pool, accruals.ledger.business) as conn:
        obligation = await (
            await conn.execute(
                "select source_kind,component,principal_minor,source_id,source_revision "
                "from gba.financial_obligations where id=%s",
                (UUID(view["obligation_id"]),),
            )
        ).fetchone()
        assert obligation == ("manual", "principal", 10000, document, 2)
        links = await (
            await conn.execute(
                "select count(*) from gba.financial_operation_entries where document_id=%s",
                (document,),
            )
        ).fetchone()
        assert links == (1,)
        receipts = await (
            await conn.execute(
                "select operation from gba.financial_command_receipts "
                "where document_id=%s order by revision",
                (document,),
            )
        ).fetchall()
        assert receipts == [("accrual_draft",), ("accrual_issue",)]
    entry_path = f"{accruals.ledger.base}/entries/{view['entry_id']}"
    old = await accruals.ledger.client.get(entry_path, headers=accruals.ledger.auth)
    assert old.status_code == 409
    assert old.json()["error"]["code"] == "JOURNAL_VERSION_REQUIRED"
    current = await accruals.ledger.client.get(
        entry_path, params={"schema_version": 2}, headers=accruals.ledger.auth
    )
    assert current.status_code == 200, current.text
    assert current.json()["source_kind"] == "accrual"
    assert current.json()["source_id"] == str(document)
    assert [(r["account_id"], r["side"], r["amount"]) for r in current.json()["lines"]] == [
        (str(accruals.invoices.control), "debit", "100.00"),
        (str(accruals.invoices.counter), "credit", "100.00"),
    ]
    changed = await accruals.save(document=document, body=accruals.body(expected_revision=2))
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "FINANCIAL_STATE_INVALID"


async def test_payable_accrual_posts_explicit_expense_against_control_liability(
    accruals: AccrualWorld,
    app_pool: RuntimePool,
) -> None:
    async with tenant_transaction(app_pool, accruals.ledger.business) as conn:
        chart = await ledger.list_accounts(
            conn, accruals.ledger.business, accruals.ledger.book, after=None, limit=100
        )
    control = next(a.account_id for a in chart.items if a.code == "2000")
    expense = next(a.account_id for a in chart.items if a.type == "expense")
    document = uuid7()
    body = accruals.body(direction="payable", control_account_id=str(control))
    body["lines"] = [
        {
            "line_id": str(uuid7()),
            "counter_account_id": str(expense),
            "description": "FAKE explicitly recognized expense",
            "amount": "40.00",
        }
    ]
    assert (await accruals.save(document=document, body=body)).status_code == 200
    issued = await accruals.issue(document)
    assert issued.status_code == 200, issued.text
    current = await accruals.ledger.client.get(
        f"{accruals.ledger.base}/entries/{issued.json()['entry_id']}",
        params={"schema_version": 2},
        headers=accruals.ledger.auth,
    )
    assert [(r["account_id"], r["side"], r["amount"]) for r in current.json()["lines"]] == [
        (str(control), "credit", "40.00"),
        (str(expense), "debit", "40.00"),
    ]
    async with tenant_transaction(app_pool, accruals.ledger.business) as conn:
        row = await (
            await conn.execute(
                "select source_kind,direction,control_account_id,principal_minor "
                "from gba.financial_obligations where source_id=%s",
                (document,),
            )
        ).fetchone()
    assert row == ("manual", "payable", control, 4000)


async def test_closed_period_rolls_back_every_accrual_effect(
    accruals: AccrualWorld,
    app_pool: RuntimePool,
) -> None:
    document = uuid7()
    assert (await accruals.save(document=document)).status_code == 200
    closed = await accruals.ledger.client.post(
        f"{accruals.ledger.base}/periods/2026-10/close",
        json={"schema_version": 1, "expected_sequence": 0},
        headers=accruals.ledger.headers(),
    )
    assert closed.status_code == 200, closed.text
    denied = await accruals.issue(document)
    assert denied.status_code == 409, denied.text
    assert denied.json()["error"]["code"] == "LEDGER_PERIOD_CLOSED"
    async with tenant_transaction(app_pool, accruals.ledger.business) as conn:
        for table in ("financial_obligations", "financial_operation_entries", "journal_entries"):
            row = await (
                await conn.execute(
                    sql.SQL("select count(*) from gba.{} where book_id=%s").format(
                        sql.Identifier(table)
                    ),
                    (accruals.ledger.book,),
                )
            ).fetchone()
            assert row == (0,)


async def test_document_kinds_never_cross_routes(accruals: AccrualWorld) -> None:
    invoice, accrual = uuid7(), uuid7()
    assert (await accruals.invoices.save(document=invoice)).status_code == 200
    assert (await accruals.save(document=accrual)).status_code == 200
    auth = accruals.ledger.auth
    http = accruals.ledger.client
    assert (await http.get(f"{accruals.base}/{invoice}", headers=auth)).status_code == 404
    assert (await http.get(f"{accruals.invoices.base}/{accrual}", headers=auth)).status_code == 404
    taken = await accruals.save(document=invoice, body=accruals.body(expected_revision=1))
    assert taken.status_code == 409
    assert taken.json()["error"]["code"] == "FINANCIAL_STATE_INVALID"
    assert (await accruals.issue(invoice)).status_code == 404
    assert (await accruals.invoices.issue(accrual)).status_code == 404
    listed_accruals = await http.get(accruals.base, headers=auth)
    listed_invoices = await http.get(accruals.invoices.base, headers=auth)
    assert [i["document_id"] for i in listed_accruals.json()["items"]] == [str(accrual)]
    assert [i["document_id"] for i in listed_invoices.json()["items"]] == [str(invoice)]
    # The untouched invoice still issues as an invoice.
    issued = await accruals.invoices.issue(invoice)
    assert issued.status_code == 200, issued.text
    assert issued.json()["kind"] == "invoice"


async def test_existing_manual_entry_is_never_linked_or_accrued_twice(
    accruals: AccrualWorld,
    app_pool: RuntimePool,
) -> None:
    legacy = uuid7()
    posted = await accruals.ledger.post(
        accruals.ledger.entry(source_id="FAKE-LEGACY-ACCRUAL"), entry=legacy
    )
    assert posted.status_code == 200, posted.text
    document = uuid7()
    assert (await accruals.save(document=document)).status_code == 200
    issued = await accruals.issue(document)
    assert issued.status_code == 200, issued.text
    assert issued.json()["entry_id"] != str(legacy)
    business, book = accruals.ledger.business, accruals.ledger.book
    async with tenant_transaction(app_pool, business) as conn:
        kinds = await (
            await conn.execute(
                "select id,source_kind from gba.journal_entries where book_id=%s", (book,)
            )
        ).fetchall()
        assert sorted(kinds) == sorted(
            [(legacy, "manual"), (UUID(issued.json()["entry_id"]), "accrual")]
        )
        linked = await (
            await conn.execute(
                "select count(*) from gba.financial_operation_entries where entry_id=%s",
                (legacy,),
            )
        ).fetchone()
        assert linked == (0,)
    # A forged issue that names the old manual entry as its accrual is refused.
    forged, obligation = uuid7(), uuid7()
    assert (await accruals.save(document=forged)).status_code == 200
    with pytest.raises(psycopg.errors.CheckViolation, match="lineage must match"):  # noqa: PT012
        async with tenant_transaction(app_pool, business) as conn:
            await conn.execute(
                "insert into gba.financial_document_versions "
                "(tenant_id,book_id,document_id,revision,state,direction,counterparty_id,"
                "counterparty_revision,currency,invoice_date,due_date,control_account_id,title,"
                "number,principal_minor,line_count,entry_id,obligation_id,issued_on,attestation,"
                "created_by) "
                "select tenant_id,book_id,document_id,2,'issued',direction,counterparty_id,"
                "counterparty_revision,currency,invoice_date,due_date,control_account_id,title,"
                "number,principal_minor,line_count,%s,%s,'2026-10-01',"
                "'confirmed_account_treatment',created_by "
                "from gba.financial_document_versions where document_id=%s and revision=1",
                (legacy, obligation, forged),
            )
            await conn.execute(
                "insert into gba.financial_document_lines "
                "(tenant_id,book_id,document_id,revision,line_no,line_id,counter_account_id,"
                "description,amount_minor) "
                "select tenant_id,book_id,document_id,2,line_no,line_id,counter_account_id,"
                "description,amount_minor from gba.financial_document_lines "
                "where document_id=%s and revision=1",
                (forged,),
            )
            await conn.execute(
                "insert into gba.financial_obligations "
                "(tenant_id,book_id,id,source_kind,source_id,source_revision,component,"
                "counterparty_id,counterparty_revision,direction,currency,control_account_id,"
                "principal_minor,created_by) "
                "select tenant_id,book_id,%s,'manual',document_id,2,'principal',counterparty_id,"
                "counterparty_revision,direction,currency,control_account_id,principal_minor,"
                "created_by from gba.financial_document_versions "
                "where document_id=%s and revision=1",
                (obligation, forged),
            )
            await conn.execute(
                "insert into gba.financial_operation_entries "
                "(tenant_id,book_id,document_id,revision,component,entry_id,obligation_id) "
                "values (%s,%s,%s,2,'principal',%s,%s)",
                (business, book, forged, legacy, obligation),
            )
            await conn.execute("set constraints all immediate")
    current = await accruals.ledger.client.get(
        f"{accruals.base}/{forged}", headers=accruals.ledger.auth
    )
    assert current.json()["state"] == "draft"


async def test_sql_rejects_orphan_accrual_origin_and_second_source_for_an_invoice(
    accruals: AccrualWorld,
    app_pool: RuntimePool,
) -> None:
    business, book = accruals.ledger.business, accruals.ledger.book
    invoice = uuid7()
    assert (await accruals.invoices.save(document=invoice)).status_code == 200
    assert (await accruals.invoices.issue(invoice)).status_code == 200
    for source in (str(uuid7()), str(invoice)):
        with pytest.raises(psycopg.errors.CheckViolation, match="issued version"):
            async with tenant_transaction(app_pool, business) as conn:
                await conn.execute(
                    "insert into gba.journal_entries "
                    "(tenant_id,id,book_id,entry_date,currency,source_kind,source_id,created_by) "
                    "values (%s,%s,%s,'2026-10-01','USD','accrual',%s,%s)",
                    (business, uuid7(), book, source, accruals.ledger.user.user_id),
                )
    # An issued invoice cannot gain a second, manual obligation for the same principal.
    with pytest.raises(psycopg.errors.CheckViolation, match="issued invoice"):  # noqa: PT012
        async with tenant_transaction(app_pool, business) as conn:
            await conn.execute(
                "insert into gba.financial_obligations "
                "(tenant_id,book_id,id,source_kind,source_id,source_revision,component,"
                "counterparty_id,counterparty_revision,direction,currency,control_account_id,"
                "principal_minor,created_by) "
                "values (%s,%s,%s,'manual',%s,2,'principal',%s,1,'receivable','USD',%s,10000,%s)",
                (
                    business,
                    book,
                    uuid7(),
                    invoice,
                    accruals.invoices.party,
                    accruals.invoices.control,
                    accruals.ledger.user.user_id,
                ),
            )
            await conn.execute("set constraints all immediate")


async def test_generic_api_and_sql_reversal_refuse_an_accrual_journal(
    accruals: AccrualWorld,
    app_pool: RuntimePool,
) -> None:
    document = uuid7()
    assert (await accruals.save(document=document)).status_code == 200
    issued = await accruals.issue(document)
    assert issued.status_code == 200
    entry = UUID(issued.json()["entry_id"])
    denied = await accruals.ledger.client.post(
        f"{accruals.ledger.base}/entries/{entry}/reverse",
        json={"schema_version": 1, "reversal_entry_id": str(uuid7()), "entry_date": "2026-10-02"},
        headers=accruals.ledger.headers(),
    )
    assert denied.status_code == 409
    assert denied.json()["error"]["code"] == "LEDGER_STATE_INVALID"
    with pytest.raises(psycopg.errors.CheckViolation, match="H-owned journal correction"):
        async with tenant_transaction(app_pool, accruals.ledger.business) as conn:
            await conn.execute(
                "insert into gba.journal_entries (tenant_id,id,book_id,entry_date,currency,"
                "source_kind,source_id,reverses_entry_id,created_by) "
                "values (%s,%s,%s,'2026-10-02','USD','reversal',%s,%s,%s)",
                (
                    accruals.ledger.business,
                    uuid7(),
                    accruals.ledger.book,
                    str(entry),
                    entry,
                    accruals.ledger.user.user_id,
                ),
            )


async def test_book_list_requires_v2_and_trial_balance_includes_the_accrual(
    accruals: AccrualWorld,
) -> None:
    document = uuid7()
    assert (await accruals.save(document=document)).status_code == 200
    assert (await accruals.issue(document)).status_code == 200
    http, auth, base = accruals.ledger.client, accruals.ledger.auth, accruals.ledger.base
    legacy = await http.get(base + "/entries", headers=auth)
    assert legacy.status_code == 409
    assert legacy.json()["error"]["code"] == "JOURNAL_VERSION_REQUIRED"
    modern = await http.get(base + "/entries", params={"schema_version": 2}, headers=auth)
    assert modern.status_code == 200, modern.text
    assert [item["source_kind"] for item in modern.json()["items"]] == ["accrual"]
    report = await http.get(
        base + "/trial-balance",
        params={"period_from": "2026-10", "period_to": "2026-10", "currency": "USD"},
        headers=auth,
    )
    assert report.status_code == 200
    assert report.json()["totals"]["debit"] == "100.00"
    assert report.json()["totals"]["credit"] == "100.00"


async def test_accrual_replay_and_recovery_survive_receipt_cleanup(
    accruals: AccrualWorld,
    owner_conn: psycopg.Connection,
) -> None:
    document, key = uuid7(), str(uuid7())
    assert (await accruals.save(document=document)).status_code == 200
    issued = await accruals.issue(document, key=key)
    assert issued.status_code == 200
    business = accruals.ledger.business
    with owner_tenant_transaction(owner_conn, business):
        deleted = owner_conn.execute(
            "delete from gba.idempotency_keys where tenant_id=%s "
            "and operation='business.finance.accrual_issue' and idempotency_key=%s",
            (business, key),
        )
        assert deleted.rowcount == 1
    command = f"/v1/businesses/{business}/financial-documents/commands/{key}"
    reference = {
        "schema_version": 1,
        "operation": "accrual_issue",
        "book_id": str(accruals.ledger.book),
        "subject_id": str(document),
        "revision": 2,
    }
    resolved = await accruals.ledger.client.post(
        command + "/resolve", json=reference, headers=accruals.ledger.auth
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["state"] == "committed"
    replay = await accruals.issue(document, key=key)
    assert replay.status_code == 200
    assert replay.json() == issued.json()
    different = await accruals.issue(document, key=key, entry_date="2026-10-02")
    assert different.status_code == 422
    assert different.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    # The same key was never an invoice command of that document.
    other_operation = await accruals.ledger.client.post(
        command + "/resolve",
        json={**reference, "operation": "invoice_issue"},
        headers=accruals.ledger.auth,
    )
    assert other_operation.json()["state"] == "unresolved"


async def test_off_preserves_accrual_history_and_seals_a_cancelled_draft(
    accruals: AccrualWorld,
    idp: FakeIdp,
) -> None:
    document, key = uuid7(), str(uuid7())
    assert (await accruals.save(document=document)).status_code == 200
    issued = await accruals.issue(document, key=key)
    assert issued.status_code == 200
    config = Config(accruals.ledger.client, idp)
    await config.publish(
        accruals.ledger.user, accruals.ledger.business, 2, ["booking_resources", "counterparties"]
    )
    history = await accruals.ledger.client.get(
        f"{accruals.base}/{document}", headers=accruals.ledger.auth
    )
    assert history.status_code == 200
    assert (await accruals.issue(document, key=key)).json() == issued.json()
    denied = await accruals.save()
    assert denied.status_code == 409
    assert denied.json()["error"]["code"] == "MODULE_DISABLED"
    late, late_key = uuid7(), str(uuid7())
    reference = {
        "schema_version": 1,
        "operation": "accrual_draft",
        "book_id": str(accruals.ledger.book),
        "subject_id": str(late),
        "revision": 1,
    }
    path = f"/v1/businesses/{accruals.ledger.business}/financial-documents/commands/{late_key}"
    cancelled = await accruals.ledger.client.post(
        path + "/cancel", json=reference, headers=accruals.ledger.auth
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["state"] == "cancelled"
    blocked = await accruals.save(document=late, key=late_key)
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "FINANCIAL_COMMAND_CANCELLED"


async def test_withdrawn_readiness_blocks_new_accruals_while_g_still_posts(
    accruals: AccrualWorld,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    feature = modules.MODULES_BY_ID["finance_documents"]
    monkeypatch.setitem(
        modules.MODULES_BY_ID,
        "finance_documents",
        feature.model_copy(update={"enableable": False, "readiness": Readiness.PLANNED}),
    )
    denied = await accruals.save()
    assert denied.status_code == 409
    assert denied.json()["error"]["code"] == "MODULE_NOT_READY"
    unchanged_g = await accruals.ledger.post(accruals.ledger.entry())
    assert unchanged_g.status_code == 200, unchanged_g.text


async def test_two_accrual_issues_wait_on_real_lock_and_only_one_commits(
    accruals: AccrualWorld,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
) -> None:
    document = uuid7()
    assert (await accruals.save(document=document)).status_code == 200
    async with tenant_transaction(app_pool, accruals.ledger.business) as conn:
        await conn.execute("select gba.lock_ledger(%s)", (accruals.ledger.business,))
        pending = [asyncio.create_task(accruals.issue(document)) for _ in range(2)]
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
                pytest.fail("Both accrual requests must be observed waiting on the ledger lock")
        except BaseException:
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            raise
    results = await asyncio.gather(*pending)
    assert sorted(r.status_code for r in results) == [200, 409]
    async with tenant_transaction(app_pool, accruals.ledger.business) as conn:
        row = await (
            await conn.execute(
                "select count(*) from gba.financial_obligations where source_id=%s", (document,)
            )
        ).fetchone()
        assert row == (1,)


_KIND = ("financial_documents", "financial_documents_kind_check")


@pytest.mark.parametrize(
    ("change", "restore"),
    [
        (
            "alter table gba.financial_documents drop constraint financial_documents_kind_check",
            approved_check(*_KIND),
        ),
        (widened_check(*_KIND, "kind = 'credit_note'"), approved_check(*_KIND)),
        (
            approved_check(*_KIND) + " not valid",
            "alter table gba.financial_documents "
            "validate constraint financial_documents_kind_check",
        ),
        (
            "alter table gba.financial_documents alter column kind drop not null",
            "alter table gba.financial_documents alter column kind set not null",
        ),
        (
            widened_check(
                "journal_entries", "journal_entries_source_kind_check", "source_kind = 'refund'"
            ),
            approved_check("journal_entries", "journal_entries_source_kind_check"),
        ),
        (
            widened_check(
                "financial_command_receipts",
                "financial_command_receipts_operation_check",
                "operation = 'accrual_issue '",
            ),
            approved_check(
                "financial_command_receipts", "financial_command_receipts_operation_check"
            ),
        ),
        (
            "create or replace function gba.enforce_invoice_origin() returns trigger "
            "language plpgsql as $$ begin return new; end; $$",
            packaged_function("enforce_invoice_origin"),
        ),
        (
            "create or replace function gba.assert_invoice_consistent"
            "(tenant uuid, book uuid, document uuid) returns void "
            "language plpgsql as $$ begin return; end; $$",
            packaged_function("assert_invoice_consistent"),
        ),
    ],
)
async def test_damaged_accrual_controls_fail_readiness_with_503(
    accruals: AccrualWorld,
    owner_conn: psycopg.Connection,
    change: str,
    restore: str,
) -> None:
    http, auth, base = accruals.ledger.client, accruals.ledger.auth, accruals.ledger.base
    owner_conn.execute(change)
    try:
        result = await http.get(base, headers=auth)
        assert result.status_code == 503, result.text
        assert result.json()["error"]["code"] == "DATABASE_UNAVAILABLE"
        assert (await http.get("/health/ready")).status_code == 503
    finally:
        owner_conn.execute(restore)
    assert (await http.get(base, headers=auth)).status_code == 200
    assert (await http.get("/health/ready")).status_code == 200


@pytest.mark.parametrize(
    ("role", "branch", "expected"),
    [
        ("owner", False, 200),
        ("front_desk", False, 403),
        ("artist", False, 403),
        ("manager", True, 403),
    ],
)
async def test_accrual_routes_keep_company_finance_permissions(
    accruals: AccrualWorld,
    owner_conn: psycopg.Connection,
    world: BookingWorld,
    idp: FakeIdp,
    role: str,
    branch: bool,
    expected: int,
) -> None:
    document = uuid7()
    assert (await accruals.save(document=document)).status_code == 200
    member = seed_user(owner_conn, f"FAKE-H2-{role}-{uuid7()}")
    add_membership(
        owner_conn,
        tenant_id=accruals.ledger.business,
        user_id=member.user_id,
        role=role,
        location_id=world.a.location_id if branch else None,
    )
    auth = idp.bearer(member.subject, email=member.email)
    response = await accruals.ledger.client.get(f"{accruals.base}/{document}", headers=auth)
    assert response.status_code == expected, response.text
    if expected != 200:
        save = await accruals.ledger.client.put(
            f"{accruals.base}/{uuid7()}",
            json=accruals.body(),
            headers={**auth, "Idempotency-Key": str(uuid7())},
        )
        assert save.status_code == 403
