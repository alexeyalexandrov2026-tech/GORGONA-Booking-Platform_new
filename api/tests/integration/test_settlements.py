"""H2 settlement documents: preparation, approval, reserve, release; no money moves."""

import asyncio
from dataclasses import dataclass
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest
from psycopg import sql

from gorgona_booking.business import modules
from gorgona_booking.business.readiness_registry import Readiness
from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import add_membership, owner_tenant_transaction
from tests.integration import test_invoice_issue as invoice_shared
from tests.integration.booking_support import BookingWorld
from tests.integration.configuration_support import Config
from tests.integration.seed import seed_user
from tests.integration.test_counterparties import card
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

_MODULES = ["booking_resources", "finance", "counterparties", "finance_documents"]


@dataclass(frozen=True)
class SettlementWorld:
    invoices: InvoiceWorld

    @property
    def ledger(self) -> LedgerWorld:
        return self.invoices.ledger

    @property
    def root(self) -> str:
        return f"/v1/businesses/{self.ledger.business}/financial-documents/books/{self.ledger.book}"

    async def obligation(self, amount: str = "100.00", **changes: object) -> UUID:
        """Issue a FAKE receivable invoice and return its principal obligation."""
        document = uuid7()
        body = self.invoices.draft_body(**changes)
        lines: list[dict[str, object]] = body["lines"]  # type: ignore[assignment]
        lines[0]["amount"] = amount
        saved = await self.invoices.save(document=document, body=body)
        assert saved.status_code == 200, saved.text
        issued = await self.invoices.issue(document)
        assert issued.status_code == 200, issued.text
        return UUID(issued.json()["obligation_id"])

    def body(self, allocations: list[tuple[UUID, str]], **changes: object) -> dict[str, object]:
        return {
            "schema_version": 1,
            "expected_sequence": 0,
            "direction": "receivable",
            "counterparty_id": str(self.invoices.party),
            "currency": "USD",
            "allocations": [
                {"obligation_id": str(obligation), "amount": amount}
                for obligation, amount in allocations
            ],
            **changes,
        }

    async def prepare(
        self,
        settlement: UUID,
        allocations: list[tuple[UUID, str]],
        *,
        key: str | None = None,
        **changes: object,
    ) -> httpx.Response:
        return await self.ledger.client.put(
            f"{self.root}/settlements/{settlement}",
            json=self.body(allocations, **changes),
            headers=self.ledger.headers(key),
        )

    async def act(
        self,
        settlement: UUID,
        action: str,
        sequence: int,
        *,
        key: str | None = None,
        headers: dict[str, str] | None = None,
        **extra: object,
    ) -> httpx.Response:
        return await self.ledger.client.post(
            f"{self.root}/settlements/{settlement}/{action}",
            json={"schema_version": 1, "expected_sequence": sequence, **extra},
            headers=headers or self.ledger.headers(key),
        )

    async def approved(self, obligation: UUID, amount: str) -> UUID:
        settlement = uuid7()
        prepared = await self.prepare(settlement, [(obligation, amount)])
        assert prepared.status_code == 200, prepared.text
        approved = await self.act(settlement, "approve", 1)
        assert approved.status_code == 200, approved.text
        return settlement

    async def reserved(self, obligation: UUID, amount: str) -> UUID:
        settlement = await self.approved(obligation, amount)
        reserved = await self.act(settlement, "reserve", 2)
        assert reserved.status_code == 200, reserved.text
        return settlement

    async def balance(self, obligation: UUID) -> dict[str, object]:
        response = await self.ledger.client.get(
            f"{self.root}/obligations/{obligation}", headers=self.ledger.auth
        )
        assert response.status_code == 200, response.text
        result: dict[str, object] = response.json()
        return result

    async def view(self, settlement: UUID) -> dict[str, object]:
        response = await self.ledger.client.get(
            f"{self.root}/settlements/{settlement}", headers=self.ledger.auth
        )
        assert response.status_code == 200, response.text
        result: dict[str, object] = response.json()
        return result


@pytest.fixture
def settlements(invoices: InvoiceWorld) -> SettlementWorld:
    return SettlementWorld(invoices)


async def _wait_for_blocked(owner_conn: psycopg.Connection, count: int) -> None:
    """Observe real advisory-lock waits; a sleep alone proves no race."""
    for _ in range(300):
        await asyncio.sleep(0.01)
        row = owner_conn.execute(
            "select count(*) from pg_catalog.pg_locks where locktype='advisory' and not granted"
        ).fetchone()
        if row and row[0] >= count:
            return
    pytest.fail(f"{count} requests must be observed waiting on the held ledger lock")


