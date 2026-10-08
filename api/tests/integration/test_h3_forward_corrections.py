"""H3 review regressions: SQL, service, immutable mirrors and readiness."""

from collections.abc import Callable, Coroutine
from typing import Any
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.db.pool import RuntimePool, set_tenant_context, tenant_transaction
from tests.integration import test_credit_notes as shared
from tests.integration import test_payment_corrections as correction_shared
from tests.integration.test_credit_notes import CreditWorld, _race
from tests.integration.test_credit_voids import _void, _void_directly
from tests.integration.test_payment_corrections import CorrectionWorld

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
manager_b = shared.manager_b
enabled = shared.enabled
invoices = shared.invoices
payments = shared.payments
credits = shared.credits
corrections = correction_shared.corrections


async def test_case_only_sigma_transfer_must_not_be_counted_twice(
    credits: CreditWorld, corrections: CorrectionWorld, app_pool: RuntimePool
) -> None:
    obligation, _ = await credits.invoice()
    first = await corrections.held([(obligation, "50.00")])
    second = await corrections.held([(obligation, "50.00")])
    refs = ("FAKE-\u039f\u03a3", "fake-\u03bf\u03c2")
    a = await credits.payments.confirm(first, 3, [(obligation, "50.00")], "50.00", refs[0])
    b = await credits.payments.confirm(second, 3, [(obligation, "50.00")], "50.00", refs[1])
    async with tenant_transaction(app_pool, credits.ledger.business) as conn:
        keys = await (
            await conn.execute(
                (
                    "select gba.external_identity_key(%s,'preserve'),gba.external_identity_key(%"
                    "s,'preserve')"
                ),
                refs,
            )
        ).fetchone()
    balance = await credits.settlements.balance(obligation)
    assert a.status_code == 200
    assert b.status_code == 409, "same transfer with upper/lower final sigma was recorded twice"
    assert b.json()["error"]["code"] == "FINANCIAL_SOURCE_ALREADY_RECORDED"
    assert keys is not None
    assert keys[0] == keys[1]
    assert balance["paid"] == "50.00"


async def test_sigma_direct_sql_must_not_count_same_transfer_twice(
    credits: CreditWorld, corrections: CorrectionWorld, app_pool: RuntimePool
) -> None:
    obligation, _ = await credits.invoice()
    await credits.paid(obligation, "50.00", "FAKE-\u039f\u03a3")
    second = await corrections.held([(obligation, "50.00")])
    with pytest.raises(psycopg.errors.UniqueViolation):
        await credits.payments.write_directly(
            app_pool, second, 4, obligation, 5000, "fake-\u03bf\u03c2"
        )
    count = await credits.payments.payment_journals(app_pool)
    assert count == 1, "runtime-role direct SQL counted the case-only duplicate"


async def archive_account(credits: CreditWorld, account: UUID) -> None:
    http, auth, base = (credits.ledger.client, credits.ledger.auth, credits.ledger.base)
    view = await http.get(f"{base}/accounts/{account}", headers=auth)
    assert view.status_code == 200, view.text
    body = view.json()
    archived = await http.put(
        f"{base}/accounts/{account}",
        headers=credits.ledger.headers(),
        json={
            "schema_version": 1,
            "expected_revision": body["revision"],
            "code": body["code"],
            "type": body["type"],
            "name": body["name"],
            "archived": True,
        },
    )
    assert archived.status_code == 200, archived.text


async def test_credit_mirror_can_use_its_archived_historical_counter_account(
    credits: CreditWorld,
) -> None:
    obligation, (line,) = await credits.invoice()
    credit = await credits.credit(obligation, [(line, "20.00")])
    await archive_account(credits, credits.settlements.invoices.counter)
    response = await _void(credits, credit["document_id"])
    assert response.status_code == 200, (
        "a historical credit mirror should not need an active counter account"
    )
    account = await credits.ledger.client.get(
        f"{credits.ledger.base}/accounts/{credits.settlements.invoices.counter}",
        headers=credits.ledger.auth,
    )
    assert account.json()["archived"] is True
    assert await corrections_balances(credits, obligation) == ("0.00", "0.00", "0.00", "100.00")


