"""H3 credit voids: mirror the credit, undo its C and cancel its untouched refund."""

from collections.abc import Callable, Coroutine
from typing import Any
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.business import modules
from gorgona_booking.business.readiness_registry import Readiness
from gorgona_booking.db.pool import RuntimeConnection, RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import add_membership, owner_tenant_transaction
from tests.integration import test_credit_notes as credit_shared
from tests.integration.booking_support import BookingWorld
from tests.integration.configuration_support import Config
from tests.integration.seed import seed_user
from tests.integration.test_credit_notes import CreditWorld, _race
from tests.integration.test_invoice_issue import approved_check, packaged_function
from tests.integration.test_payment_corrections import CorrectionWorld
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = credit_shared.client
idp = credit_shared.idp
manager_a = credit_shared.manager_a
manager_b = credit_shared.manager_b
enabled = credit_shared.enabled
invoices = credit_shared.invoices
payments = credit_shared.payments
credits = credit_shared.credits

_VOID = {
    "schema_version": 1,
    "entry_date": "2026-10-04",
    "attestation": "attested_erroneous_credit",
    "reason": "FAKE the credit was issued to the wrong customer",
    "evidence_source": "FAKE customer service ticket",
}


async def _void(
    credits: CreditWorld,
    document: object,
    revision: int = 2,
    *,
    key: str | None = None,
    headers: dict[str, str] | None = None,
    **changes: object,
) -> httpx.Response:
    return await credits.ledger.client.post(
        f"{credits.base}/{document}/void",
        json={**_VOID, "expected_revision": revision, **changes},
        headers=headers or credits.ledger.headers(key),
    )


async def _entry(credits: CreditWorld, entry: object) -> dict[str, Any]:
    response = await credits.ledger.client.get(
        f"{credits.ledger.base}/entries/{entry}",
        params={"schema_version": 2},
        headers=credits.ledger.auth,
    )
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


async def _balances(credits: CreditWorld, obligation: UUID) -> tuple[object, ...]:
    balance = await credits.settlements.balance(obligation)
    return balance["paid"], balance["credited"], balance["reserved"], balance["available"]


async def _refunded(credits: CreditWorld, reference: str) -> tuple[UUID, UUID, dict[str, Any]]:
    """Invoice 100, paid 70, credit 50: C 30 and an untouched refund obligation of 20."""
    obligation, (line,) = await credits.invoice()
    await credits.paid(obligation, "70.00", reference)
    view = await credits.credit(obligation, [(line, "50.00")], refund=credits.chart["2100"])
    return obligation, UUID(str(view["refund_obligation_id"])), view


async def test_credit_void_route_requires_authentication(client: httpx.AsyncClient) -> None:
    path = f"/v1/businesses/{uuid7()}/financial-documents/books/{uuid7()}/credits/{uuid7()}/void"
    assert (await client.post(path, json={})).status_code == 401