async def test_settlement_routes_require_authentication(client: httpx.AsyncClient) -> None:
    base = f"/v1/businesses/{uuid7()}/financial-documents/books/{uuid7()}"
    assert (await client.get(f"{base}/settlements/{uuid7()}")).status_code == 401
    assert (await client.get(f"{base}/obligations")).status_code == 401


async def test_prepare_approve_reserve_release_change_only_the_reserve(
    settlements: SettlementWorld,
    app_pool: RuntimePool,
) -> None:
    obligation = await settlements.obligation()
    start = await settlements.balance(obligation)
    assert (start["principal"], start["paid"], start["credited"], start["reserved"]) == (
        "100.00",
        "0.00",
        "0.00",
        "0.00",
    )
    assert (start["available"], start["source_kind"]) == ("100.00", "invoice")
    settlement, reserve_key = uuid7(), str(uuid7())
    prepared = await settlements.prepare(settlement, [(obligation, "70.00")])
    assert prepared.status_code == 200, prepared.text
    assert (prepared.json()["status"], prepared.json()["sequence"]) == ("prepared", 1)
    assert prepared.json()["total"] == "70.00"
    assert (await settlements.balance(obligation))["reserved"] == "0.00"
    approved = await settlements.act(settlement, "approve", 1)
    assert approved.status_code == 200, approved.text
    assert (approved.json()["status"], approved.json()["approved_by_preparer"]) == (
        "approved",
        True,
    )
    assert (await settlements.balance(obligation))["reserved"] == "0.00"
    reserved = await settlements.act(settlement, "reserve", 2, key=reserve_key)
    assert reserved.status_code == 200, reserved.text
    assert (reserved.json()["status"], reserved.json()["reserved"]) == ("reserved", "70.00")
    after = await settlements.balance(obligation)
    assert (after["reserved"], after["available"], after["paid"]) == ("70.00", "30.00", "0.00")
    replay = await settlements.act(settlement, "reserve", 2, key=reserve_key)
    assert replay.status_code == 200
    assert replay.json() == reserved.json()
    stale = await settlements.act(settlement, "sent", 2)
    assert stale.status_code == 409
    released = await settlements.act(settlement, "release", 3)
    assert released.status_code == 200, released.text
    assert (released.json()["status"], released.json()["reserved"]) == ("released", "0.00")
    assert [e["kind"] for e in released.json()["events"]] == [
        "prepared",
        "approved",
        "reserved",
        "released",
    ]
    final = await settlements.balance(obligation)
    assert (final["reserved"], final["available"]) == ("0.00", "100.00")
    again = await settlements.act(settlement, "reserve", 4)
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "FINANCIAL_STATE_INVALID"
    async with tenant_transaction(app_pool, settlements.ledger.business) as conn:
        # A reserve is not money: the only journal is the invoice accrual.
        entries = await (
            await conn.execute(
                "select source_kind from gba.journal_entries where book_id=%s",
                (settlements.ledger.book,),
            )
        ).fetchall()
        assert entries == [("invoice",)]
        receipts = await (
            await conn.execute(
                "select operation,sequence from gba.settlement_command_receipts "
                "where settlement_id=%s order by sequence",
                (settlement,),
            )
        ).fetchall()
        assert receipts == [
            ("settlement_prepare", 1),
            ("settlement_approve", 2),
            ("settlement_reserve", 3),
            ("settlement_release", 4),
        ]


async def test_another_authorized_person_can_approve_and_the_view_says_so(
    settlements: SettlementWorld,
    owner_conn: psycopg.Connection,
    idp: FakeIdp,
) -> None:
    obligation = await settlements.obligation()
    settlement = uuid7()
    assert (await settlements.prepare(settlement, [(obligation, "10.00")])).status_code == 200
    second = seed_user(owner_conn, f"FAKE-H2-approver-{uuid7()}")
    add_membership(
        owner_conn,
        tenant_id=settlements.ledger.business,
        user_id=second.user_id,
        role="manager",
        location_id=None,
    )
    headers = {
        **idp.bearer(second.subject, email=second.email),
        "Idempotency-Key": str(uuid7()),
    }
    approved = await settlements.act(settlement, "approve", 1, headers=headers)
    assert approved.status_code == 200, approved.text
    view = approved.json()
    assert view["approved_by_preparer"] is False
    assert view["approved_by"] == str(second.user_id)
    assert view["prepared_by"] == str(settlements.ledger.user.user_id)