async def test_payment_mirror_can_use_its_archived_historical_cash_account(
    credits: CreditWorld, corrections: CorrectionWorld
) -> None:
    obligation, _ = await credits.invoice()
    settlement, payment = await corrections.confirmed(
        [(obligation, "70.00")], "70.00", "FAKE-ARCHIVED"
    )
    await archive_account(credits, credits.payments.cash)
    response = await corrections.void(settlement, payment, 4)
    assert response.status_code == 200, (
        "a historical payment mirror should not need an active cash account"
    )
    account = await credits.ledger.client.get(
        f"{credits.ledger.base}/accounts/{credits.payments.cash}", headers=credits.ledger.auth
    )
    assert account.json()["archived"] is True
    assert await corrections.balances(obligation) == ("0.00", "0.00", "70.00", "30.00")


async def test_archived_account_refuses_replacement_and_ordinary_posting(
    credits: CreditWorld, corrections: CorrectionWorld
) -> None:
    obligation, _ = await credits.invoice()
    settlement, payment = await corrections.confirmed(
        [(obligation, "70.00")], "70.00", "FAKE-ARCHIVE-REPLACEMENT"
    )
    await archive_account(credits, credits.payments.cash)
    replacement = await corrections.correct(
        settlement, payment, 4, [(obligation, "60.00")], "60.00"
    )
    assert replacement.status_code == 409
    assert await corrections.balances(obligation) == ("70.00", "0.00", "0.00", "30.00")
    ordinary = await credits.ledger.post(
        credits.ledger.entry(
            lines=[
                {"account_id": str(credits.payments.cash), "side": "debit", "amount": "1.00"},
                {
                    "account_id": str(credits.settlements.invoices.control),
                    "side": "credit",
                    "amount": "1.00",
                },
            ]
        )
    )
    assert ordinary.status_code == 409
    assert ordinary.json()["error"]["code"] == "LEDGER_STATE_INVALID"


async def test_sql_archived_mirror_refuses_changed_amount(
    credits: CreditWorld, app_pool: RuntimePool
) -> None:
    obligation, (line,) = await credits.invoice()
    credit = await credits.credit(obligation, [(line, "20.00")])
    await archive_account(credits, credits.settlements.invoices.counter)
    with pytest.raises(psycopg.errors.CheckViolation, match="mirror"):
        async with tenant_transaction(app_pool, credits.ledger.business) as conn:
            await _void_directly(credits, conn, credit["document_id"], shrink=1)
    assert await corrections_balances(credits, obligation) == ("0.00", "20.00", "0.00", "80.00")


@pytest.mark.parametrize("scope", ["foreign_tenant", "foreign_book", "replacement", "manual"])
async def test_mirror_helper_refuses_untrusted_scope_or_origin(
    credits: CreditWorld, app_pool: RuntimePool, scope: str
) -> None:
    obligation, (line,) = await credits.invoice()
    credit = await credits.credit(obligation, [(line, "20.00")])
    tenant = uuid7() if scope == "foreign_tenant" else credits.ledger.business
    book = uuid7() if scope == "foreign_book" else credits.ledger.book
    kind = (
        "manual"
        if scope == "manual"
        else "payment_correction"
        if scope == "replacement"
        else "credit_void"
    )
    async with tenant_transaction(app_pool, credits.ledger.business) as conn:
        await _void_directly(credits, conn, credit["document_id"])
        found = await (
            await conn.execute(
                "select void_entry_id from gba.financial_document_versions "
                "where document_id=%s and state='voided'",
                (UUID(str(credit["document_id"])),),
            )
        ).fetchone()
        assert found is not None
        entry = UUID(str(found[0]))
        valid = await (
            await conn.execute(
                "select gba.financial_mirror_original(%s,%s,%s,'credit_void')",
                (credits.ledger.business, credits.ledger.book, entry),
            )
        ).fetchone()
        assert valid == (UUID(str(credit["entry_id"])),)
        if scope == "foreign_tenant":
            await set_tenant_context(conn, tenant)
        row = await (
            await conn.execute(
                "select gba.financial_mirror_original(%s,%s,%s,%s)",
                (credits.ledger.business, book, entry, kind),
            )
        ).fetchone()
        await set_tenant_context(conn, credits.ledger.business)
    assert row is not None
    assert row[0] is None