async def test_void_mirrors_an_unpaid_credit_and_restores_its_line(
    credits: CreditWorld,
    app_pool: RuntimePool,
) -> None:
    obligation, (line,) = await credits.invoice()
    view = await credits.credit(obligation, [(line, "40.00")])
    document = view["document_id"]
    key = str(uuid7())
    voided = await _void(credits, document, key=key)
    assert voided.status_code == 200, voided.text
    result = voided.json()
    assert (result["state"], result["revision"]) == ("voided", 3)
    # Every issued fact stays; the void adds its own journal, date and reason.
    for field in ("entry_id", "issued_on", "applied", "refund", "total", "lines"):
        assert result[field] == view[field]
    assert (result["voided_on"], result["void_reason"]) == ("2026-10-04", _VOID["reason"])
    assert result["void_evidence_source"] == _VOID["evidence_source"]
    assert (await _void(credits, document, key=key)).json() == result
    assert await _balances(credits, obligation) == ("0.00", "0.00", "0.00", "100.00")
    mirror = await _entry(credits, result["void_entry_id"])
    assert (mirror["source_kind"], mirror["source_id"], mirror["entry_date"]) == (
        "credit_void",
        str(document),
        "2026-10-04",
    )
    counter, control = credits.settlements.invoices.counter, credits.settlements.invoices.control
    assert [(r["account_id"], r["side"], r["amount"]) for r in mirror["lines"]] == [
        (str(counter), "credit", "40.00"),
        (str(control), "debit", "40.00"),
    ]
    closing = await credits.closing()
    assert closing["4000"] == ("0.00", "100.00")
    assert closing["1200"] == ("100.00", "0.00")
    # The history keeps the issued version; a void is final.
    issued = await credits.ledger.client.get(
        f"{credits.base}/{document}", params={"revision": 2}, headers=credits.ledger.auth
    )
    assert issued.json()["state"] == "issued"
    again = await _void(credits, document, 3)
    assert again.status_code == 409, again.text
    assert again.json()["error"]["code"] == "FINANCIAL_STATE_INVALID"
    listed = await credits.ledger.client.get(credits.base, headers=credits.ledger.auth)
    (item,) = listed.json()["items"]
    assert (item["state"], item["voided_on"]) == ("voided", "2026-10-04")
    # The line of 100 is whole again.
    whole = await credits.credit(obligation, [(line, "100.00")])
    assert whole["applied"] == "100.00"
    reverse = await credits.ledger.client.post(
        f"{credits.ledger.base}/entries/{result['void_entry_id']}/reverse",
        json={"schema_version": 1, "reversal_entry_id": str(uuid7()), "entry_date": "2026-10-05"},
        headers=credits.ledger.headers(),
    )
    assert reverse.status_code == 409, reverse.text
    assert reverse.json()["error"]["code"] == "LEDGER_STATE_INVALID"
    legacy = await credits.ledger.client.get(
        f"{credits.ledger.base}/entries/{result['void_entry_id']}", headers=credits.ledger.auth
    )
    assert legacy.json()["error"]["code"] == "JOURNAL_VERSION_REQUIRED"
    voids = await credits.count(
        app_pool, "select count(*) from gba.journal_entries where source_kind='credit_void'"
    )
    assert voids == 1


async def test_void_cancels_an_untouched_refund_and_undoes_c(credits: CreditWorld) -> None:
    obligation, refund, view = await _refunded(credits, "FAKE-CV-1")
    voided = await _void(credits, view["document_id"])
    assert voided.status_code == 200, voided.text
    assert await _balances(credits, obligation) == ("70.00", "0.00", "0.00", "30.00")
    # The cancelled refund can never be reserved or paid.
    assert await _balances(credits, refund) == ("0.00", "20.00", "0.00", "0.00")
    world = credits.settlements
    settlement = uuid7()
    prepared = await world.prepare(settlement, [(refund, "1.00")], direction="payable")
    assert prepared.status_code == 200, prepared.text
    assert (await world.act(settlement, "approve", 1)).status_code == 200
    reserved = await world.act(settlement, "reserve", 2)
    assert reserved.status_code == 409, reserved.text
    assert reserved.json()["error"]["code"] == "FINANCIAL_CAP_EXCEEDED"
    mirror = await _entry(credits, voided.json()["void_entry_id"])
    counter, control = credits.settlements.invoices.counter, credits.settlements.invoices.control
    assert [(r["account_id"], r["side"], r["amount"]) for r in mirror["lines"]] == [
        (str(counter), "credit", "50.00"),
        (str(control), "debit", "30.00"),
        (str(credits.chart["2100"]), "debit", "20.00"),
    ]
    closing = await credits.closing()
    assert closing["2100"] == ("0.00", "0.00")
    assert closing["1200"] == ("30.00", "0.00")