@pytest.mark.parametrize("first", [0, 1])
async def test_two_documents_reserving_70_of_100_wait_on_real_lock_and_one_wins(
    settlements: SettlementWorld,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
    first: int,
) -> None:
    obligation = await settlements.obligation()
    documents = [await settlements.approved(obligation, "70.00") for _ in range(2)]
    order = [documents[first], documents[1 - first]]
    async with tenant_transaction(app_pool, settlements.ledger.business) as conn:
        await conn.execute("select gba.lock_ledger(%s)", (settlements.ledger.business,))
        pending = []
        try:
            for index, document in enumerate(order, 1):
                pending.append(asyncio.create_task(settlements.act(document, "reserve", 2)))
                await _wait_for_blocked(owner_conn, index)
        except BaseException:
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            raise
    results = await asyncio.gather(*pending)
    assert sorted(r.status_code for r in results) == [200, 409]
    refused = next(r for r in results if r.status_code == 409)
    assert refused.json()["error"]["code"] == "FINANCIAL_CAP_EXCEEDED"
    balance = await settlements.balance(obligation)
    assert (balance["reserved"], balance["available"]) == ("70.00", "30.00")
    statuses = sorted([str((await settlements.view(d))["status"]) for d in documents])
    assert statuses == ["approved", "reserved"]


async def test_release_and_competing_reserve_keep_the_cap(
    settlements: SettlementWorld,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
) -> None:
    obligation = await settlements.obligation()
    holder = await settlements.reserved(obligation, "70.00")
    waiting = await settlements.approved(obligation, "70.00")
    async with tenant_transaction(app_pool, settlements.ledger.business) as conn:
        await conn.execute("select gba.lock_ledger(%s)", (settlements.ledger.business,))
        pending = [
            asyncio.create_task(settlements.act(holder, "release", 3)),
            asyncio.create_task(settlements.act(waiting, "reserve", 2)),
        ]
        try:
            await _wait_for_blocked(owner_conn, 2)
        except BaseException:
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            raise
    release, reserve = await asyncio.gather(*pending)
    assert release.status_code == 200, release.text
    assert reserve.status_code in (200, 409)
    balance = await settlements.balance(obligation)
    assert balance["reserved"] == ("70.00" if reserve.status_code == 200 else "0.00")
    assert balance["paid"] == "0.00"


async def test_sql_cannot_bypass_cap_order_or_history(
    settlements: SettlementWorld,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
) -> None:
    business, book = settlements.ledger.business, settlements.ledger.book
    user = settlements.ledger.user.user_id
    obligation = await settlements.obligation()
    await settlements.reserved(obligation, "70.00")
    second = await settlements.approved(obligation, "70.00")
    event = (
        "insert into gba.settlement_events "
        "(tenant_id,book_id,settlement_id,sequence,kind,created_by) values (%s,%s,%s,%s,%s,%s)"
    )
    with pytest.raises(psycopg.errors.CheckViolation, match="cap exceeded"):  # noqa: PT012
        async with tenant_transaction(app_pool, business) as conn:
            await conn.execute(event, (business, book, second, 3, "reserved", user))
            await conn.execute("set constraints all immediate")
    with pytest.raises(psycopg.errors.CheckViolation, match="contiguous"):
        async with tenant_transaction(app_pool, business) as conn:
            await conn.execute(event, (business, book, second, 5, "reserved", user))
    prepared = uuid7()
    assert (await settlements.prepare(prepared, [(obligation, "10.00")])).status_code == 200
    with pytest.raises(psycopg.errors.CheckViolation, match="does not follow"):
        async with tenant_transaction(app_pool, business) as conn:
            await conn.execute(event, (business, book, prepared, 2, "reserved", user))
    with pytest.raises(psycopg.errors.CheckViolation, match="written with their document"):
        async with tenant_transaction(app_pool, business) as conn:
            await conn.execute(
                "insert into gba.settlement_allocations "
                "(tenant_id,book_id,settlement_id,line_no,obligation_id,amount_minor) "
                "values (%s,%s,%s,2,%s,1)",
                (business, book, prepared, await settlements.obligation("5.00")),
            )
    # A document cannot be created without its prepared event and allocations.
    with pytest.raises(psycopg.errors.CheckViolation, match="prepared event"):  # noqa: PT012
        async with tenant_transaction(app_pool, business) as conn:
            await conn.execute(
                "insert into gba.settlement_documents "
                "(tenant_id,book_id,id,direction,counterparty_id,currency,created_by) "
                "values (%s,%s,%s,'receivable',%s,'USD',%s)",
                (business, book, uuid7(), settlements.invoices.party, user),
            )
            await conn.execute("set constraints all immediate")
    for table in ("settlement_documents", "settlement_allocations", "settlement_events"):
        with (
            pytest.raises(psycopg.errors.CheckViolation, match="kept unchanged"),
            owner_tenant_transaction(owner_conn, business),
        ):
            owner_conn.execute(
                sql.SQL("update gba.{} set book_id=book_id where book_id=%s").format(
                    sql.Identifier(table)
                ),
                (book,),
            )
    assert (await settlements.balance(obligation))["reserved"] == "70.00"


