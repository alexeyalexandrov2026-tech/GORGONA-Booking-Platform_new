"""O3b: construction actual costs (package O, BUILD-01; FAKE data only).

docs/plan/PACKAGE_O3B_DESIGN_2026-10-31.md: an actual cost is a link of one existing fact (a
STOCK-01 write-off line, a FIN-03 payable line, a WORK-01 approved time entry with a rate) to one
budget line; each fact is linked once; a reversal row instead of an edit; overruns are shown.
"""

from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.business import ledger, modules
from gorgona_booking.business.readiness_registry import Readiness
from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import add_membership, owner_tenant_transaction
from tests.integration.booking_support import BookingWorld, at
from tests.integration.configuration_support import Config
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.seed import FakeUser, seed_other_branch, seed_user
from tests.integration.test_counterparties import card
from tests.integration.test_inventory import Inventory
from tests.integration.test_l8b2_finance_races import race
from tests.integration.test_o1_construction_estimates import (
    Construction,
    accepted,
    client,
    error,
    idp,
    line,
    manager_a,
    manager_b,
)
from tests.integration.test_o2_construction_contract import accept
from tests.integration.test_o3a_construction_budget import budgeted, commit
from tests.integration.test_stock import Stock, entity_with_book
from tests.integration.test_workforce import Workforce
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
__all__ = ["accepted", "client", "idp", "manager_a", "manager_b"]
LOCK = "select 1 from gba.construction_projects where id = %s for update"
ENABLED = [
    "booking_resources",
    "counterparties",
    "finance",
    "finance_documents",
    "construction",
    "inventory",
    "workforce",
]
# 10 sheets at 15.00 cost (Framing) and 3.3333 m2 of tile at 10.00 cost (Finishes): 150.00 + 33.33.
TWO_LINES = [
    line(),
    line("FAKE tile", quantity="3.3333", cost=1000, price=1800, phase="Finishes", unit="m2"),
]


@dataclass(frozen=True)
class Costs:
    c: Construction
    stock: Stock
    workforce: Workforce
    crew: dict[str, str]
    profile: str
    supplier: UUID
    chart: dict[str, UUID]
    expense: UUID
    revenue: UUID

    @property
    def tenant(self) -> UUID:
        return self.c.tenant


async def _party(c: Construction, name: str, roles: list[str]) -> UUID:
    counterparty = uuid7()
    saved = await c.client.put(
        f"/v1/businesses/{c.tenant}/counterparties/{counterparty}",
        json=card(display_name=name, roles=roles),
        headers={**c.headers, "Idempotency-Key": str(uuid7())},
    )
    assert saved.status_code == 200, saved.text
    return counterparty