async def test_a_touched_refund_is_never_undone(credits: CreditWorld) -> None:
    world = credits.settlements
    # Reserved: release first.
    _, refund, view = await _refunded(credits, "FAKE-CV-2")
    held = uuid7()
    assert (await world.prepare(held, [(refund, "20.00")], direction="payable")).status_code == 200
    for action, sequence in (("approve", 1), ("reserve", 2)):
        assert (await world.act(held, action, sequence)).status_code == 200
    reserved = await _void(credits, view["document_id"])
    assert reserved.status_code == 409, reserved.text
    assert reserved.json()["error"]["code"] == "FINANCIAL_STATE_INVALID"
    # Sent with an unknown outcome: reconcile.
    assert (await world.act(held, "sent", 3)).status_code == 200
    unknown = await _void(credits, view["document_id"])
    assert unknown.status_code == 409, unknown.text
    assert unknown.json()["error"]["code"] == "FINANCIAL_RECONCILIATION_REQUIRED"
    assert unknown.json()["error"]["details"]["settlement_id"] == str(held)
    resolved = await world.act(
        held,
        "release",
        4,
        resolution="attested_no_payment",
        reason="FAKE the refund transfer was never made",
        evidence_source="FAKE bank statement",
    )
    assert resolved.status_code == 200, resolved.text
    assert (await _void(credits, view["document_id"])).status_code == 200
    # Paid: a real refund is never undone.
    _, paid_refund, paid_view = await _refunded(credits, "FAKE-CV-3")
    settlement = uuid7()
    assert (
        await world.prepare(settlement, [(paid_refund, "20.00")], direction="payable")
    ).status_code == 200
    for action, sequence in (("approve", 1), ("reserve", 2)):
        assert (await world.act(settlement, action, sequence)).status_code == 200
    confirmed = await credits.payments.confirm(
        settlement,
        3,
        [(paid_refund, "20.00")],
        "20.00",
        "FAKE-CV-REFUND",
        changes={"entry_date": "2026-10-04", "actual_external_date": "2026-10-04"},
    )
    assert confirmed.status_code == 200, confirmed.text
    paid = await _void(credits, paid_view["document_id"])
    assert paid.status_code == 409, paid.text
    assert paid.json()["error"]["code"] == "FINANCIAL_RECONCILIATION_REQUIRED"
    assert paid.json()["error"]["details"]["obligation_id"] == str(paid_refund)
    assert await _balances(credits, paid_refund) == ("20.00", "0.00", "0.00", "0.00")


async def test_a_later_refunded_credit_keeps_the_credit_it_relied_on(
    credits: CreditWorld,
) -> None:
    obligation, (line,) = await credits.invoice()
    await credits.paid(obligation, "70.00", "FAKE-CV-4")
    first = await credits.credit(obligation, [(line, "20.00")])
    second = await credits.credit(obligation, [(line, "30.00")], refund=credits.chart["2100"])
    assert (first["applied"], second["applied"], second["refund"]) == ("20.00", "10.00", "20.00")
    blocked = await _void(credits, first["document_id"])
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["error"]["code"] == "FINANCIAL_RECONCILIATION_REQUIRED"
    assert blocked.json()["error"]["details"]["document_id"] == second["document_id"]
    assert (await _void(credits, second["document_id"])).status_code == 200
    assert (await _void(credits, first["document_id"])).status_code == 200
    assert await _balances(credits, obligation) == ("70.00", "0.00", "0.00", "30.00")


async def test_a_voided_credit_no_longer_holds_its_payments(credits: CreditWorld) -> None:
    corrections = CorrectionWorld(credits)
    obligation, (line,) = await credits.invoice()
    settlement, payment = await corrections.confirmed([(obligation, "70.00")], "70.00", "FAKE-CV-5")
    view = await credits.credit(obligation, [(line, "10.00")])
    held = await corrections.void(settlement, payment, 4)
    assert held.status_code == 409, held.text
    assert held.json()["error"]["code"] == "FINANCIAL_RECONCILIATION_REQUIRED"
    assert (await _void(credits, view["document_id"])).status_code == 200
    released = await corrections.void(settlement, payment, 4)
    assert released.status_code == 200, released.text
    assert await _balances(credits, obligation) == ("0.00", "0.00", "70.00", "30.00")


async def test_void_dates_and_closed_month(credits: CreditWorld, app_pool: RuntimePool) -> None:
    obligation, (line,) = await credits.invoice()
    view = await credits.credit(obligation, [(line, "10.00")])
    early = await _void(credits, view["document_id"], entry_date="2026-10-02")
    assert early.status_code == 422, early.text
    assert early.json()["error"]["code"] == "LEDGER_DATE_INVALID"
    stale = await _void(credits, view["document_id"], 3)
    assert stale.status_code == 409, stale.text
    assert stale.json()["error"]["details"]["revision"] == 2
    assert (await _void(credits, uuid7())).status_code == 404
    closed = await credits.ledger.client.post(
        f"{credits.ledger.base}/periods/2026-10/close",
        json={"schema_version": 1, "expected_sequence": 0},
        headers=credits.ledger.headers(),
    )
    assert closed.status_code == 200, closed.text
    denied = await _void(credits, view["document_id"])
    assert denied.status_code == 409, denied.text
    assert denied.json()["error"]["code"] == "LEDGER_PERIOD_CLOSED"
    assert await _balances(credits, obligation) == ("0.00", "10.00", "0.00", "90.00")
    voids = await credits.count(
        app_pool, "select count(*) from gba.journal_entries where source_kind='credit_void'"
    )
    assert voids == 0