async def test_allocations_match_party_direction_currency_and_principal(
    settlements: SettlementWorld,
    app_pool: RuntimePool,
) -> None:
    business, book = settlements.ledger.business, settlements.ledger.book
    obligation = await settlements.obligation()
    other_party = uuid7()
    created = await settlements.ledger.client.put(
        f"/v1/businesses/{business}/counterparties/{other_party}",
        json=card(),
        headers=settlements.ledger.headers(),
    )
    assert created.status_code == 200, created.text
    for changes in (
        {"counterparty_id": str(other_party)},
        {"direction": "payable"},
        {"currency": "JPY"},
    ):
        refused = await settlements.prepare(uuid7(), [(obligation, "10.00")], **changes)
        assert refused.status_code == 409, refused.text
        assert refused.json()["error"]["code"] == "FINANCIAL_STATE_INVALID"
    too_much = await settlements.prepare(uuid7(), [(obligation, "100.01")])
    assert too_much.status_code == 409
    assert too_much.json()["error"]["code"] == "FINANCIAL_CAP_EXCEEDED"
    twice = await settlements.prepare(uuid7(), [(obligation, "10.00"), (obligation, "5.00")])
    assert twice.status_code == 422
    unknown = await settlements.prepare(uuid7(), [(uuid7(), "10.00")])
    assert unknown.status_code == 409
    scale = await settlements.prepare(uuid7(), [(obligation, "10.001")])
    assert scale.status_code == 422
    assert scale.json()["error"]["code"] == "FINANCIAL_AMOUNT_INVALID"
    settlement = uuid7()
    with pytest.raises(psycopg.errors.CheckViolation, match="same party"):  # noqa: PT012
        async with tenant_transaction(app_pool, business) as conn:
            await conn.execute(
                "insert into gba.settlement_documents "
                "(tenant_id,book_id,id,direction,counterparty_id,currency,created_by) "
                "values (%s,%s,%s,'payable',%s,'USD',%s)",
                (
                    business,
                    book,
                    settlement,
                    settlements.invoices.party,
                    settlements.ledger.user.user_id,
                ),
            )
            await conn.execute(
                "insert into gba.settlement_allocations "
                "(tenant_id,book_id,settlement_id,line_no,obligation_id,amount_minor) "
                "values (%s,%s,%s,1,%s,1000)",
                (business, book, settlement, obligation),
            )
    two = await settlements.obligation("40.00")
    both = uuid7()
    prepared = await settlements.prepare(both, [(obligation, "60.00"), (two, "40.00")])
    assert prepared.status_code == 200, prepared.text
    assert prepared.json()["total"] == "100.00"
    assert (await settlements.act(both, "approve", 1)).status_code == 200
    assert (await settlements.act(both, "reserve", 2)).status_code == 200
    assert (await settlements.balance(obligation))["reserved"] == "60.00"
    assert (await settlements.balance(two))["available"] == "0.00"


async def test_sent_outcome_needs_explicit_resolution_even_when_off(
    settlements: SettlementWorld,
    idp: FakeIdp,
) -> None:
    obligation = await settlements.obligation()
    settlement = await settlements.reserved(obligation, "70.00")
    sent = await settlements.act(settlement, "sent", 3)
    assert sent.status_code == 200, sent.text
    assert sent.json()["status"] == "sent"
    plain = await settlements.act(settlement, "release", 4)
    assert plain.status_code == 409
    assert plain.json()["error"]["code"] == "FINANCIAL_OUTCOME_UNRESOLVED"

    async def attested() -> httpx.Response:
        return await settlements.act(
            settlement,
            "release",
            4,
            resolution="attested_no_payment",
            reason="FAKE transfer was rejected by the bank",
            evidence_source="FAKE bank statement 2026-10-05",
        )

    incomplete = await settlements.act(settlement, "release", 4, resolution="attested_no_payment")
    assert incomplete.status_code == 422
    config = Config(settlements.ledger.client, idp)
    await config.publish(
        settlements.ledger.user, settlements.ledger.business, 2, ["booking_resources"]
    )
    off = await attested()
    assert off.status_code == 409
    assert off.json()["error"]["code"] == "MODULE_DISABLED"
    assert (await settlements.balance(obligation))["reserved"] == "70.00"
    await config.publish(settlements.ledger.user, settlements.ledger.business, 3, _MODULES)
    resolved = await attested()
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["status"] == "released"
    last = resolved.json()["events"][-1]
    assert (last["kind"], last["resolution"], last["evidence_source"]) == (
        "released",
        "attested_no_payment",
        "FAKE bank statement 2026-10-05",
    )
    assert (await settlements.balance(obligation))["reserved"] == "0.00"