async def test_replacement_to_open_account_can_mirror_archived_old_account(
    credits: CreditWorld, corrections: CorrectionWorld
) -> None:
    obligation, _ = await credits.invoice()
    settlement, payment = await corrections.confirmed(
        [(obligation, "70.00")], "70.00", "FAKE-NEW-CASH"
    )
    await archive_account(credits, credits.payments.cash)
    cash = uuid7()
    created = await credits.ledger.client.put(
        f"{credits.ledger.base}/accounts/{cash}",
        headers=credits.ledger.headers(),
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "code": "1020",
            "type": "asset",
            "name": "FAKE replacement bank",
            "archived": False,
        },
    )
    assert created.status_code == 200
    corrected = await corrections.correct(
        settlement, payment, 4, [(obligation, "60.00")], "60.00", cash_account_id=str(cash)
    )
    assert corrected.status_code == 200, corrected.text
    assert await corrections.balances(obligation) == ("60.00", "0.00", "10.00", "30.00")
    archived = await credits.ledger.client.get(
        f"{credits.ledger.base}/accounts/{credits.payments.cash}", headers=credits.ledger.auth
    )
    assert archived.json()["archived"] is True


@pytest.mark.parametrize("archive_first", [True, False])
async def test_archive_and_credit_void_serialize_on_ledger_lock(
    credits: CreditWorld, app_pool: RuntimePool, owner_conn: psycopg.Connection, archive_first: bool
) -> None:
    obligation, (line,) = await credits.invoice()
    credit = await credits.credit(obligation, [(line, "20.00")])
    account_id = credits.settlements.invoices.counter
    account = await credits.ledger.client.get(
        f"{credits.ledger.base}/accounts/{account_id}", headers=credits.ledger.auth
    )
    body = account.json()

    async def archive() -> httpx.Response:
        return await credits.ledger.client.put(
            f"{credits.ledger.base}/accounts/{account_id}",
            headers=credits.ledger.headers(),
            json={
                "schema_version": 1,
                "expected_revision": body["revision"],
                "code": body["code"],
                "type": body["type"],
                "name": body["name"],
                "archived": True,
            },
        )

    async def void() -> httpx.Response:
        return await _void(credits, credit["document_id"])

    calls: list[Callable[[], Coroutine[Any, Any, httpx.Response]]] = (
        [archive, void] if archive_first else [void, archive]
    )
    responses = await _race(credits, app_pool, owner_conn, calls)
    assert [response.status_code for response in responses] == [200, 200]
    assert await corrections_balances(credits, obligation) == ("0.00", "0.00", "0.00", "100.00")


@pytest.mark.parametrize(
    "helper",
    ["credit_voided(uuid,uuid,uuid)", "financial_mirror_original(uuid,uuid,uuid,text)"],
)
async def test_readiness_refuses_missing_helper_execute(
    credits: CreditWorld, owner_conn: psycopg.Connection, app_pool: RuntimePool, helper: str
) -> None:
    http, auth, base = (credits.ledger.client, credits.ledger.auth, credits.ledger.base)
    owner_conn.execute(f"revoke execute on function gba.{helper} from gba_runtime")
    try:
        ready = await http.get("/health/ready")
        ledger = await http.get(base, headers=auth)
        denied = None
        try:
            async with tenant_transaction(app_pool, credits.ledger.business) as conn:
                if helper.startswith("credit_voided"):
                    await conn.execute(
                        "select gba.credit_voided(%s,%s,%s)",
                        (credits.ledger.business, credits.ledger.book, uuid7()),
                    )
                else:
                    await conn.execute(
                        "select gba.financial_mirror_original(%s,%s,%s,'credit_void')",
                        (credits.ledger.business, credits.ledger.book, uuid7()),
                    )
        except psycopg.errors.InsufficientPrivilege as exc:
            denied = exc.sqlstate
        assert denied == "42501"
        assert ready.status_code == 503, "helper is unusable by runtime but readiness reports ready"
        assert ledger.status_code == 503
    finally:
        owner_conn.execute(f"grant execute on function gba.{helper} to gba_runtime")


async def test_readiness_refuses_wrong_transaction_default(
    credits: CreditWorld, owner_conn: psycopg.Connection
) -> None:
    http = credits.ledger.client
    owner_conn.execute(
        "alter table gba.financial_document_versions alter column created_transactio"
        "n set default '0'::xid8"
    )
    try:
        ready = await http.get("/health/ready")
        saved = await credits.settlements.invoices.save()
        assert ready.status_code == 503, (
            "transaction default breaks writes but readiness reports ready"
        )
        assert saved.status_code == 503
    finally:
        owner_conn.execute(
            "alter table gba.financial_document_versions alter column created_transactio"
            "n set default pg_catalog.pg_current_xact_id()"
        )