@pytest.fixture
def stocked(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only fixtures stand in for the STOCK-01 acceptance; the registry stays as it is."""
    current = modules.MODULES_BY_ID["inventory"]
    monkeypatch.setitem(
        modules.MODULES_BY_ID,
        "inventory",
        current.model_copy(
            update={"enableable": True, "readiness": Readiness.TECHNICALLY_VERIFIED}
        ),
    )


@pytest.fixture
async def costs(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager_a: FakeUser,
    idp: FakeIdp,
    owner_conn: psycopg.Connection,
    app_pool: RuntimePool,
    accepted: None,
    stocked: None,
) -> Costs:
    tenant = world.a.tenant_id
    config = Config(client, idp)
    await config.profile(manager_a, tenant, 0, [19])
    await config.publish(manager_a, tenant, 0, ENABLED)
    headers = idp.bearer(manager_a.subject, email=manager_a.email)
    c = Construction(client, world, owner_conn, idp, headers, uuid7())
    customer = await _party(c, "FAKE Homeowner", ["customer"])
    c = Construction(client, world, owner_conn, idp, headers, customer)
    supplier = await _party(c, "FAKE Lumber Yard", ["supplier"])
    inventory = Inventory(client, world, idp, owner_conn, manager_a, headers)
    entity, book, accounts = await entity_with_book(inventory, app_pool, "FAKE")
    place = await inventory.place(world.a.location_id)
    stock = Stock(inventory, app_pool, entity, book, accounts, place)
    rules = await stock.set_rules()
    assert rules.status_code == 200, rules.text
    async with tenant_transaction(app_pool, tenant) as conn:
        listed = await ledger.list_accounts(conn, tenant, book, after=None, limit=100)
    expense = next(a.account_id for a in listed.items if a.type == "expense")
    revenue = next(a.account_id for a in listed.items if a.type == "revenue")
    # A crew member of branch a with a staff profile; the manager approves the time.
    user = seed_user(owner_conn, f"o3b-crew-{uuid7()}")
    add_membership(
        owner_conn,
        tenant_id=tenant,
        user_id=user.user_id,
        role="artist",
        location_id=world.a.location_id,
    )
    with owner_tenant_transaction(owner_conn, tenant):
        found = owner_conn.execute(
            "select id from gba.memberships where user_id=%s", (user.user_id,)
        ).fetchone()
    assert found is not None
    workforce = Workforce(client, world, headers, found[0], user)
    profile = await workforce.profile()
    return Costs(
        c,
        stock,
        workforce,
        idp.bearer(user.subject, email=user.email),
        str(profile["profile_id"]),
        supplier,
        accounts,
        expense,
        revenue,
    )


# Facts ------------------------------------------------------------------------------


async def signed_in(
    c: Construction,
    lines: list[dict[str, Any]] | None = None,
    location: UUID | None = None,
    currency: str = "USD",
) -> UUID:
    """A project, in a branch and currency, whose first estimate version became the contract."""
    project = uuid7()
    branch = c.world.a.location_id if location is None else location
    saved = await c.project(project, currency=currency, location_id=str(branch))
    assert saved.status_code == 200, saved.text
    made = await c.estimate(project, lines or [line()])
    assert made.status_code == 200, made.text
    assert (await c.propose(project, 1)).status_code == 200
    contract = await accept(c, project, 1)
    assert contract.status_code == 200, contract.text
    return project


async def written_off(k: Costs, used: str = "4") -> tuple[UUID, UUID]:
    """10 pieces in for 25.00; `used` written off at the 2.50 average: (receipt, write-off)."""
    item = await k.stock.inventory.item(
        code=f"FAKE-{uuid7().hex[-8:].upper()}", unit="pcs", quantity_scale=0
    )
    receipt, write_off = uuid7(), uuid7()
    received = await k.stock.post(
        k.stock.receipt([{"item_id": item["item_id"], "quantity": "10", "amount": "25.00"}]),
        receipt,
    )
    assert received.status_code == 200, received.text
    gone = await k.stock.post(
        k.stock.receipt(
            [{"item_id": item["item_id"], "quantity": used}], kind="write_off", reason="used"
        ),
        write_off,
    )
    assert gone.status_code == 200, gone.text
    return receipt, write_off


async def billed(
    k: Costs,
    amount: str = "40.00",
    *,
    route: str = "accruals",
    direction: str = "payable",
    issue: bool = True,
) -> tuple[UUID, UUID, UUID]:
    """A FIN-03 document with one line (draft or issued): (book, document, line id)."""
    book, document, line_id = k.stock.book, uuid7(), uuid7()
    base = f"/v1/businesses/{k.tenant}/financial-documents/books/{book}/{route}"
    payable = direction == "payable"
    body = {
        "schema_version": 1,
        "expected_revision": 0,
        "direction": direction,
        "counterparty_id": str(k.supplier if payable else k.c.customer),
        "counterparty_revision": 1,
        "currency": "USD",
        "invoice_date": "2026-10-01",
        "control_account_id": str(k.chart["2000" if payable else "1200"]),
        "title": "FAKE lumber delivery",
        "number": f"FAKE-{document.hex[-8:]}",
        "lines": [
            {
                "line_id": str(line_id),
                "counter_account_id": str(k.expense if payable else k.revenue),
                "description": "FAKE studs and plates",
                "amount": amount,
            }
        ],
    }
    saved = await k.c.client.put(
        f"{base}/{document}", json=body, headers={**k.c.headers, "Idempotency-Key": str(uuid7())}
    )
    assert saved.status_code == 200, saved.text
    if issue:
        issued = await k.c.client.post(
            f"{base}/{document}/issue",
            json={
                "schema_version": 1,
                "expected_revision": 1,
                "entry_date": "2026-10-01",
                "attestation": "confirmed_account_treatment",
            },
            headers={**k.c.headers, "Idempotency-Key": str(uuid7())},
        )
        assert issued.status_code == 200, issued.text
    return book, document, line_id


async def _event(
    k: Costs, entry: dict[str, Any], action: str, headers: dict[str, str], **extra: Any
) -> dict[str, Any]:
    answer = await k.c.client.post(
        f"{k.workforce.base}/time-entries/{entry['entry_id']}/events",
        headers={**headers, "Idempotency-Key": str(uuid7())},
        json={
            "schema_version": 1,
            "expected_revision": entry["revision"],
            "action": action,
            **extra,
        },
    )
    assert answer.status_code == 200, answer.text
    return dict(answer.json())


async def worked(k: Costs, hour: int, until: str = "approve") -> UUID:
    """An entry from `hour` for an hour with a 10-minute break (50 minutes), left at `until`."""
    entry = uuid7()
    started = await k.c.client.put(
        f"{k.workforce.base}/time-entries/{entry}",
        headers={**k.crew, "Idempotency-Key": str(uuid7())},
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "staff_profile_id": k.profile,
            "starts_at": at(hour).isoformat(),
        },
    )
    assert started.status_code == 200, started.text
    current = dict(started.json())
    if until == "open":
        return entry
    current = await _event(k, current, "break_start", k.crew, at=at(hour, 20).isoformat())
    current = await _event(k, current, "break_end", k.crew, at=at(hour, 30).isoformat())
    current = await _event(k, current, "clock_out", k.crew, at=at(hour + 1).isoformat())
    if until == "approve":
        await _event(k, current, "approve", k.c.headers)
    elif until == "decline":
        await _event(k, current, "decline", k.c.headers, reason="FAKE declined")
    return entry


def from_stock(document: UUID, line_no: int = 1) -> dict[str, Any]:
    return {"kind": "stock_write_off", "stock_document_id": str(document), "stock_line_no": line_no}


def from_payable(book: UUID, document: UUID, line_id: UUID) -> dict[str, Any]:
    return {
        "kind": "payable",
        "book_id": str(book),
        "document_id": str(document),
        "line_id": str(line_id),
    }


def from_time(entry: UUID, rate: int) -> dict[str, Any]:
    return {"kind": "time_entry", "time_entry_id": str(entry), "rate_per_hour_minor": rate}


async def link(
    k: Costs,
    project: UUID,
    fact: dict[str, Any],
    change_order: int | None = None,
    position: int = 1,
    headers: dict[str, str] | None = None,
    key: str | None = None,
    **changes: Any,
) -> httpx.Response:
    body = {"change_order": change_order, "position": position, **fact, **changes}
    return await k.c.send("POST", f"/projects/{project}/costs", body, headers, key)


async def reverse(
    k: Costs,
    project: UUID,
    number: int,
    headers: dict[str, str] | None = None,
    reason: str = "FAKE booked to the wrong project",
) -> httpx.Response:
    return await k.c.send(
        "POST", f"/projects/{project}/costs/{number}/reversal", {"reason": reason}, headers
    )


async def budget_of(k: Costs, project: UUID) -> dict[str, Any]:
    read = await k.c.get(f"/projects/{project}/budget")
    assert read.status_code == 200, read.text
    return dict(read.json())


def actual(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        item["change_order"],
        item["position"],
        item["phase"],
        item["budget_minor"],
        item["committed_minor"],
        item["actual_minor"],
        item["remaining_minor"],
        item["over_budget"],
    )


async def _counts(pool: RuntimePool, tenant: UUID) -> tuple[int, int]:
    async with tenant_transaction(pool, tenant) as conn:
        found = await (
            await conn.execute(
                "select (select count(*) from gba.construction_cost_links), "
                "(select count(*) from gba.construction_cost_reversals)"
            )
        ).fetchone()
    assert found is not None
    return int(found[0]), int(found[1])


# O3b-01 ----------------------------------------------------------------------------


async def test_a_write_off_line_links_at_its_valuation(costs: Costs) -> None:
    k = costs
    project = await signed_in(k.c)
    receipt, write_off = await written_off(k)
    key = str(uuid7())
    linked = await link(k, project, from_stock(write_off), key=key, note="FAKE studs used on site")
    assert linked.status_code == 200, linked.text
    view = linked.json()
    assert {name: value for name, value in view.items() if name != "linked_at"} == {
        "schema_version": 1,
        "project_id": str(project),
        "number": 1,
        "kind": "stock_write_off",
        "change_order": None,
        "position": 1,
        "amount_minor": 1000,
        "currency": "USD",
        "note": "FAKE studs used on site",
        "attempt": 1,
        "stock_document_id": str(write_off),
        "stock_line_no": 1,
        "book_id": None,
        "document_id": None,
        "document_revision": None,
        "line_id": None,
        "time_entry_id": None,
        "time_entry_revision": None,
        "worked_microseconds": None,
        "rate_per_hour_minor": None,
        "reversal": None,
    }
    replay = await link(k, project, from_stock(write_off), key=key, note="FAKE studs used on site")
    assert (replay.status_code, replay.json()) == (200, view), replay.text
    assert (await k.c.get(f"/projects/{project}/costs/1")).json() == view
    listed = await k.c.get(f"/projects/{project}/costs")
    assert (listed.status_code, listed.json()["items"]) == (200, [view]), listed.text
    lines = (await budget_of(k, project))["lines"]
    assert [actual(item) for item in lines] == [(None, 1, "Framing", 15000, 0, 1000, 14000, False)]
    # A receipt line, an unknown line or document and an unknown budget line are no write-off line.
    for fact, position in (
        (from_stock(receipt), 1),
        (from_stock(write_off, 2), 1),
        (from_stock(uuid7()), 1),
    ):
        refused = await link(k, project, fact, position=position)
        assert error(refused) == (422, "INVALID_REFERENCE"), (fact, refused.text)
    _, other = await written_off(k, "1")
    unknown_line = await link(k, project, from_stock(other), position=9)
    assert error(unknown_line) == (422, "INVALID_REFERENCE"), unknown_line.text
    # A project in another branch does not take this branch's write-off.
    away, _ = seed_other_branch(k.c.owner_conn, k.c.world.a)
    elsewhere = await signed_in(k.c, location=away)
    wrong_branch = await link(k, elsewhere, from_stock(other))
    assert error(wrong_branch) == (422, "INVALID_REFERENCE"), wrong_branch.text
    # A project in another currency does not take a USD valuation.
    euros = await signed_in(k.c, currency="EUR")
    wrong_currency = await link(k, euros, from_stock(other))
    assert error(wrong_currency) == (409, "CONSTRUCTION_COST_CURRENCY"), wrong_currency.text
    # No contract, no budget line to put a cost on.
    bare = uuid7()
    assert (await k.c.project(bare)).status_code == 200
    early = await link(k, bare, from_stock(other))
    assert error(early) == (409, "CONSTRUCTION_NO_CONTRACT"), early.text
    assert (await link(k, project, from_stock(other))).status_code == 200


# O3b-02 ----------------------------------------------------------------------------


async def test_a_payable_line_links_at_its_amount(costs: Costs) -> None:
    k = costs
    project = await signed_in(k.c, TWO_LINES)
    book, accrual, accrual_line = await billed(k, "40.00")
    linked = await link(k, project, from_payable(book, accrual, accrual_line))
    assert linked.status_code == 200, linked.text
    view = linked.json()
    assert (view["kind"], view["amount_minor"], view["currency"]) == ("payable", 4000, "USD")
    assert (view["book_id"], view["document_id"], view["line_id"]) == (
        str(book),
        str(accrual),
        str(accrual_line),
    )
    assert view["document_revision"] == 2
    _, invoice, invoice_line = await billed(k, "12.34", route="invoices")
    second = await link(k, project, from_payable(book, invoice, invoice_line), position=2)
    assert (second.status_code, second.json()["amount_minor"]) == (200, 1234), second.text
    # A draft, an issued receivable and an unknown line are not issued payable lines.
    _, draft, draft_line = await billed(k, "9.00", issue=False)
    _, sale, sale_line = await billed(k, "9.00", route="invoices", direction="receivable")
    for fact in (
        from_payable(book, draft, draft_line),
        from_payable(book, sale, sale_line),
        from_payable(book, accrual, uuid7()),
        from_payable(uuid7(), accrual, accrual_line),
    ):
        refused = await link(k, project, fact)
        assert error(refused) == (422, "INVALID_REFERENCE"), (fact, refused.text)
    _, spare, spare_line = await billed(k, "5.00")
    euros = await signed_in(k.c, currency="EUR")
    wrong_currency = await link(k, euros, from_payable(book, spare, spare_line))
    assert error(wrong_currency) == (409, "CONSTRUCTION_COST_CURRENCY"), wrong_currency.text
    assert [actual(item) for item in (await budget_of(k, project))["lines"]] == [
        (None, 1, "Framing", 15000, 0, 4000, 11000, False),
        (None, 2, "Finishes", 3333, 0, 1234, 2099, False),
    ]


# O3b-03 ----------------------------------------------------------------------------


async def test_an_approved_time_entry_links_at_worked_time_and_the_rate(costs: Costs) -> None:
    k = costs
    project = await signed_in(k.c)
    entry = await worked(k, 8)
    # 50 minutes at 33.33 an hour: 3000 s x 3333 / 3600 = 2777.5, rounded half up.
    linked = await link(k, project, from_time(entry, 3333))
    assert linked.status_code == 200, linked.text
    view = linked.json()
    assert (view["kind"], view["amount_minor"], view["currency"]) == ("time_entry", 2778, "USD")
    assert (view["time_entry_id"], view["time_entry_revision"]) == (str(entry), 5)
    assert (view["worked_microseconds"], view["rate_per_hour_minor"]) == (3_000_000_000, 3333)
    later = await worked(k, 14)
    # A proposed, a declined and an open entry have no approved time (one open entry per person).
    for until, hour in (("clock_out", 10), ("decline", 12), ("open", 16)):
        unapproved = await worked(k, hour, until)
        refused = await link(k, project, from_time(unapproved, 3333))
        assert error(refused) == (422, "INVALID_REFERENCE"), (until, refused.text)
    # The rate belongs to a time entry and only to it.
    for fact in (
        {"kind": "time_entry", "time_entry_id": str(later)},
        from_time(later, 0),
        {**from_stock(uuid7()), "rate_per_hour_minor": 3333},
    ):
        invalid = await link(k, project, fact)
        assert invalid.status_code == 422, (fact, invalid.text)
    away, _ = seed_other_branch(k.c.owner_conn, k.c.world.a)
    elsewhere = await signed_in(k.c, location=away)
    wrong_branch = await link(k, elsewhere, from_time(later, 3333))
    assert error(wrong_branch) == (422, "INVALID_REFERENCE"), wrong_branch.text


# O3b-04 ----------------------------------------------------------------------------


async def test_a_fact_links_once_and_again_after_its_reversal(costs: Costs) -> None:
    k = costs
    first, second = await signed_in(k.c), await signed_in(k.c)
    _, write_off = await written_off(k)
    assert (await link(k, first, from_stock(write_off))).status_code == 200
    for project in (first, second):
        again = await link(k, project, from_stock(write_off))
        assert error(again) == (409, "CONSTRUCTION_COST_ALREADY_LINKED"), again.text
    undone = await reverse(k, first, 1)
    assert undone.status_code == 200, undone.text
    reversal = undone.json()["reversal"]
    assert reversal["reason"] == "FAKE booked to the wrong project"
    assert set(reversal) == {"reason", "reversed_at"}
    twice = await reverse(k, first, 1)
    assert error(twice) == (409, "CONSTRUCTION_COST_REVERSED"), twice.text
    missing = await reverse(k, first, 2)
    assert error(missing) == (404, "NOT_FOUND"), missing.text
    moved = await link(k, second, from_stock(write_off))
    assert moved.status_code == 200, moved.text
    assert (moved.json()["number"], moved.json()["attempt"]) == (1, 2)
    assert [actual(item)[5] for item in (await budget_of(k, first))["lines"]] == [0]
    assert [actual(item)[5] for item in (await budget_of(k, second))["lines"]] == [1000]
    listed = (await k.c.get(f"/projects/{first}/costs")).json()["items"]
    assert [(item["number"], item["reversal"] is not None) for item in listed] == [(1, True)]


async def test_two_racing_links_of_one_fact_leave_one(
    costs: Costs, app_pool: RuntimePool, test_database: ProvisionedDatabase
) -> None:
    k = costs
    project = await signed_in(k.c)
    _, write_off = await written_off(k)
    answers = await race(
        app_pool,
        test_database,
        k.tenant,
        LOCK,
        project,
        [link(k, project, from_stock(write_off)), link(k, project, from_stock(write_off))],
    )
    assert sorted(a.status_code for a in answers) == [200, 409], [a.text for a in answers]
    (lost,) = [a for a in answers if a.status_code == 409]
    assert error(lost) == (409, "CONSTRUCTION_COST_ALREADY_LINKED")
    assert await _counts(app_pool, k.tenant) == (1, 0)


# O3b-05 ----------------------------------------------------------------------------


async def test_two_racing_reversals_leave_one(
    costs: Costs, app_pool: RuntimePool, test_database: ProvisionedDatabase
) -> None:
    k = costs
    project = await signed_in(k.c)
    _, write_off = await written_off(k)
    assert (await link(k, project, from_stock(write_off))).status_code == 200
    answers = await race(
        app_pool,
        test_database,
        k.tenant,
        LOCK,
        project,
        [reverse(k, project, 1), reverse(k, project, 1, reason="FAKE duplicate")],
    )
    assert sorted(a.status_code for a in answers) == [200, 409], [a.text for a in answers]
    (lost,) = [a for a in answers if a.status_code == 409]
    assert error(lost) == (409, "CONSTRUCTION_COST_REVERSED")
    assert await _counts(app_pool, k.tenant) == (1, 1)


async def _forged(pool: RuntimePool, tenant: UUID, project: UUID, **columns: str) -> str:
    """Link 2 written by SQL as a copy of link 1 with some columns replaced; the refused check."""
    chosen = {"number": "2", "attempt": "2", "amount_minor": "amount_minor", "currency": "currency"}
    chosen.update(columns)
    with pytest.raises(psycopg.errors.CheckViolation) as refused:
        async with tenant_transaction(pool, tenant) as conn:
            await conn.execute(
                "insert into gba.construction_cost_links (tenant_id, project_id, number, kind, "
                "change_order, budget_position, stock_document_id, stock_line_no, fact_key, "
                "attempt, amount_minor, currency, created_by) "
                f"select tenant_id, project_id, {chosen['number']}, kind, change_order, "
                f"budget_position, stock_document_id, stock_line_no, fact_key, "
                f"{chosen['attempt']}, {chosen['amount_minor']}, {chosen['currency']}, created_by "
                "from gba.construction_cost_links where project_id = %s and number = 1",
                (project,),
            )
    return str(refused.value.diag.constraint_name)


async def test_sql_keeps_links_and_reversals_whole(costs: Costs, app_pool: RuntimePool) -> None:
    k = costs
    project = await signed_in(k.c)
    _, write_off = await written_off(k)
    assert (await link(k, project, from_stock(write_off))).status_code == 200
    for statement in (
        "update gba.construction_cost_links set amount_minor = 1",
        "delete from gba.construction_cost_links",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with tenant_transaction(app_pool, k.tenant) as conn:
                await conn.execute(statement)
    # While link 1 counts, a second link of its fact is refused.
    assert await _forged(app_pool, k.tenant, project) == "construction_cost_links_attempt_check"
    assert (await reverse(k, project, 1)).status_code == 200
    for statement in (
        "update gba.construction_cost_reversals set reason = 'FAKE'",
        "delete from gba.construction_cost_reversals",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with tenant_transaction(app_pool, k.tenant) as conn:
                await conn.execute(statement)
    forged = {
        "construction_cost_links_amount_check": {"amount_minor": "amount_minor + 1"},
        "construction_cost_links_currency_check": {"currency": "'EUR'"},
        "construction_cost_links_attempt_check": {"attempt": "3"},
        "construction_cost_links_sequence_check": {"number": "3"},
    }
    for constraint, columns in forged.items():
        assert await _forged(app_pool, k.tenant, project, **columns) == constraint, columns
    assert await _counts(app_pool, k.tenant) == (1, 1)


# O3b-06 ----------------------------------------------------------------------------


async def test_actual_remaining_and_over_budget_per_line_phase_and_total(costs: Costs) -> None:
    k = costs
    project = await signed_in(k.c, TWO_LINES)
    crew = await _party(k.c, "FAKE Framing Crew", ["contractor"])
    assert (
        await commit(k.c, project, "subcontract", crew, [budgeted(None, 1, 8000)])
    ).status_code == 200
    _, write_off = await written_off(k)
    book, accrual, accrual_line = await billed(k, "40.00")
    _, over, over_line = await billed(k, "50.00")
    entry = await worked(k, 8)
    for fact, position in (
        (from_stock(write_off), 1),
        (from_payable(book, accrual, accrual_line), 1),
        (from_time(entry, 3333), 2),
        (from_payable(book, over, over_line), 2),
    ):
        made = await link(k, project, fact, position=position)
        assert made.status_code == 200, made.text
    view = await budget_of(k, project)
    # Framing: 10.00 + 40.00 against 150.00; Finishes: 27.78 + 50.00 against 33.33, over.
    assert [actual(item) for item in view["lines"]] == [
        (None, 1, "Framing", 15000, 8000, 5000, 10000, False),
        (None, 2, "Finishes", 3333, 0, 7778, -4445, True),
    ]
    assert [
        (p["phase"], p["budget_minor"], p["committed_minor"], p["actual_minor"])
        for p in view["phases"]
    ] == [("Framing", 15000, 8000, 5000), ("Finishes", 3333, 0, 7778)]
    assert [p["remaining_minor"] for p in view["phases"]] == [10000, -4445]
    assert (view["budget_minor"], view["actual_minor"], view["remaining_minor"]) == (
        18333,
        12778,
        5555,
    )
    assert (await reverse(k, project, 4, reason="FAKE billed twice")).status_code == 200
    after = await budget_of(k, project)
    assert [actual(item)[5:] for item in after["lines"]] == [
        (5000, 10000, False),
        (2778, 555, False),
    ]
    assert (after["actual_minor"], after["remaining_minor"]) == (7778, 10555)


# O3b-07 ----------------------------------------------------------------------------


async def test_without_the_module_costs_are_refused_and_scope_holds(
    costs: Costs,
    app_pool: RuntimePool,
    idp: FakeIdp,
    manager_a: FakeUser,
    manager_b: FakeUser,
) -> None:
    k = costs
    world: BookingWorld = k.c.world
    project = await signed_in(k.c)
    _, write_off = await written_off(k)
    _, spare = await written_off(k, "1")
    assert (await link(k, project, from_stock(write_off))).status_code == 200
    # Front desk links and reverses nothing.
    staff = k.c.member("front_desk", None)
    refused = await link(k, project, from_stock(spare), headers=staff)
    assert refused.status_code == 403, refused.text
    unreversed = await reverse(k, project, 1, headers=staff)
    assert unreversed.status_code == 403, unreversed.text
    # A manager of another branch does not see the costs.
    away, _ = seed_other_branch(k.c.owner_conn, world.a)
    elsewhere = k.c.member("manager", away)
    for path in ("costs", "costs/1"):
        hidden = await k.c.get(f"/projects/{project}/{path}", headers=elsewhere)
        assert error(hidden) == (404, "NOT_FOUND"), (path, hidden.text)
    blind = await link(k, project, from_stock(spare), headers=elsewhere)
    assert error(blind) == (404, "NOT_FOUND"), blind.text
    # Another company sees nothing.
    other = idp.bearer(manager_b.subject, email=manager_b.email)
    foreign = await k.c.get(f"/projects/{project}/costs", headers=other)
    assert foreign.status_code in (403, 404), foreign.text
    assert await _counts(app_pool, world.b.tenant_id) == (0, 0)
    # Turned off: links and reversals are refused and write nothing; reads continue.
    before = await _counts(app_pool, k.tenant)
    assert before == (1, 0)
    await Config(k.c.client, idp).publish(
        manager_a, k.tenant, 1, [name for name in ENABLED if name != "construction"]
    )
    for answer in (
        await link(k, project, from_stock(spare)),
        await reverse(k, project, 1),
    ):
        assert error(answer) == (409, "MODULE_DISABLED"), answer.text
    assert await _counts(app_pool, k.tenant) == before
    listed = await k.c.get(f"/projects/{project}/costs")
    assert (listed.status_code, len(listed.json()["items"])) == (200, 1), listed.text
    assert (await budget_of(k, project))["actual_minor"] == 1000
