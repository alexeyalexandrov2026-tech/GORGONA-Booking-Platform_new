"""O5: construction pay applications with retainage (package O, BUILD-01; FAKE data only).

docs/plan/PACKAGE_O5_DESIGN_2026-11-01.md: a versioned retainage rate; a pay application closes a
billing period and bills completed value as of its end minus earlier billing; retainage is held
rounded down; the amount due is a FIN-03 receivable invoice and the retained amount a separate
receivable accrual without a due date; billed never exceeds the contract sum.
"""

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.business import ledger
from gorgona_booking.business.ledger_contracts import AccountInput
from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from tests.integration.booking_support import BookingWorld
from tests.integration.configuration_support import Config
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.seed import FakeUser, seed_other_branch
from tests.integration.test_counterparties import card
from tests.integration.test_inventory import Inventory
from tests.integration.test_l8b2_finance_races import race
from tests.integration.test_o1_construction_estimates import (
    Construction,
    accepted,
    client,
    error,
    idp,
    manager_a,
    manager_b,
)
from tests.integration.test_o2_construction_contract import change, decide, remove
from tests.integration.test_o4a_construction_execution import (
    LOCK,
    TWO_LINES,
    ago,
    measure,
    signed_at,
    today,
)
from tests.integration.test_stock import entity_with_book
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
__all__ = ["accepted", "client", "idp", "manager_a", "manager_b"]
ENABLED = ["booking_resources", "counterparties", "finance", "finance_documents", "construction"]
TABLES = (
    "construction_retainage_rates",
    "construction_pay_applications",
    "construction_pay_application_lines",
)
NONE = (0, 0, 0)
CONTRACT = 31007  # 10 sheets at 25.00 and 3.3333 m2 of tile at 18.02 (6006.6066 rounds to 6007)


@dataclass(frozen=True)
class Billing:
    c: Construction
    book: UUID
    chart: dict[str, UUID]
    retainage: UUID

    @property
    def tenant(self) -> UUID:
        return self.c.tenant

    @property
    def documents(self) -> str:
        return f"/v1/businesses/{self.tenant}/financial-documents/books/{self.book}"


@pytest.fixture
async def billing(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager_a: FakeUser,
    idp: FakeIdp,
    owner_conn: psycopg.Connection,
    app_pool: RuntimePool,
    accepted: None,
) -> Billing:
    tenant = world.a.tenant_id
    config = Config(client, idp)
    await config.profile(manager_a, tenant, 0, [19])
    await config.publish(manager_a, tenant, 0, ENABLED)
    headers = idp.bearer(manager_a.subject, email=manager_a.email)
    customer = uuid7()
    saved = await client.put(
        f"/v1/businesses/{tenant}/counterparties/{customer}",
        json=card(display_name="FAKE Homeowner", roles=["customer"]),
        headers={**headers, "Idempotency-Key": str(uuid7())},
    )
    assert saved.status_code == 200, saved.text
    c = Construction(client, world, owner_conn, idp, headers, customer)
    inventory = Inventory(client, world, idp, owner_conn, manager_a, headers)
    _, book, chart = await entity_with_book(inventory, app_pool, "FAKE")
    retainage = uuid7()
    async with tenant_transaction(app_pool, tenant) as conn:
        await ledger.save_account(
            conn,
            business_id=tenant,
            book_id=book,
            account_id=retainage,
            user_id=manager_a.user_id,
            actor=f"user:{manager_a.user_id}",
            key=str(uuid7()),
            body=AccountInput(
                expected_revision=0, code="1210", type="asset", name="FAKE Retainage receivable"
            ),
        )
    return Billing(c, book, chart, retainage)