async def test_plain_reserve_cannot_claim_an_attested_resolution(
    settlements: SettlementWorld,
    app_pool: RuntimePool,
) -> None:
    obligation = await settlements.obligation()
    settlement = await settlements.reserved(obligation, "70.00")
    refused = await settlements.act(
        settlement,
        "release",
        3,
        resolution="attested_no_payment",
        reason="FAKE reason",
        evidence_source="FAKE source",
    )
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "FINANCIAL_STATE_INVALID"
    business = settlements.ledger.business
    assert (await settlements.act(settlement, "sent", 3)).status_code == 200
    with pytest.raises(psycopg.errors.CheckViolation, match="does not follow"):
        async with tenant_transaction(app_pool, business) as conn:
            await conn.execute(
                "insert into gba.settlement_events "
                "(tenant_id,book_id,settlement_id,sequence,kind,created_by) "
                "values (%s,%s,%s,5,'released',%s)",
                (business, settlements.ledger.book, settlement, settlements.ledger.user.user_id),
            )
    assert (await settlements.balance(obligation))["reserved"] == "70.00"


async def test_off_blocks_new_effects_but_keeps_reads_release_and_cancel(
    settlements: SettlementWorld,
    idp: FakeIdp,
) -> None:
    obligation = await settlements.obligation()
    reserved = await settlements.reserved(obligation, "30.00")
    approved = await settlements.approved(obligation, "20.00")
    prepared = uuid7()
    assert (await settlements.prepare(prepared, [(obligation, "10.00")])).status_code == 200
    config = Config(settlements.ledger.client, idp)
    await config.publish(
        settlements.ledger.user, settlements.ledger.business, 2, ["booking_resources"]
    )
    for response in (
        await settlements.prepare(uuid7(), [(obligation, "1.00")]),
        await settlements.act(prepared, "approve", 1),
        await settlements.act(approved, "reserve", 2),
        await settlements.act(reserved, "sent", 3),
    ):
        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == "MODULE_DISABLED"
    assert (await settlements.view(reserved))["status"] == "reserved"
    assert (await settlements.balance(obligation))["reserved"] == "30.00"
    listed = await settlements.ledger.client.get(
        f"{settlements.root}/settlements", headers=settlements.ledger.auth
    )
    assert listed.status_code == 200
    assert len(listed.json()["items"]) == 3
    released = await settlements.act(reserved, "release", 3)
    assert released.status_code == 200, released.text
    cancelled = await settlements.act(prepared, "cancel", 1)
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"
    assert (await settlements.balance(obligation))["reserved"] == "0.00"