async def test_sql_void_event_cannot_precede_original_confirmation(
    credits: CreditWorld, corrections: CorrectionWorld, app_pool: RuntimePool
) -> None:
    obligation, _ = await credits.invoice()
    settlement = await corrections.held([(obligation, "100.00")])
    with pytest.raises(
        psycopg.errors.CheckViolation, match="follows its previous confirmation event"
    ):
        await _write_out_of_order(credits, app_pool, obligation, settlement)
    assert await corrections.balances(obligation) == ("0.00", "0.00", "100.00", "0.00")


async def test_sql_credit_line_limit_must_match_read_contract(
    credits: CreditWorld, app_pool: RuntimePool
) -> None:
    obligation, (original_line,) = await credits.invoice()
    with pytest.raises(psycopg.errors.CheckViolation, match="at most 198 lines"):
        await _write_oversized_credit(credits, app_pool, obligation, original_line)
    assert await corrections_balances(credits, obligation) == ("0.00", "0.00", "0.00", "100.00")


async def corrections_balances(credits: CreditWorld, obligation: UUID) -> tuple[object, ...]:
    balance = await credits.settlements.balance(obligation)
    return (balance["paid"], balance["credited"], balance["reserved"], balance["available"])


async def _write_out_of_order(
    credits: CreditWorld, app_pool: RuntimePool, obligation: UUID, settlement: UUID
) -> UUID:
    tenant, book, actor = (
        credits.ledger.business,
        credits.ledger.book,
        credits.ledger.user.user_id,
    )
    payment, original, reversal = (uuid7(), uuid7(), uuid7())
    async with tenant_transaction(app_pool, tenant) as conn:
        await conn.execute(
            (
                "insert into gba.settlement_events (tenant_id,book_id,settlement_id,sequence"
                ",kind,created_by) values (%s,%s,%s,4,'payment_voided',%s),(%s,%s,%s,5,'conf"
                "irmed',%s)"
            ),
            (tenant, book, settlement, actor, tenant, book, settlement, actor),
        )
        await conn.execute(
            (
                "insert into gba.external_payments (tenant_id,book_id,id,settlement_id,seque"
                "nce,direction,currency,amount_minor,actual_external_date,entry_date,cash_ac"
                "count_id,source_account_alias,external_reference,attestation,entry_id,creat"
                "ed_by) values (%s,%s,%s,%s,5,'receivable','USD',5000,'2026-10-02','2026-10-"
                "02',%s,'FAKE bank','FAKE sequence inversion','manual_attestation',%s,%s)"
            ),
            (tenant, book, payment, settlement, credits.payments.cash, original, actor),
        )
        await conn.execute(
            (
                "insert into gba.external_payment_allocations (tenant_id,book_id,payment_id,"
                "line_no,obligation_id,amount_minor) values (%s,%s,%s,1,%s,5000)"
            ),
            (tenant, book, payment, obligation),
        )
        await conn.execute(
            (
                "insert into gba.journal_entries (tenant_id,id,book_id,entry_date,currency,s"
                "ource_kind,source_id,created_by) values (%s,%s,%s,'2026-10-02','USD','payme"
                "nt',%s,%s)"
            ),
            (tenant, original, book, str(payment), actor),
        )
        await conn.execute(
            (
                "insert into gba.journal_lines (tenant_id,entry_id,line_no,book_id,account_i"
                "d,side,amount_minor) values (%s,%s,1,%s,%s,'debit',5000),(%s,%s,2,%s,%s,'cr"
                "edit',5000)"
            ),
            (
                tenant,
                original,
                book,
                credits.payments.cash,
                tenant,
                original,
                book,
                credits.settlements.invoices.control,
            ),
        )
        await conn.execute(
            (
                "insert into gba.external_payment_revisions (tenant_id,book_id,payment_id,re"
                "vision,settlement_id,sequence,kind,entry_date,attestation,reason,evidence_s"
                "ource,reversal_entry_id,created_by) values (%s,%s,%s,2,%s,4,'voided','2026-"
                "10-04','attested_erroneous_confirmation','FAKE reverse chronology','FAKE re"
                "view',%s,%s)"
            ),
            (tenant, book, payment, settlement, reversal, actor),
        )
        await conn.execute(
            (
                "insert into gba.journal_entries (tenant_id,id,book_id,entry_date,currency,s"
                "ource_kind,source_id,created_by) values (%s,%s,%s,'2026-10-04','USD','payme"
                "nt_correction',%s,%s)"
            ),
            (tenant, reversal, book, f"{payment}:2:reversal", actor),
        )
        await conn.execute(
            (
                "insert into gba.journal_lines (tenant_id,entry_id,line_no,book_id,account_i"
                "d,side,amount_minor) select tenant_id,%s,line_no,book_id,account_id,case si"
                "de when 'debit' then 'credit' else 'debit' end,amount_minor from gba.journa"
                "l_lines where tenant_id=%s and entry_id=%s"
            ),
            (reversal, tenant, original),
        )
        await conn.execute("set constraints all immediate")
    return payment