async def rate(
    b: Billing,
    project: UUID,
    revision: int,
    basis_points: int,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    body = {"expected_revision": revision, "rate_bp": basis_points}
    return await b.c.send("PUT", f"/projects/{project}/retainage", body, headers)


def pay_body(b: Billing, period_end: str, **changes: Any) -> dict[str, Any]:
    return {
        "period_end": period_end,
        "book_id": str(b.book),
        "receivable_account_id": str(b.chart["1200"]),
        "revenue_account_id": str(b.chart["4100"]),
        "retainage_account_id": str(b.retainage),
        "invoice_date": period_end,
        "due_date": (today() + timedelta(days=30)).isoformat(),
        "number": f"FAKE-PA-{uuid7().hex[-8:]}",
        **changes,
    }


async def pay(
    b: Billing,
    project: UUID,
    period_end: str,
    headers: dict[str, str] | None = None,
    key: str | None = None,
    **changes: Any,
) -> httpx.Response:
    body = pay_body(b, period_end, **changes)
    return await b.c.send("POST", f"/projects/{project}/pay-applications", body, headers, key)


def amounts(view: dict[str, Any]) -> tuple[Any, ...]:
    return (
        view["number"],
        view["period_end"],
        view["rate_revision"],
        view["rate_bp"],
        view["previous_billed_minor"],
        view["billed_to_date_minor"],
        view["this_period_minor"],
        view["retained_minor"],
        view["due_minor"],
    )


def billed_lines(view: dict[str, Any]) -> list[tuple[Any, ...]]:
    return [
        (
            item["change_order"],
            item["position"],
            Decimal(item["completed"]),
            item["value_to_date_minor"],
            item["previous_minor"],
            item["this_period_minor"],
        )
        for item in view["lines"]
    ]


async def issue(b: Billing, route: str, document: str, on: str) -> httpx.Response:
    return await b.c.client.post(
        f"{b.documents}/{route}/{document}/issue",
        json={
            "schema_version": 1,
            "expected_revision": 1,
            "entry_date": on,
            "attestation": "confirmed_account_treatment",
        },
        headers={**b.c.headers, "Idempotency-Key": str(uuid7())},
    )


async def draft(
    b: Billing,
    route: str,
    document: UUID,
    control: UUID,
    amount: str,
    revision: int = 0,
    number: str | None = None,
) -> httpx.Response:
    """A FIN-03 receivable draft to the project's customer, through FIN-03 itself."""
    body = {
        "schema_version": 1,
        "expected_revision": revision,
        "direction": "receivable",
        "counterparty_id": str(b.c.customer),
        "counterparty_revision": 1,
        "currency": "USD",
        "invoice_date": ago(8),
        "control_account_id": str(control),
        "title": "FAKE edited here",
        "number": number or f"FAKE-X-{document.hex[-8:]}",
        "lines": [
            {
                "line_id": str(uuid7()),
                "counter_account_id": str(b.chart["4100"]),
                "description": "FAKE work",
                "amount": amount,
            }
        ],
    }
    return await b.c.client.put(
        f"{b.documents}/{route}/{document}",
        json=body,
        headers={**b.c.headers, "Idempotency-Key": str(uuid7())},
    )


async def _counts(pool: RuntimePool, tenant: UUID) -> tuple[int, ...]:
    query = "select " + ", ".join(f"(select count(*) from gba.{table})" for table in TABLES)
    async with tenant_transaction(pool, tenant) as conn:
        found = await (await conn.execute(query)).fetchone()
    assert found is not None
    return tuple(int(n) for n in found)


async def _together(
    pool: RuntimePool, tenant: UUID, statements: tuple[tuple[str, tuple[Any, ...]], ...]
) -> None:
    async with tenant_transaction(pool, tenant) as conn:
        for statement, params in statements:
            await conn.execute(statement, params)


async def _refused_by(
    pool: RuntimePool, tenant: UUID, *statements: tuple[str, tuple[Any, ...]]
) -> str:
    """The constraint the database names when it refuses these statements in one transaction."""
    with pytest.raises(psycopg.errors.CheckViolation) as refused:
        await _together(pool, tenant, statements)
    return str(refused.value.diag.constraint_name)


# O5-01 ------------------------------------------------------------------------------


async def test_the_retainage_rate_is_versioned(billing: Billing, app_pool: RuntimePool) -> None:
    b = billing
    bare = uuid7()
    assert (await b.c.project(bare)).status_code == 200
    for early in (await rate(b, bare, 0, 1000), await b.c.get(f"/projects/{bare}/retainage")):
        assert error(early) == (409, "CONSTRUCTION_NO_CONTRACT"), early.text
    project = await signed_at(b.c, TWO_LINES)
    none = (await b.c.get(f"/projects/{project}/retainage")).json()
    assert (none["revision"], none["rate_bp"], none["recorded_at"]) == (0, 0, None)
    first = await rate(b, project, 0, 1000)
    assert first.status_code == 200, first.text
    assert (first.json()["revision"], first.json()["rate_bp"]) == (1, 1000)
    stale = await rate(b, project, 0, 500)
    assert error(stale) == (409, "CONSTRUCTION_REVISION_CONFLICT"), stale.text
    for wrong in (5001, -1):
        refused = await rate(b, project, 1, wrong)
        assert error(refused) == (422, "INVALID_REQUEST"), (wrong, refused.text)
    second = await rate(b, project, 1, 0)
    assert (second.status_code, second.json()["revision"], second.json()["rate_bp"]) == (
        200,
        2,
        0,
    )
    assert (await b.c.get(f"/projects/{project}/retainage")).json() == second.json()
    assert await _counts(app_pool, b.tenant) == (2, 0, 0)


# O5-02 ------------------------------------------------------------------------------


async def test_an_application_bills_completed_value_and_holds_retainage(
    billing: Billing, app_pool: RuntimePool
) -> None:
    b = billing
    project = await signed_at(b.c, TWO_LINES)
    assert (await rate(b, project, 0, 1000)).status_code == 200
    assert (await measure(b.c, project, 1, "4", ago(10))).status_code == 200
    key = str(uuid7())
    body = pay_body(b, ago(8))
    first = await b.c.send("POST", f"/projects/{project}/pay-applications", body, None, key)
    assert first.status_code == 200, first.text
    view = first.json()
    assert amounts(view) == (1, ago(8), 1, 1000, 0, 10000, 10000, 1000, 9000)
    assert billed_lines(view) == [
        (None, 1, Decimal(4), 10000, 0, 10000),
        (None, 2, Decimal(0), 0, 0, 0),
    ]
    invoice, held = view["invoice"], view["retainage"]
    assert (
        invoice["kind"],
        invoice["direction"],
        invoice["counterparty_id"],
        invoice["control_account_id"],
        invoice["state"],
        invoice["total"],
        invoice["number"],
        invoice["due_date"],
    ) == (
        "invoice",
        "receivable",
        str(b.c.customer),
        str(b.chart["1200"]),
        "draft",
        "90.00",
        body["number"],
        body["due_date"],
    )
    assert [(x["counter_account_id"], x["amount"]) for x in invoice["lines"]] == [
        (str(b.chart["4100"]), "90.00")
    ]
    assert (
        held["kind"],
        held["direction"],
        held["control_account_id"],
        held["total"],
        held["number"],
        held["due_date"],
    ) == ("manual_accrual", "receivable", str(b.retainage), "10.00", body["number"] + "-R", None)
    assert [(x["counter_account_id"], x["amount"]) for x in held["lines"]] == [
        (str(b.chart["4100"]), "10.00")
    ]
    again = await b.c.send("POST", f"/projects/{project}/pay-applications", body, None, key)
    assert (again.status_code, again.json()) == (200, view)
    # FIN-03 keeps both drafts as the application wrote them.
    for route, document, control in (
        ("invoices", invoice["document_id"], b.chart["1200"]),
        ("accruals", held["document_id"], b.retainage),
    ):
        edited = await draft(b, route, UUID(document), control, "1.00", revision=1)
        assert error(edited) == (409, "FINANCIAL_DOCUMENT_LINKED"), (route, edited.text)
    # Issued, they are two obligations; the retained one has no due date.
    obligations = set()
    for route, document in (
        ("invoices", invoice["document_id"]),
        ("accruals", held["document_id"]),
    ):
        issued = await issue(b, route, document, ago(8))
        assert issued.status_code == 200, (route, issued.text)
        obligations.add(issued.json()["obligation_id"])
    assert len(obligations) == 2
    # A new rate applies to later applications only.
    assert (await rate(b, project, 1, 500)).status_code == 200
    assert (await measure(b.c, project, 1, "7", ago(5))).status_code == 200
    assert (await measure(b.c, project, 2, "1.1111", ago(5))).status_code == 200
    second = await pay(b, project, ago(3))
    assert second.status_code == 200, second.text
    # 17500 + 2002 = 19502; 9502 x 5% = 475.1, held 475.
    assert amounts(second.json()) == (2, ago(3), 2, 500, 10000, 19502, 9502, 475, 9027)
    assert billed_lines(second.json()) == [
        (None, 1, Decimal(7), 17500, 10000, 7500),
        (None, 2, Decimal("1.1111"), 2002, 0, 2002),
    ]
    kept = (await b.c.get(f"/projects/{project}/pay-applications/1")).json()
    assert amounts(kept) == amounts(view)
    assert (kept["invoice"]["state"], kept["retainage"]["state"]) == ("issued", "issued")
    listed = (await b.c.get(f"/projects/{project}/pay-applications")).json()
    assert (
        listed["currency"],
        listed["contract_minor"],
        listed["billed_to_date_minor"],
        listed["retained_minor"],
        listed["due_minor"],
        listed["remaining_minor"],
    ) == ("USD", CONTRACT, 19502, 1475, 18027, CONTRACT - 19502)
    assert [
        (
            i["number"],
            i["period_end"],
            i["this_period_minor"],
            i["retained_minor"],
            i["due_minor"],
            i["invoice_state"],
            i["retainage_state"],
        )
        for i in listed["items"]
    ] == [
        (1, ago(8), 10000, 1000, 9000, "issued", "issued"),
        (2, ago(3), 9502, 475, 9027, "draft", "draft"),
    ]
    missing = await b.c.get(f"/projects/{project}/pay-applications/9")
    assert error(missing) == (404, "NOT_FOUND"), missing.text
    same_account = await pay(b, project, ago(1), retainage_account_id=str(b.chart["1200"]))
    assert error(same_account) == (422, "INVALID_REQUEST"), same_account.text
    assert await _counts(app_pool, b.tenant) == (2, 2, 4)


# O5-03 ------------------------------------------------------------------------------


async def test_one_application_per_period(billing: Billing) -> None:
    b = billing
    bare = uuid7()
    assert (await b.c.project(bare)).status_code == 200
    early = await pay(b, bare, ago(1))
    assert error(early) == (409, "CONSTRUCTION_NO_CONTRACT"), early.text
    project = await signed_at(b.c, TWO_LINES)
    nothing = await pay(b, project, ago(5))
    assert error(nothing) == (409, "CONSTRUCTION_NOTHING_TO_BILL"), nothing.text
    assert (await measure(b.c, project, 1, "2", ago(6))).status_code == 200
    first = await pay(b, project, ago(5))
    assert first.status_code == 200, first.text
    assert first.json()["retainage"] is None  # no rate yet: nothing held, no accrual
    for period in (ago(5), ago(6)):
        again = await pay(b, project, period)
        assert error(again) == (409, "CONSTRUCTION_PERIOD_BILLED"), (period, again.text)
    ahead = await pay(b, project, (today() + timedelta(days=2)).isoformat())
    assert error(ahead) == (422, "CONSTRUCTION_FUTURE_DATE"), ahead.text
    idle = await pay(b, project, ago(4))
    assert error(idle) == (409, "CONSTRUCTION_NOTHING_TO_BILL"), idle.text
    # The billed period is closed for measurements; corrections are dated after it.
    closed = await measure(b.c, project, 1, "3", ago(5))
    assert error(closed) == (409, "CONSTRUCTION_PERIOD_BILLED"), closed.text
    assert (await measure(b.c, project, 1, "3", ago(4))).status_code == 200
    second = await pay(b, project, ago(3))
    assert second.status_code == 200, second.text
    assert (second.json()["billed_to_date_minor"], second.json()["this_period_minor"]) == (
        7500,
        2500,
    )
    # A line may bill less than before when its measurement was corrected; the total grows.
    lower = await measure(b.c, project, 1, "2", ago(2), note="FAKE recount")
    assert lower.status_code == 200, lower.text
    assert (await measure(b.c, project, 2, "3.3333", ago(2))).status_code == 200
    third = await pay(b, project, ago(1))
    assert third.status_code == 200, third.text
    assert amounts(third.json())[4:7] == (7500, 11007, 3507)
    assert billed_lines(third.json()) == [
        (None, 1, Decimal(2), 5000, 7500, -2500),
        (None, 2, Decimal("3.3333"), 6007, 0, 6007),
    ]


# O5-04 ------------------------------------------------------------------------------


async def test_billed_never_exceeds_the_contract_sum(billing: Billing) -> None:
    b = billing
    done = await signed_at(b.c, TWO_LINES)
    assert (await measure(b.c, done, 1, "10", ago(4))).status_code == 200
    assert (await measure(b.c, done, 2, "3.3333", ago(4))).status_code == 200
    whole = await pay(b, done, ago(3))
    assert whole.status_code == 200, whole.text
    contract = (await b.c.get(f"/projects/{done}/contract")).json()["current_price_minor"]
    assert contract == CONTRACT
    assert amounts(whole.json())[5:] == (CONTRACT, CONTRACT, 0, CONTRACT)
    assert whole.json()["invoice"]["total"] == "310.07"
    listed = (await b.c.get(f"/projects/{done}/pay-applications")).json()
    assert (listed["billed_to_date_minor"], listed["remaining_minor"]) == (CONTRACT, 0)
    more = await pay(b, done, ago(1))
    assert error(more) == (409, "CONSTRUCTION_NOTHING_TO_BILL"), more.text
    # A removal may not take the contract below what was billed.
    project = await signed_at(b.c, TWO_LINES)
    assert (await measure(b.c, project, 1, "8", ago(6))).status_code == 200
    assert (await pay(b, project, ago(5))).status_code == 200  # 20000 billed
    corrected = await measure(b.c, project, 1, "2", ago(4), note="FAKE wrong count")
    assert corrected.status_code == 200, corrected.text
    assert (await change(b.c, project, [remove(1, "7")])).status_code == 200
    below = await decide(b.c, project, 1, "approved")
    assert error(below) == (409, "CONSTRUCTION_BELOW_BILLED"), below.text
    assert (await b.c.get(f"/projects/{project}/change-orders/1")).json()["state"] == "proposed"
    assert (await change(b.c, project, [remove(1, "1")])).status_code == 200
    assert (await decide(b.c, project, 2, "approved")).status_code == 200
    after = (await b.c.get(f"/projects/{project}/pay-applications")).json()
    assert (after["contract_minor"], after["billed_to_date_minor"]) == (28507, 20000)


# O5-05 ------------------------------------------------------------------------------


async def test_two_racing_applications_for_one_period_leave_one(
    billing: Billing, app_pool: RuntimePool, test_database: ProvisionedDatabase
) -> None:
    b = billing
    project = await signed_at(b.c, TWO_LINES)
    assert (await measure(b.c, project, 1, "4", ago(3))).status_code == 200
    answers = await race(
        app_pool,
        test_database,
        b.tenant,
        LOCK,
        project,
        [pay(b, project, ago(2)), pay(b, project, ago(2))],
    )
    assert sorted(a.status_code for a in answers) == [200, 409], [a.text for a in answers]
    (lost,) = [a for a in answers if a.status_code == 409]
    assert error(lost) == (409, "CONSTRUCTION_PERIOD_BILLED"), lost.text
    assert await _counts(app_pool, b.tenant) == (0, 1, 2)
    async with tenant_transaction(app_pool, b.tenant) as conn:
        found = await (
            await conn.execute("select count(*) from gba.financial_documents")
        ).fetchone()
    assert found is not None
    assert int(found[0]) == 1  # the loser drafted nothing in FIN-03


# O5-04 and O5-06: the database itself -----------------------------------------------


async def test_sql_keeps_applications_whole(billing: Billing, app_pool: RuntimePool) -> None:
    b = billing
    tenant = b.tenant
    project = await signed_at(b.c, TWO_LINES)
    assert (await rate(b, project, 0, 1000)).status_code == 200
    assert (await measure(b.c, project, 1, "4", ago(10))).status_code == 200
    assert (await pay(b, project, ago(8))).status_code == 200
    for table in TABLES:
        for statement in (
            f"update gba.{table} set tenant_id = tenant_id",
            f"delete from gba.{table}",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                async with tenant_transaction(app_pool, tenant) as conn:
                    await conn.execute(statement)
    head = (
        "insert into gba.construction_pay_applications (tenant_id, project_id, number, period_end, "
        "previous_billed_minor, billed_to_date_minor, this_period_minor, rate_revision, rate_bp, "
        "retained_minor, due_minor, book_id, invoice_document_id, retainage_document_id, "
        "created_by) select tenant_id, project_id, {number}, {period}, {previous}, {billed}, "
        "{this}, rate_revision, {rate}, {retained}, {due}, book_id, {invoice}, {retainage}, "
        "created_by from gba.construction_pay_applications where project_id = %s and number = 1"
    )
    valid = {
        "number": "2",
        "period": "period_end + 1",
        "previous": "billed_to_date_minor",
        "billed": "billed_to_date_minor + 10000",
        "this": "10000",
        "rate": "rate_bp",
        "retained": "1000",
        "due": "9000",
        "invoice": "invoice_document_id",
        "retainage": "retainage_document_id",
    }
    huge = "99999999 - billed_to_date_minor"
    forged = {
        "construction_pay_applications_sequence_check": {"number": "5"},
        "construction_pay_applications_period_check": {"period": "period_end"},
        "construction_pay_applications_date_check": {"period": "current_date + 2"},
        "construction_pay_applications_previous_check": {"previous": "0"},
        "construction_pay_applications_amounts_check": {"retained": "500", "due": "9500"},
        "construction_pay_applications_rate_check": {
            "rate": "2500",
            "retained": "2500",
            "due": "7500",
        },
        "construction_pay_applications_contract_check": {
            "billed": "99999999",
            "this": huge,
            "retained": f"floor(({huge}) * 0.1)::bigint",
            "due": f"({huge}) - floor(({huge}) * 0.1)::bigint",
        },
        "construction_pay_applications_document_check": {
            "billed": "billed_to_date_minor + 20000",
            "this": "20000",
            "retained": "2000",
            "due": "18000",
        },
    }
    for constraint, changes in forged.items():
        statement = head.format(**{**valid, **changes})
        assert await _refused_by(app_pool, tenant, (statement, (project,))) == constraint
    # Fresh FIN-03 drafts with the right amounts let a forged header pass; its lines may not.
    invoice, held = uuid7(), uuid7()
    assert (await draft(b, "invoices", invoice, b.chart["1200"], "90.00")).status_code == 200
    assert (await draft(b, "accruals", held, b.retainage, "10.00")).status_code == 200
    header = head.format(**{**valid, "invoice": f"'{invoice}'", "retainage": f"'{held}'"})
    lines = (
        "insert into gba.construction_pay_application_lines (tenant_id, project_id, number, "
        "change_order, budget_position, quantity_to_date, value_to_date_minor) "
        "select tenant_id, project_id, {number}, change_order, budget_position, {quantity}, "
        "value_to_date_minor from gba.construction_pay_application_lines "
        "where project_id = %s and number = 1 {only}"
    )
    cases = {
        "construction_pay_application_lines_record_check": [
            (lines.format(number="1", quantity="quantity_to_date", only=""), (project,))
        ],
        "construction_pay_application_lines_quantity_check": [
            (header, (project,)),
            (
                lines.format(number="2", quantity="5", only="and budget_position = 1"),
                (project,),
            ),
        ],
        "construction_pay_applications_lines_check": [
            (header, (project,)),
            (lines.format(number="2", quantity="quantity_to_date", only=""), (project,)),
        ],
        "construction_progress_measurements_period_check": [
            (
                "insert into gba.construction_progress_measurements (tenant_id, project_id, "
                "number, change_order, budget_position, measured_on, quantity_to_date, note, "
                "created_by) select tenant_id, project_id, 2, null, 1, measured_on + 2, 5, null, "
                "created_by from gba.construction_progress_measurements "
                "where project_id = %s and number = 1",
                (project,),
            )
        ],
    }
    for constraint, statements in cases.items():
        assert await _refused_by(app_pool, tenant, *statements) == constraint, constraint
    # An approval may not take the contract below the billed 10000.
    corrected = await measure(b.c, project, 1, "1", ago(7), note="FAKE recount")
    assert corrected.status_code == 200, corrected.text
    assert (await change(b.c, project, [remove(1, "9")])).status_code == 200
    approval = (
        "insert into gba.construction_change_order_decisions (tenant_id, project_id, number, "
        "decision, source, decided_by) select tenant_id, project_id, number, 'approved', "
        "'paper', created_by from gba.construction_change_orders "
        "where project_id = %s and number = 1"
    )
    refused = await _refused_by(app_pool, tenant, (approval, (project,)))
    assert refused == "construction_change_order_decisions_billed_check"
    assert await _counts(app_pool, tenant) == (1, 1, 2)


# O5-06 ------------------------------------------------------------------------------


async def test_without_the_module_billing_is_refused_and_scope_holds(
    billing: Billing,
    app_pool: RuntimePool,
    idp: FakeIdp,
    manager_a: FakeUser,
    manager_b: FakeUser,
) -> None:
    b = billing
    c = b.c
    world: BookingWorld = c.world
    project = await signed_at(c, TWO_LINES)
    assert (await rate(b, project, 0, 1000)).status_code == 200
    assert (await measure(c, project, 1, "4", ago(3))).status_code == 200
    assert (await pay(b, project, ago(2))).status_code == 200
    # Front desk writes nothing here.
    staff = c.member("front_desk", None)
    for refused in (
        await rate(b, project, 1, 500, headers=staff),
        await pay(b, project, ago(1), headers=staff),
    ):
        assert refused.status_code == 403, refused.text
    # A manager of another branch does not see the project's billing.
    away, _ = seed_other_branch(c.owner_conn, world.a)
    elsewhere = c.member("manager", away)
    for path in ("retainage", "pay-applications", "pay-applications/1"):
        hidden = await c.get(f"/projects/{project}/{path}", headers=elsewhere)
        assert error(hidden) == (404, "NOT_FOUND"), (path, hidden.text)
    # Another company sees nothing.
    other = idp.bearer(manager_b.subject, email=manager_b.email)
    foreign = await c.get(f"/projects/{project}/pay-applications", headers=other)
    assert foreign.status_code in (403, 404), foreign.text
    assert await _counts(app_pool, world.b.tenant_id) == NONE
    # Turned off: writes are refused and write nothing; reads continue.
    before = await _counts(app_pool, c.tenant)
    assert before == (1, 1, 2)
    await Config(c.client, idp).publish(
        manager_a, c.tenant, 1, ["booking_resources", "counterparties"]
    )
    for answer in (await rate(b, project, 1, 500), await pay(b, project, ago(1))):
        assert error(answer) == (409, "MODULE_DISABLED"), answer.text
    assert await _counts(app_pool, c.tenant) == before
    for path in ("retainage", "pay-applications", "pay-applications/1"):
        read = await c.get(f"/projects/{project}/{path}")
        assert read.status_code == 200, (path, read.text)