@pytest.mark.parametrize("void_first", [True, False])
async def test_void_and_refund_reserve_wait_on_one_lock(
    credits: CreditWorld,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
    void_first: bool,
) -> None:
    _, refund, view = await _refunded(credits, "FAKE-CV-RACE")
    world = credits.settlements
    settlement = uuid7()
    assert (
        await world.prepare(settlement, [(refund, "20.00")], direction="payable")
    ).status_code == 200
    assert (await world.act(settlement, "approve", 1)).status_code == 200
    calls: list[Callable[[], Coroutine[Any, Any, httpx.Response]]] = [
        lambda: _void(credits, view["document_id"]),
        lambda: world.act(settlement, "reserve", 2),
    ]
    first, second = await _race(credits, app_pool, owner_conn, calls if void_first else calls[::-1])
    assert first.status_code == 200, first.text
    assert second.status_code == 409, second.text
    if void_first:
        assert second.json()["error"]["code"] == "FINANCIAL_CAP_EXCEEDED"
        assert await _balances(credits, refund) == ("0.00", "20.00", "0.00", "0.00")
    else:
        assert second.json()["error"]["code"] == "FINANCIAL_STATE_INVALID"
        assert await _balances(credits, refund) == ("0.00", "0.00", "20.00", "0.00")


async def _void_directly(
    credits: CreditWorld,
    conn: RuntimeConnection,
    document: object,
    *,
    revision: int = 3,
    title: str | None = None,
    shrink: int = 0,
) -> None:
    """A complete void written by SQL alone, in the order the service uses."""
    business, book, user = credits.ledger.business, credits.ledger.book, credits.ledger.user.user_id
    entry = uuid7()
    await conn.execute(
        "insert into gba.financial_document_versions (tenant_id,book_id,document_id,revision,"
        "state,direction,counterparty_id,counterparty_revision,currency,invoice_date,due_date,"
        "control_account_id,title,number,principal_minor,line_count,credited_obligation_id,"
        "entry_id,obligation_id,issued_on,attestation,applied_minor,refund_control_account_id,"
        "void_entry_id,voided_on,void_reason,void_evidence_source,created_by) "
        "select tenant_id,book_id,document_id,%s,'voided',direction,counterparty_id,"
        "counterparty_revision,currency,invoice_date,due_date,control_account_id,"
        "coalesce(%s,title),number,principal_minor,line_count,credited_obligation_id,entry_id,"
        "obligation_id,issued_on,attestation,applied_minor,refund_control_account_id,%s,"
        "'2026-10-04','FAKE SQL void','FAKE SQL evidence',%s from gba.financial_document_versions "
        "where tenant_id=%s and book_id=%s and document_id=%s and revision=2",
        (revision, title, entry, user, business, book, document),
    )
    await conn.execute(
        "insert into gba.financial_document_lines (tenant_id,book_id,document_id,revision,"
        "line_no,line_id,credited_line_id,counter_account_id,description,amount_minor,reason,"
        "reference_entry_id) select tenant_id,book_id,document_id,%s,line_no,line_id,"
        "credited_line_id,counter_account_id,description,amount_minor,reason,reference_entry_id "
        "from gba.financial_document_lines where tenant_id=%s and book_id=%s "
        "and document_id=%s and revision=2",
        (revision, business, book, document),
    )
    await conn.execute(
        "insert into gba.journal_entries "
        "(tenant_id,id,book_id,entry_date,currency,source_kind,source_id,created_by) "
        "values (%s,%s,%s,'2026-10-04','USD','credit_void',%s,%s)",
        (business, entry, book, str(document), user),
    )
    await conn.execute(
        "insert into gba.journal_lines "
        "(tenant_id,entry_id,line_no,book_id,account_id,side,amount_minor) "
        "select j.tenant_id,%s,j.line_no,j.book_id,j.account_id,"
        "case j.side when 'debit' then 'credit' else 'debit' end,j.amount_minor-%s "
        "from gba.journal_lines j join gba.financial_document_versions v "
        "on v.tenant_id=j.tenant_id and v.entry_id=j.entry_id "
        "where v.tenant_id=%s and v.book_id=%s and v.document_id=%s and v.revision=2",
        (entry, shrink, business, book, document),
    )
    await conn.execute("set constraints all immediate")