async def test_withdrawn_readiness_blocks_new_settlement_effects(
    settlements: SettlementWorld,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    obligation = await settlements.obligation()
    reserved = await settlements.reserved(obligation, "30.00")
    approved = await settlements.approved(obligation, "20.00")
    feature = modules.MODULES_BY_ID["finance_documents"]
    monkeypatch.setitem(
        modules.MODULES_BY_ID,
        "finance_documents",
        feature.model_copy(update={"enableable": False, "readiness": Readiness.PLANNED}),
    )
    for response in (
        await settlements.prepare(uuid7(), [(obligation, "1.00")]),
        await settlements.act(approved, "reserve", 2),
        await settlements.act(reserved, "sent", 3),
    ):
        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == "MODULE_NOT_READY"
    assert (await settlements.act(reserved, "release", 3)).status_code == 200


async def test_reserve_replay_recovery_and_cancel_before_late_original(
    settlements: SettlementWorld,
    owner_conn: psycopg.Connection,
) -> None:
    business = settlements.ledger.business
    obligation = await settlements.obligation()
    settlement = await settlements.approved(obligation, "70.00")
    key = str(uuid7())
    reserved = await settlements.act(settlement, "reserve", 2, key=key)
    assert reserved.status_code == 200, reserved.text
    with owner_tenant_transaction(owner_conn, business):
        deleted = owner_conn.execute(
            "delete from gba.idempotency_keys where tenant_id=%s "
            "and operation='business.finance.settlement_reserve' and idempotency_key=%s",
            (business, key),
        )
        assert deleted.rowcount == 1
    commands = f"/v1/businesses/{business}/financial-documents/commands"
    reference = {
        "schema_version": 1,
        "operation": "settlement_reserve",
        "book_id": str(settlements.ledger.book),
        "subject_id": str(settlement),
        "revision": 3,
    }
    resolved = await settlements.ledger.client.post(
        f"{commands}/{key}/resolve", json=reference, headers=settlements.ledger.auth
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["state"] == "committed"
    replay = await settlements.act(settlement, "reserve", 2, key=key)
    assert replay.status_code == 200
    assert replay.json() == reserved.json()
    assert (await settlements.balance(obligation))["reserved"] == "70.00"
    with owner_tenant_transaction(owner_conn, business):
        stored = owner_conn.execute(
            "select response_body from gba.idempotency_keys where tenant_id=%s "
            "and operation='business.finance.settlement_reserve' and idempotency_key=%s",
            (business, key),
        ).fetchone()
    assert stored is not None
    assert set(stored[0]) == {"book_id", "settlement_id", "sequence"}
    late, late_key = uuid7(), str(uuid7())
    late_reference = {**reference, "operation": "settlement_prepare", "subject_id": str(late)}
    impossible = await settlements.ledger.client.post(
        f"{commands}/{late_key}/cancel", json=late_reference, headers=settlements.ledger.headers()
    )
    assert impossible.status_code == 422
    cancelled = await settlements.ledger.client.post(
        f"{commands}/{late_key}/cancel",
        json={**late_reference, "revision": 1},
        headers=settlements.ledger.headers(),
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["state"] == "cancelled"
    blocked = await settlements.prepare(late, [(obligation, "10.00")], key=late_key)
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "FINANCIAL_COMMAND_CANCELLED"
    committed = await settlements.ledger.client.post(
        f"{commands}/{key}/cancel", json=reference, headers=settlements.ledger.headers()
    )
    assert committed.json()["state"] == "committed"


async def test_settlement_recovery_replay_and_cancel_work_while_finance_is_off(
    settlements: SettlementWorld,
    idp: FakeIdp,
    owner_conn: psycopg.Connection,
) -> None:
    business = settlements.ledger.business
    obligation = await settlements.obligation()
    settlement = await settlements.approved(obligation, "70.00")
    key = str(uuid7())
    reserved = await settlements.act(settlement, "reserve", 2, key=key)
    assert reserved.status_code == 200, reserved.text
    config = Config(settlements.ledger.client, idp)
    await config.publish(settlements.ledger.user, business, 2, ["booking_resources"])
    with owner_tenant_transaction(owner_conn, business):
        deleted = owner_conn.execute(
            "delete from gba.idempotency_keys where tenant_id=%s "
            "and operation='business.finance.settlement_reserve' and idempotency_key=%s",
            (business, key),
        )
        assert deleted.rowcount == 1
    commands = f"/v1/businesses/{business}/financial-documents/commands"
    reference = {
        "schema_version": 1,
        "operation": "settlement_reserve",
        "book_id": str(settlements.ledger.book),
        "subject_id": str(settlement),
        "revision": 3,
    }
    resolved = await settlements.ledger.client.post(
        f"{commands}/{key}/resolve", json=reference, headers=settlements.ledger.auth
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["state"] == "committed"
    replay = await settlements.act(settlement, "reserve", 2, key=key)
    assert replay.status_code == 200, replay.text
    assert replay.json() == reserved.json()
    # A lost sent command is resolved and sealed while finance stays off.
    late_key = str(uuid7())
    late = {**reference, "operation": "settlement_sent", "revision": 4}
    unknown = await settlements.ledger.client.post(
        f"{commands}/{late_key}/resolve", json=late, headers=settlements.ledger.auth
    )
    assert unknown.status_code == 200, unknown.text
    assert unknown.json()["state"] == "unresolved"
    cancelled = await settlements.ledger.client.post(
        f"{commands}/{late_key}/cancel", json=late, headers=settlements.ledger.headers()
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["state"] == "cancelled"
    blocked = await settlements.act(settlement, "sent", 3, key=late_key)
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["error"]["code"] == "FINANCIAL_COMMAND_CANCELLED"
    assert (await settlements.view(settlement))["status"] == "reserved"
    assert (await settlements.balance(obligation))["reserved"] == "70.00"


async def test_obligation_list_shows_invoice_and_manual_sources_with_balances(
    settlements: SettlementWorld,
) -> None:
    http, auth = settlements.ledger.client, settlements.ledger.auth
    invoice = await settlements.obligation("100.00")
    accruals = f"{settlements.root}/accruals"
    document = uuid7()
    body = settlements.invoices.draft_body(title="FAKE manual accrual", number="FAKE-ACC-9")
    saved = await http.put(
        f"{accruals}/{document}", json=body, headers=settlements.ledger.headers()
    )
    assert saved.status_code == 200, saved.text
    issued = await http.post(
        f"{accruals}/{document}/issue",
        json={
            "schema_version": 1,
            "expected_revision": 1,
            "entry_date": "2026-10-01",
            "attestation": "confirmed_account_treatment",
        },
        headers=settlements.ledger.headers(),
    )
    assert issued.status_code == 200, issued.text
    await settlements.reserved(invoice, "25.00")
    listed = await http.get(f"{settlements.root}/obligations", headers=auth)
    assert listed.status_code == 200, listed.text
    items = {item["obligation_id"]: item for item in listed.json()["items"]}
    assert items[str(invoice)]["source_kind"] == "invoice"
    assert items[str(invoice)]["reserved"] == "25.00"
    assert items[issued.json()["obligation_id"]]["source_kind"] == "manual"
    assert items[issued.json()["obligation_id"]]["available"] == "100.00"
    page = await http.get(f"{settlements.root}/obligations", params={"limit": 1}, headers=auth)
    assert len(page.json()["items"]) == 1
    assert page.json()["next_cursor"] is not None
    missing = await http.get(f"{settlements.root}/obligations/{uuid7()}", headers=auth)
    assert missing.status_code == 404


async def test_settlement_amounts_use_the_obligation_currency_scale(
    settlements: SettlementWorld,
) -> None:
    obligation = await settlements.obligation("1000", currency="JPY")
    settlement = uuid7()
    fraction = await settlements.prepare(settlement, [(obligation, "700.5")], currency="JPY")
    assert fraction.status_code == 422
    prepared = await settlements.prepare(settlement, [(obligation, "700")], currency="JPY")
    assert prepared.status_code == 200, prepared.text
    assert (await settlements.act(settlement, "approve", 1)).status_code == 200
    assert (await settlements.act(settlement, "reserve", 2)).status_code == 200
    balance = await settlements.balance(obligation)
    assert (balance["reserved"], balance["available"]) == ("700", "300")


@pytest.mark.parametrize(
    ("role", "branch", "expected"),
    [
        ("owner", False, 200),
        ("front_desk", False, 403),
        ("artist", False, 403),
        ("manager", True, 403),
    ],
)
async def test_settlement_routes_keep_company_finance_permissions(
    settlements: SettlementWorld,
    owner_conn: psycopg.Connection,
    world: BookingWorld,
    idp: FakeIdp,
    role: str,
    branch: bool,
    expected: int,
) -> None:
    obligation = await settlements.obligation()
    settlement = await settlements.approved(obligation, "10.00")
    member = seed_user(owner_conn, f"FAKE-H2-{role}-{uuid7()}")
    add_membership(
        owner_conn,
        tenant_id=settlements.ledger.business,
        user_id=member.user_id,
        role=role,
        location_id=world.a.location_id if branch else None,
    )
    auth = idp.bearer(member.subject, email=member.email)
    http = settlements.ledger.client
    for path in (f"settlements/{settlement}", f"obligations/{obligation}", "obligations"):
        response = await http.get(f"{settlements.root}/{path}", headers=auth)
        assert response.status_code == expected, response.text
    if expected != 200:
        keyed = {**auth, "Idempotency-Key": str(uuid7())}
        assert (await settlements.act(settlement, "reserve", 2, headers=keyed)).status_code == 403
        assert (await settlements.balance(obligation))["reserved"] == "0.00"


async def test_another_company_cannot_read_or_settle_these_obligations(
    settlements: SettlementWorld,
    world: BookingWorld,
    manager_b: object,
    idp: FakeIdp,
) -> None:
    obligation = await settlements.obligation()
    settlement = await settlements.approved(obligation, "10.00")
    config = Config(settlements.ledger.client, idp)
    foreign = config.auth(manager_b)  # type: ignore[arg-type]
    http = settlements.ledger.client
    assert (
        await http.get(f"{settlements.root}/settlements/{settlement}", headers=foreign)
    ).status_code == 403
    other_root = settlements.root.replace(str(settlements.ledger.business), str(world.b.tenant_id))
    assert (
        await http.get(f"{other_root}/obligations/{obligation}", headers=foreign)
    ).status_code in (403, 404, 409)


_EVENT_KIND = ("settlement_events", "settlement_events_kind_check")


@pytest.mark.parametrize(
    ("change", "restore"),
    [
        (
            "alter table gba.settlement_events disable trigger settlement_events_next",
            "alter table gba.settlement_events enable trigger settlement_events_next",
        ),
        (
            "alter table gba.settlement_allocations "
            "disable trigger settlement_allocations_consistent",
            "alter table gba.settlement_allocations "
            "enable trigger settlement_allocations_consistent",
        ),
        (
            "alter table gba.settlement_events no force row level security",
            "alter table gba.settlement_events force row level security",
        ),
        (
            "alter policy settlement_documents_unrestricted_scope on gba.settlement_documents "
            "using (true) with check (true)",
            "alter policy settlement_documents_unrestricted_scope on gba.settlement_documents "
            "using (gba.current_location_id() is null) "
            "with check (gba.current_location_id() is null)",
        ),
        (
            "create policy extra_settlement_grant on gba.settlement_events "
            "using (true) with check (true)",
            "drop policy extra_settlement_grant on gba.settlement_events",
        ),
        (
            "grant insert(created_transaction) on gba.settlement_events to gba_runtime",
            "revoke insert(created_transaction) on gba.settlement_events from gba_runtime",
        ),
        (
            "grant update on gba.settlement_allocations to gba_runtime",
            "revoke update on gba.settlement_allocations from gba_runtime",
        ),
        (widened_check(*_EVENT_KIND, "kind = 'voided'"), approved_check(*_EVENT_KIND)),
        (
            "create or replace function gba.obligation_balance(tenant uuid, book uuid, "
            "obligation uuid) returns table (principal_minor bigint, paid_minor bigint, "
            "credited_minor bigint, reserved_minor bigint) language plpgsql as $$ begin "
            "return query select 1::bigint, 0::bigint, 0::bigint, 0::bigint; end; $$",
            packaged_function("obligation_balance"),
        ),
        (
            "create or replace function gba.enforce_settlement_event() returns trigger "
            "language plpgsql as $$ begin return new; end; $$",
            packaged_function("enforce_settlement_event"),
        ),
    ],
)
async def test_damaged_settlement_controls_fail_readiness_with_503(
    settlements: SettlementWorld,
    owner_conn: psycopg.Connection,
    change: str,
    restore: str,
) -> None:
    http, auth, base = settlements.ledger.client, settlements.ledger.auth, settlements.ledger.base
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


async def test_api_status_equals_the_sql_phase_at_every_step(
    settlements: SettlementWorld,
    app_pool: RuntimePool,
) -> None:
    obligation = await settlements.obligation()

    async def agree(settlement: UUID, expected: str) -> None:
        assert (await settlements.view(settlement))["status"] == expected
        async with tenant_transaction(app_pool, settlements.ledger.business) as conn:
            row = await (
                await conn.execute(
                    "select gba.settlement_phase(%s,%s,%s)",
                    (settlements.ledger.business, settlements.ledger.book, settlement),
                )
            ).fetchone()
        assert row == (expected,)

    settlement = uuid7()
    assert (await settlements.prepare(settlement, [(obligation, "10.00")])).status_code == 200
    await agree(settlement, "prepared")
    for sequence, action, status in (
        (1, "approve", "approved"),
        (2, "reserve", "reserved"),
        (3, "sent", "sent"),
    ):
        assert (await settlements.act(settlement, action, sequence)).status_code == 200
        await agree(settlement, status)
    resolved = await settlements.act(
        settlement,
        "release",
        4,
        resolution="attested_no_payment",
        reason="FAKE no payment left the account",
        evidence_source="FAKE statement",
    )
    assert resolved.status_code == 200, resolved.text
    await agree(settlement, "released")
    other = await settlements.approved(obligation, "10.00")
    assert (await settlements.act(other, "cancel", 2, reason="FAKE not needed")).status_code == 200
    await agree(other, "cancelled")
    assert (await settlements.view(other))["events"][-1]["reason"] == "FAKE not needed"  # type: ignore[index]