async def _write_oversized_credit(
    credits: CreditWorld, app_pool: RuntimePool, obligation: UUID, original_line: UUID
) -> UUID:
    tenant, book, actor = (
        credits.ledger.business,
        credits.ledger.book,
        credits.ledger.user.user_id,
    )
    party = credits.settlements.invoices.party
    control, counter = (credits.settlements.invoices.control, credits.settlements.invoices.counter)
    document, entry = (uuid7(), uuid7())
    line_ids = [uuid7() for _ in range(199)]
    async with tenant_transaction(app_pool, tenant) as conn:
        await conn.execute(
            (
                "insert into gba.financial_documents (tenant_id,book_id,id,created_by,kind) "
                "values (%s,%s,%s,%s,'credit_note')"
            ),
            (tenant, book, document, actor),
        )
        for revision in (1, 2):
            issued = revision == 2
            await conn.execute(
                (
                    "insert into gba.financial_document_versions (tenant_id,book_id,document_id,"
                    "revision,state,direction,counterparty_id,counterparty_revision,currency,inv"
                    "oice_date,control_account_id,title,number,principal_minor,line_count,credit"
                    "ed_obligation_id,entry_id,issued_on,attestation,applied_minor,created_by) v"
                    "alues (%s,%s,%s,%s,%s,'receivable',%s,1,'USD','2026-10-03',%s,'FAKE SQL 199"
                    " lines','FAKE-SQL-199',199,199,%s,%s,%s,%s,%s,%s)"
                ),
                (
                    tenant,
                    book,
                    document,
                    revision,
                    "issued" if issued else "draft",
                    party,
                    control,
                    obligation,
                    entry if issued else None,
                    "2026-10-03" if issued else None,
                    "confirmed_account_treatment" if issued else None,
                    199 if issued else None,
                    actor,
                ),
            )
            for number, line_id in enumerate(line_ids, 1):
                await conn.execute(
                    (
                        "insert into gba.financial_document_lines "
                        "(tenant_id,book_id,document_id,rev"
                        "ision,line_no,line_id,credited_line_id,counter_account_id,description,amoun"
                        "t_minor) values (%s,%s,%s,%s,%s,%s,%s,%s,'FAKE one minor',1)"
                    ),
                    (tenant, book, document, revision, number, line_id, original_line, counter),
                )
        await conn.execute(
            (
                "insert into gba.journal_entries (tenant_id,id,book_id,entry_date,currency,s"
                "ource_kind,source_id,created_by) values (%s,%s,%s,'2026-10-03','USD','credi"
                "t',%s,%s)"
            ),
            (tenant, entry, book, str(document), actor),
        )
        for number in range(1, 200):
            await conn.execute(
                (
                    "insert into gba.journal_lines (tenant_id,entry_id,line_no,book_id,account_i"
                    "d,side,amount_minor) values (%s,%s,%s,%s,%s,'debit',1)"
                ),
                (tenant, entry, number, book, counter),
            )
        await conn.execute(
            (
                "insert into gba.journal_lines (tenant_id,entry_id,line_no,book_id,account_i"
                "d,side,amount_minor) values (%s,%s,200,%s,%s,'credit',199)"
            ),
            (tenant, entry, book, control),
        )
        await conn.execute("set constraints all immediate")
    return document