async def test_sql_rechecks_a_void_its_mirror_and_its_refund(
    credits: CreditWorld,
    app_pool: RuntimePool,
) -> None:
    business = credits.ledger.business
    obligation, (line,) = await credits.invoice()
    view = await credits.credit(obligation, [(line, "40.00")])
    document = view["document_id"]
    cases: tuple[tuple[str, dict[str, Any]], ...] = (
        ("must mirror the credit journal", {"shrink": 100}),
        ("a void preserves the issued credit note", {"title": "FAKE other title"}),
        ("only an issued credit note is voided", {"revision": 4}),
    )
    for message, values in cases:
        with pytest.raises(psycopg.errors.CheckViolation, match=message):
            async with tenant_transaction(app_pool, business) as conn:
                await _void_directly(credits, conn, document, **values)
    assert await _balances(credits, obligation) == ("0.00", "40.00", "0.00", "60.00")
    async with tenant_transaction(app_pool, business) as conn:
        await _void_directly(credits, conn, document)
    assert await _balances(credits, obligation) == ("0.00", "0.00", "0.00", "100.00")
    with pytest.raises(psycopg.errors.CheckViolation, match="only an issued credit note"):
        async with tenant_transaction(app_pool, business) as conn:
            await _void_directly(credits, conn, document, revision=4)
    # A reserved refund stays, whoever writes.
    _, refund, refunded = await _refunded(credits, "FAKE-CV-SQL")
    settlement = uuid7()
    world = credits.settlements
    assert (
        await world.prepare(settlement, [(refund, "20.00")], direction="payable")
    ).status_code == 200
    for action, sequence in (("approve", 1), ("reserve", 2)):
        assert (await world.act(settlement, action, sequence)).status_code == 200
    with pytest.raises(psycopg.errors.CheckViolation, match="reconciled separately"):
        async with tenant_transaction(app_pool, business) as conn:
            await _void_directly(credits, conn, refunded["document_id"])
    # An invoice is never voided.
    invoice = await credits.settlements.balance(obligation)
    with pytest.raises(psycopg.errors.CheckViolation, match="only an issued credit note"):
        async with tenant_transaction(app_pool, business) as conn:
            await _void_directly(credits, conn, invoice["source_id"])


async def test_voided_history_stays_unchanged(
    credits: CreditWorld,
    owner_conn: psycopg.Connection,
) -> None:
    obligation, (line,) = await credits.invoice()
    view = await credits.credit(obligation, [(line, "10.00")])
    assert (await _void(credits, view["document_id"])).status_code == 200
    with (
        pytest.raises(psycopg.errors.CheckViolation, match="kept unchanged"),
        owner_tenant_transaction(owner_conn, credits.ledger.business),
    ):
        owner_conn.execute(
            "update gba.financial_document_versions set void_reason='FAKE rewritten' "
            "where document_id=%s and state='voided'",
            (UUID(str(view["document_id"])),),
        )
    assert await _balances(credits, obligation) == ("0.00", "0.00", "0.00", "100.00")


async def test_off_and_withdrawn_readiness_block_voids_but_keep_history(
    credits: CreditWorld,
    idp: FakeIdp,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    obligation, (line,) = await credits.invoice()
    view = await credits.credit(obligation, [(line, "10.00")])
    feature = modules.MODULES_BY_ID["finance_documents"]
    with monkeypatch.context() as patch:
        patch.setitem(
            modules.MODULES_BY_ID,
            "finance_documents",
            feature.model_copy(update={"enableable": False, "readiness": Readiness.PLANNED}),
        )
        unready = await _void(credits, view["document_id"])
        assert unready.status_code == 409
        assert unready.json()["error"]["code"] == "MODULE_NOT_READY"
    config = Config(credits.ledger.client, idp)
    await config.publish(credits.ledger.user, credits.ledger.business, 2, ["booking_resources"])
    off = await _void(credits, view["document_id"])
    assert off.status_code == 409, off.text
    assert off.json()["error"]["code"] == "MODULE_DISABLED"
    read = await credits.ledger.client.get(
        f"{credits.base}/{view['document_id']}", headers=credits.ledger.auth
    )
    assert read.json() == view
    assert await _balances(credits, obligation) == ("0.00", "10.00", "0.00", "90.00")


async def test_void_replay_recovery_and_cancel_before_late_original(
    credits: CreditWorld,
    owner_conn: psycopg.Connection,
) -> None:
    obligation, (line,) = await credits.invoice()
    view = await credits.credit(obligation, [(line, "10.00")])
    other = await credits.credit(obligation, [(line, "5.00")])
    key = str(uuid7())
    voided = await _void(credits, view["document_id"], key=key)
    assert voided.status_code == 200, voided.text
    business = credits.ledger.business
    with owner_tenant_transaction(owner_conn, business):
        deleted = owner_conn.execute(
            "delete from gba.idempotency_keys where tenant_id=%s "
            "and operation='business.finance.credit_void' and idempotency_key=%s",
            (business, key),
        )
        assert deleted.rowcount == 1
    command = f"/v1/businesses/{business}/financial-documents/commands"
    reference = {
        "schema_version": 1,
        "operation": "credit_void",
        "book_id": str(credits.ledger.book),
        "subject_id": str(view["document_id"]),
        "revision": 3,
    }
    http, auth = credits.ledger.client, credits.ledger.auth
    resolved = await http.post(f"{command}/{key}/resolve", json=reference, headers=auth)
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["state"] == "committed"
    assert (await _void(credits, view["document_id"], key=key)).json() == voided.json()
    late_key = str(uuid7())
    cancelled = await http.post(
        f"{command}/{late_key}/cancel",
        json={**reference, "subject_id": str(other["document_id"])},
        headers=auth,
    )
    assert cancelled.status_code == 200, cancelled.text
    sealed = await _void(credits, other["document_id"], key=late_key)
    assert sealed.status_code == 409
    assert sealed.json()["error"]["code"] == "FINANCIAL_COMMAND_CANCELLED"
    assert await _balances(credits, obligation) == ("0.00", "5.00", "0.00", "95.00")


@pytest.mark.parametrize(
    ("role", "branch"),
    [("front_desk", False), ("artist", False), ("manager", True)],
)
async def test_void_keeps_company_finance_permissions(
    credits: CreditWorld,
    owner_conn: psycopg.Connection,
    world: BookingWorld,
    idp: FakeIdp,
    manager_b: object,
    role: str,
    branch: bool,
) -> None:
    obligation, (line,) = await credits.invoice()
    view = await credits.credit(obligation, [(line, "10.00")])
    member = seed_user(owner_conn, f"FAKE-H3-void-{role}-{uuid7()}")
    add_membership(
        owner_conn,
        tenant_id=credits.ledger.business,
        user_id=member.user_id,
        role=role,
        location_id=world.a.location_id if branch else None,
    )
    foreign = Config(credits.ledger.client, idp).auth(manager_b)  # type: ignore[arg-type]
    for auth in (idp.bearer(member.subject, email=member.email), foreign):
        keyed = {**auth, "Idempotency-Key": str(uuid7())}
        assert (await _void(credits, view["document_id"], headers=keyed)).status_code == 403
    assert await _balances(credits, obligation) == ("0.00", "10.00", "0.00", "90.00")


_VOID_REFS = ("financial_document_versions", "financial_versions_void_refs")


@pytest.mark.parametrize(
    ("change", "restore"),
    [
        (
            "alter table gba.financial_document_versions "
            "drop constraint financial_versions_void_refs",
            approved_check(*_VOID_REFS),
        ),
        (
            "create or replace function gba.credit_voided(tenant uuid, book uuid, "
            "document uuid) returns boolean language plpgsql as $$ begin return false; end; $$",
            packaged_function("credit_voided"),
        ),
        (
            "alter table gba.financial_document_versions "
            "drop constraint financial_versions_void_entry_fk",
            "alter table gba.financial_document_versions add constraint "
            "financial_versions_void_entry_fk foreign key (tenant_id, book_id, void_entry_id) "
            "references gba.journal_entries(tenant_id, book_id, id) deferrable initially deferred",
        ),
    ],
)
async def test_damaged_void_controls_fail_readiness_with_503(
    credits: CreditWorld,
    owner_conn: psycopg.Connection,
    change: str,
    restore: str,
) -> None:
    http, auth, base = credits.ledger.client, credits.ledger.auth, credits.ledger.base
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
