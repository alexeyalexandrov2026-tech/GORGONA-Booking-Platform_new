"""J2 posting rules and receipts with amounts against real PostgreSQL 18."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.auth.principal import set_user_context
from gorgona_booking.business import ledger
from gorgona_booking.business.ledger_contracts import BookInput
from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import (
    add_membership,
    grant_platform_admin,
    owner_tenant_transaction,
)
from tests.integration import test_inventory as shared
from tests.integration.configuration_support import Config
from tests.integration.seed import seed_other_branch, seed_user
from tests.integration.test_counterparties import card
from tests.integration.test_inventory import Inventory, error, refused_sql

pytestmark = pytest.mark.anyio
inventory = shared.inventory
accepted = shared.accepted
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
DAY = "2026-10-01"
MONEY_TABLES = ("stock_document_postings", "stock_valuations", "stock_costs")
DOCUMENT_TABLES = (
    "stock_documents",
    "stock_document_lines",
    "stock_movements",
    "stock_balances",
    *MONEY_TABLES,
)
RULE_CODES = {
    "inventory": "1300",
    "receipt": "1400",
    "opening": "3900",
    "surplus": "4900",
    "consumption": "5000",
    "loss": "6900",
    "difference": "6900",
}
# What a document line reads when it returns nothing: only a return line names a source.
NO_SOURCE: dict[str, object] = {"source_line_no": None, "source_amount": None}


@dataclass(frozen=True)
class Stock:
    inventory: Inventory
    pool: RuntimePool
    entity: UUID
    book: UUID
    accounts: dict[str, UUID]
    place: dict[str, object]

    @property
    def tenant(self) -> UUID:
        return self.inventory.tenant

    @property
    def ledger(self) -> str:
        return f"/v1/businesses/{self.tenant}/ledger/books/{self.book}"

    def keyed(self) -> dict[str, str]:
        return {**self.inventory.headers, "Idempotency-Key": str(uuid7())}

    def rules(self, expected: int = 0, **codes: str) -> dict[str, object]:
        chosen = {**RULE_CODES, **codes}
        return {
            "expected_revision": expected,
            **{f"{name}_account_id": str(self.accounts[code]) for name, code in chosen.items()},
        }

    async def set_rules(
        self, expected: int = 0, accounts: dict[str, str] | None = None, **codes: str
    ) -> httpx.Response:
        body = {**self.rules(expected, **codes), **(accounts or {})}
        return await self.inventory.put(f"/posting-rules/{self.book}", body)

    async def account(self, code: str, kind: str, name: str, revision: int, archived: bool) -> None:
        saved = await self.inventory.client.put(
            f"{self.ledger}/accounts/{self.accounts[code]}",
            json={
                "schema_version": 1,
                "expected_revision": revision,
                "code": code,
                "type": kind,
                "name": name,
                "archived": archived,
            },
            headers=self.keyed(),
        )
        assert saved.status_code == 200, saved.text

    def receipt(self, lines: list[dict[str, object]], **changes: object) -> dict[str, object]:
        return {
            "kind": "receipt",
            "reason": "purchase",
            "legal_entity_id": str(self.entity),
            "place_id": self.place["place_id"],
            "document_date": DAY,
            "lines": lines,
            **changes,
        }

    async def post(
        self,
        body: dict[str, object],
        document: UUID | None = None,
        key: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        return await self.inventory.put(f"/documents/{document or uuid7()}", body, key, headers)

    def rows(self, statement: str, *values: object) -> list[tuple[object, ...]]:
        with owner_tenant_transaction(self.inventory.owner_conn, self.tenant):
            return self.inventory.owner_conn.execute(statement.encode("utf-8"), values).fetchall()

    def counts(self) -> dict[str, int]:
        counted = {
            table: int(str(self.rows(f"select count(*) from gba.{table}")[0][0]))
            for table in DOCUMENT_TABLES
        }
        entries = self.rows("select count(*) from gba.journal_entries where source_kind='stock'")
        return {**counted, "stock_entries": int(str(entries[0][0]))}

    def reconciled(self) -> tuple[int, int]:
        """Rule 14: the value of the materials and the stock lines on the inventory account.

        Its quantity half is asserted here: for every material of the owner the cost
        quantity, the balances of all places and the signed movements agree.
        """
        apart = self.rows(
            "select c.item_id from gba.stock_costs c where c.legal_entity_id=%s and ("
            "c.quantity<>(select coalesce(sum(b.quantity),0) from gba.stock_balances b "
            "where b.tenant_id=c.tenant_id and b.legal_entity_id=c.legal_entity_id "
            "and b.item_id=c.item_id) or c.quantity<>(select coalesce(sum(case m.direction "
            "when 'in' then m.quantity else -m.quantity end),0) from gba.stock_movements m "
            "where m.tenant_id=c.tenant_id and m.legal_entity_id=c.legal_entity_id "
            "and m.item_id=c.item_id))",
            self.entity,
        )
        assert apart == [], apart
        value = self.rows(
            "select coalesce(sum(value_minor),0) from gba.stock_costs where legal_entity_id=%s",
            self.entity,
        )
        posted = self.rows(
            "select coalesce(sum(case l.side when 'debit' then l.amount_minor "
            "else -l.amount_minor end),0) from gba.journal_lines l join gba.journal_entries e "
            "on e.tenant_id=l.tenant_id and e.id=l.entry_id "
            "where e.source_kind='stock' and e.book_id=%s and l.account_id=%s",
            self.book,
            self.accounts["1300"],
        )
        return int(str(value[0][0])), int(str(posted[0][0]))


async def entity_with_book(
    owner: Inventory, pool: RuntimePool, code: str, *, book: bool = True
) -> tuple[UUID, UUID, dict[str, UUID]]:
    entity, book_id = uuid7(), uuid7()
    created = await owner.client.put(
        f"/v1/businesses/{owner.tenant}/legal-entities/{entity}",
        json={"expected_revision": 0, "code": code, "legal_name": f"FAKE {code} LLC"},
        headers={**owner.headers, "Idempotency-Key": str(uuid7())},
    )
    assert created.status_code == 200, created.text
    if not book:
        return entity, book_id, {}
    async with tenant_transaction(pool, owner.tenant) as conn:
        await ledger.save_book(
            conn,
            business_id=owner.tenant,
            book_id=book_id,
            user_id=owner.manager.user_id,
            actor=f"user:{owner.manager.user_id}",
            key=str(uuid7()),
            body=BookInput(
                expected_revision=0,
                legal_entity_id=entity,
                base_currency="USD",
                fiscal_year_start_month=1,
                accounting_start=date(2026, 1, 1),
            ),
        )
        accounts = await ledger.list_accounts(conn, owner.tenant, book_id, after=None, limit=100)
    return entity, book_id, {account.code: account.account_id for account in accounts.items}


@pytest.fixture
async def stock(inventory: Inventory, app_pool: RuntimePool) -> Stock:
    entity, book, accounts = await entity_with_book(inventory, app_pool, "FAKE")
    place = await inventory.place(inventory.world.a.location_id)
    return Stock(inventory, app_pool, entity, book, accounts, place)


async def test_posting_rules_are_versioned_and_checked(stock: Stock) -> None:
    path = f"/posting-rules/{stock.book}"
    assert error(await stock.inventory.get(path)) == (404, "NOT_FOUND")
    key = str(uuid7())
    created = await stock.inventory.put(path, stock.rules(), key)
    assert created.status_code == 200, created.text
    assert created.json() == {
        "schema_version": 1,
        "business_id": str(stock.tenant),
        "book_id": str(stock.book),
        "revision": 1,
        **{name: value for name, value in stock.rules().items() if name != "expected_revision"},
    }
    assert (await stock.inventory.put(path, stock.rules(), key)).json() == created.json()
    reused = await stock.inventory.put(path, stock.rules(surplus="5000"), key)
    assert error(reused) == (422, "IDEMPOTENCY_KEY_REUSED"), reused.text
    assert error(await stock.set_rules()) == (409, "INVENTORY_CONFLICT")

    # The inventory account is an asset and differs from the rest; receipts take an asset
    # or an expense account; every account is an open account of this book.
    same = await stock.set_rules(1, receipt="1300")
    assert error(same) == (422, "INVALID_REQUEST"), same.text
    for refused in (
        await stock.set_rules(1, inventory="2000"),
        await stock.set_rules(1, receipt="2000"),
    ):
        assert error(refused) == (422, "INVALID_REFERENCE"), refused.text
    _, _, foreign = await entity_with_book(stock.inventory, stock.pool, "OTHER")
    other_book = await stock.set_rules(1, {"surplus_account_id": str(foreign["4900"])})
    assert error(other_book) == (422, "INVALID_REFERENCE"), other_book.text
    await stock.account("6900", "expense", "Other expenses", 1, True)
    closed = await stock.set_rules(1, surplus="4000")
    assert error(closed) == (422, "INVALID_REFERENCE"), closed.text
    changed = await stock.set_rules(1, loss="6400", difference="6400", surplus="4000")
    assert (changed.status_code, changed.json()["revision"]) == (200, 2), changed.text
    assert (await stock.inventory.get(path)).json() == changed.json()
    assert (await stock.inventory.get(path, revision=1)).json() == created.json()

    # Rules belong to finance: a branch manager and staff neither read nor set them.
    for role, location in (("manager", stock.inventory.world.a.location_id), ("artist", None)):
        headers = stock.inventory.member(role, location)[1]
        assert (await stock.inventory.get(path, headers=headers)).status_code == 403
        denied = await stock.inventory.put(path, stock.rules(2), headers=headers)
        assert denied.status_code == 403, denied.text
    assert stock.rows("select count(*) from gba.stock_posting_rules") == [(2,)]


async def test_receipts_post_movements_cost_and_one_journal_entry(stock: Stock) -> None:
    assert (await stock.set_rules()).status_code == 200
    dye = await stock.inventory.item(code="DYE", unit="ml", quantity_scale=1)
    foil = await stock.inventory.item(code="FOIL", unit="pcs", quantity_scale=0)
    document = uuid7()
    lines: list[dict[str, object]] = [
        {"item_id": dye["item_id"], "quantity": "12.5", "amount": "25.00"},
        {"item_id": foil["item_id"], "quantity": "3", "amount": "9.99"},
    ]
    posted = await stock.post(stock.receipt(lines), document)
    assert posted.status_code == 200, posted.text
    view = posted.json()
    entry = view["money"]["entry_id"]
    assert {name: value for name, value in view.items() if name != "created_at"} == {
        "schema_version": 1,
        "business_id": str(stock.tenant),
        "document_id": str(document),
        "kind": "receipt",
        "reason": "purchase",
        "legal_entity_id": str(stock.entity),
        "place_id": stock.place["place_id"],
        "location_id": stock.place["location_id"],
        "to_place_id": None,
        "to_location_id": None,
        "source_document_id": None,
        "document_date": DAY,
        "supplier_id": None,
        "supplier_document": None,
        "lines": [{"line_no": number, **line, **NO_SOURCE} for number, line in enumerate(lines, 1)],
        "money": {
            "book_id": str(stock.book),
            "rule_revision": 1,
            "currency": "USD",
            "total": "34.99",
            "entry_id": entry,
        },
    }
    assert (await stock.inventory.get(f"/documents/{document}")).json() == view

    # One journal entry of the document: inventory debited, the receipt account credited.
    second = {"schema_version": "2"}
    journal = await stock.inventory.client.get(
        f"{stock.ledger}/entries/{entry}", params=second, headers=stock.inventory.headers
    )
    assert journal.status_code == 200, journal.text
    assert (journal.json()["source_kind"], journal.json()["source_id"]) == ("stock", str(document))
    assert (journal.json()["entry_date"], journal.json()["total"]) == (DAY, "34.99")
    assert [
        (line["account_code"], line["side"], line["amount"]) for line in journal.json()["lines"]
    ] == [("1300", "debit", "34.99"), ("1400", "credit", "34.99")]
    listed = await stock.inventory.client.get(
        f"{stock.ledger}/entries", params=second, headers=stock.inventory.headers
    )
    assert [item["source_kind"] for item in listed.json()["items"]] == ["stock"]

    # An opening balance and a surplus use their own accounts; a zero total posts no entry.
    opening = await stock.post(
        stock.receipt(
            [{"item_id": dye["item_id"], "quantity": "7.5", "amount": "30"}],
            reason="opening_balance",
        )
    )
    assert opening.status_code == 200, opening.text
    gift = [{"item_id": foil["item_id"], "quantity": "1", "amount": "0"}]
    free = await stock.post(stock.receipt(gift, reason="surplus"))
    assert free.status_code == 200, free.text
    assert free.json()["money"] == {
        "book_id": str(stock.book),
        "rule_revision": 1,
        "currency": "USD",
        "total": "0.00",
        "entry_id": None,
    }
    found = [{"item_id": foil["item_id"], "quantity": "2", "amount": "5.01"}]
    paid = await stock.post(stock.receipt(found, reason="surplus"))
    assert paid.status_code == 200, paid.text
    credited = stock.rows(
        "select d.reason,a.code,l.amount_minor from gba.stock_documents d "
        "join gba.stock_document_postings p on p.tenant_id=d.tenant_id and p.document_id=d.id "
        "join gba.journal_lines l on l.tenant_id=p.tenant_id and l.entry_id=p.entry_id "
        "join gba.ledger_accounts a on a.tenant_id=l.tenant_id and a.id=l.account_id "
        "where l.side='credit' order by d.id"
    )
    assert credited == [
        ("purchase", "1400", 3499),
        ("opening_balance", "3900", 3000),
        ("surplus", "4900", 501),
    ]

    # Quantities by place, cost by material and owner, and the books agree.
    assert stock.counts() == {
        "stock_documents": 4,
        "stock_document_lines": 5,
        "stock_movements": 5,
        "stock_balances": 2,
        "stock_document_postings": 4,
        "stock_valuations": 5,
        "stock_costs": 2,
        "stock_entries": 3,
    }
    balances = await stock.inventory.get("/balances")
    assert {(row["item_id"], row["quantity"]) for row in balances.json()["items"]} == {
        (dye["item_id"], "20.0"),
        (foil["item_id"], "6"),
    }
    assert {row["place_id"] for row in balances.json()["items"]} == {stock.place["place_id"]}
    costs = await stock.inventory.get("/costs")
    assert {
        (row["item_id"], row["quantity"], row["value"], row["currency"])
        for row in costs.json()["items"]
    } == {(dye["item_id"], "20.0", "55.00", "USD"), (foil["item_id"], "6", "15.00", "USD")}
    assert stock.reconciled() == (7000, 7000)
    both = {dye["item_id"], foil["item_id"]}
    for path in ("/balances", "/costs"):
        first = await stock.inventory.get(path, limit=1)
        more = await stock.inventory.get(path, limit=1, after=first.json()["next_cursor"])
        assert more.json()["next_cursor"] is None, path
        assert {page.json()["items"][0]["item_id"] for page in (first, more)} == both, path
    narrowed = await stock.inventory.get(
        "/balances", item_id=str(dye["item_id"]), place_id=str(stock.place["place_id"])
    )
    assert [row["quantity"] for row in narrowed.json()["items"]] == ["20.0"]
    elsewhere = await stock.inventory.get("/balances", place_id=str(uuid7()))
    assert elsewhere.json()["items"] == []
    documents = (await stock.inventory.get("/documents")).json()["items"]
    assert (len(documents), documents[0]["document_id"]) == (4, str(document))
    assert documents[0]["line_count"] == 2
    page = await stock.inventory.get("/documents", limit=3)
    rest = await stock.inventory.get("/documents", limit=3, after=page.json()["next_cursor"])
    assert (len(page.json()["items"]), len(rest.json()["items"])) == (3, 1)
    assert rest.json()["next_cursor"] is None

    # The audit names the document, its kind and its line count, never names or amounts.
    audit = stock.rows(
        "select action,target_type,details from gba.audit_events where target_id=%s",
        str(document),
    )
    assert audit == [("inventory.document", "stock_document", {"kind": "receipt", "lines": 2})]


async def test_receipt_command_is_idempotent(stock: Stock) -> None:
    assert (await stock.set_rules()).status_code == 200
    item = await stock.inventory.item(quantity_scale=0)
    body = stock.receipt([{"item_id": item["item_id"], "quantity": "4", "amount": "8.00"}])
    document, key = uuid7(), str(uuid7())
    first = await stock.post(body, document, key)
    assert first.status_code == 200, first.text
    counts = stock.counts()
    assert (await stock.post(body, document, key)).json() == first.json()
    other = await stock.post({**body, "reason": "surplus"}, document, key)
    assert error(other) == (422, "IDEMPOTENCY_KEY_REUSED"), other.text
    # A posted document is never posted again, even with a new key.
    again = await stock.post(body, document)
    assert error(again) == (409, "INVENTORY_CONFLICT"), again.text
    assert stock.counts() == counts
    assert stock.rows("select quantity from gba.stock_balances") == [(4,)]
    assert stock.rows("select quantity,value_minor from gba.stock_costs") == [(4, 800)]
    # One material on two lines at two prices adds up in one balance and one cost row.
    twice = await stock.post(
        stock.receipt(
            [
                {"item_id": item["item_id"], "quantity": "1", "amount": "1.00"},
                {"item_id": item["item_id"], "quantity": "2", "amount": "5.00"},
            ]
        )
    )
    assert (twice.status_code, twice.json()["money"]["total"]) == (200, "6.00"), twice.text
    assert stock.rows("select quantity from gba.stock_balances") == [(7,)]
    assert stock.rows("select quantity,value_minor from gba.stock_costs") == [(7, 1400)]
    assert stock.reconciled() == (1400, 1400)


async def test_receipt_takes_one_hundred_lines(stock: Stock) -> None:
    assert (await stock.set_rules()).status_code == 200
    item = await stock.inventory.item(quantity_scale=3)
    lines: list[dict[str, object]] = [
        {"item_id": item["item_id"], "quantity": f"0.{number:03d}", "amount": f"{number}.01"}
        for number in range(1, 101)
    ]
    posted = await stock.post(stock.receipt(lines))
    assert posted.status_code == 200, posted.text
    assert len(posted.json()["lines"]) == 100
    # 0.001 + ... + 0.100 of the unit, and 1.01 + ... + 100.01 of money.
    assert posted.json()["money"]["total"] == "5051.00"
    assert stock.rows("select quantity from gba.stock_balances") == [(5050,)]
    assert stock.rows("select quantity,value_minor from gba.stock_costs") == [(5050, 505100)]
    assert stock.counts()["stock_movements"] == 100
    assert stock.reconciled() == (505100, 505100)


async def hand_post(
    stock: Stock, item: str, *, credit: str = "1400", journal: int = 1000, valued: int = 1000
) -> None:
    """A receipt of 5 units for 10.00 written by SQL alone, the way the service writes it."""
    tenant, user = stock.tenant, stock.inventory.manager.user_id
    document, entry = uuid7(), uuid7()
    place, home = stock.place["place_id"], stock.place["location_id"]
    async with tenant_transaction(stock.pool, tenant) as conn:
        await set_user_context(conn, user)
        await conn.execute(
            "insert into gba.stock_documents (tenant_id,id,kind,reason,legal_entity_id,place_id,"
            "location_id,document_date,line_count,created_by) "
            "values (%s,%s,'receipt','purchase',%s,%s,%s,%s,1,%s)",
            (tenant, document, stock.entity, place, home, DAY, user),
        )
        await conn.execute(
            "insert into gba.stock_document_lines (tenant_id,document_id,line_no,location_id,"
            "item_id,quantity) values (%s,%s,1,%s,%s,5)",
            (tenant, document, home, item),
        )
        await conn.execute(
            "insert into gba.stock_document_postings (tenant_id,document_id,book_id,"
            "rule_revision,entry_id,total_minor,created_by) values (%s,%s,%s,1,%s,1000,%s)",
            (tenant, document, stock.book, entry, user),
        )
        await conn.execute(
            "insert into gba.stock_valuations (tenant_id,document_id,line_no,direction,"
            "legal_entity_id,item_id,quantity,amount_minor) values (%s,%s,1,'in',%s,%s,5,%s)",
            (tenant, document, stock.entity, item, valued),
        )
        await conn.execute(
            "insert into gba.stock_movements (tenant_id,document_id,line_no,direction,"
            "location_id,place_id,item_id,legal_entity_id,quantity) "
            "values (%s,%s,1,'in',%s,%s,%s,%s,5)",
            (tenant, document, home, place, item, stock.entity),
        )
        await conn.execute(
            "insert into gba.journal_entries (tenant_id,id,book_id,entry_date,currency,"
            "source_kind,source_id,created_by) values (%s,%s,%s,%s,'USD','stock',%s,%s)",
            (tenant, entry, stock.book, DAY, str(document), user),
        )
        for number, side, code in ((1, "debit", "1300"), (2, "credit", credit)):
            await conn.execute(
                "insert into gba.journal_lines (tenant_id,entry_id,line_no,book_id,account_id,"
                "side,amount_minor) values (%s,%s,%s,%s,%s,%s,%s)",
                (tenant, entry, number, stock.book, stock.accounts[code], side, journal),
            )


async def test_sql_receipt_needs_every_part_and_its_exact_journal(stock: Stock) -> None:
    assert (await stock.set_rules()).status_code == 200
    item = str((await stock.inventory.item(quantity_scale=0))["item_id"])
    # Written whole by SQL alone a receipt is accepted: the database holds the rules.
    await hand_post(stock, item)
    assert stock.reconciled() == (1000, 1000)
    # A wrong credit account, a journal of another amount and a line valued differently
    # from the total are refused at commit, and nothing of them remains.
    for attempt in (
        hand_post(stock, item, credit="3900"),
        hand_post(stock, item, journal=900),
        hand_post(stock, item, valued=900),
    ):
        with pytest.raises(psycopg.errors.CheckViolation):
            await attempt
    assert stock.counts()["stock_documents"] == 1
    assert stock.rows("select quantity,value_minor from gba.stock_costs") == [(5, 1000)]
    assert stock.reconciled() == (1000, 1000)


async def test_refused_receipts_leave_no_parts(stock: Stock) -> None:
    item = await stock.inventory.item(quantity_scale=1)
    line: dict[str, object] = {"item_id": item["item_id"], "quantity": "1.5", "amount": "3.00"}
    assert error(await stock.post(stock.receipt([line]))) == (409, "STOCK_RULES_REQUIRED")
    assert (await stock.set_rules()).status_code == 200
    bookless, _, _ = await entity_with_book(stock.inventory, stock.pool, "NOBOOK", book=False)
    missing = await stock.post(stock.receipt([line], legal_entity_id=str(bookless)))
    assert error(missing) == (409, "STOCK_BOOK_REQUIRED"), missing.text

    # Dates: not in the future of the branch, from the accounting start, in an open month.
    future = (datetime.now(UTC).date() + timedelta(days=2)).isoformat()
    for day in (future, "2025-12-31"):
        refused = await stock.post(stock.receipt([line], document_date=day))
        assert error(refused) == (422, "STOCK_DATE_INVALID"), refused.text
    closed = await stock.inventory.client.post(
        f"{stock.ledger}/periods/2026-09/close",
        json={"schema_version": 1, "expected_sequence": 0},
        headers=stock.keyed(),
    )
    assert closed.status_code == 200, closed.text
    late = await stock.post(stock.receipt([line], document_date="2026-09-15"))
    assert error(late) == (409, "LEDGER_PERIOD_CLOSED"), late.text

    # Quantities follow the scale of the material and amounts the scale of the currency;
    # extra decimals are refused, never rounded.
    for change, code in (
        ({"quantity": "1.25"}, "STOCK_QUANTITY_INVALID"),
        ({"quantity": "0"}, "STOCK_QUANTITY_INVALID"),
        ({"quantity": "0.0"}, "STOCK_QUANTITY_INVALID"),
        ({"amount": "3.001"}, "STOCK_AMOUNT_INVALID"),
    ):
        refused = await stock.post(stock.receipt([{**line, **change}]))
        assert error(refused) == (422, code), refused.text
        assert refused.json()["error"]["details"]["line"] == 1
    for change in ({"quantity": "-1"}, {"amount": "-1"}, {"quantity": "1e3"}, {"amount": ""}):
        malformed = await stock.post(stock.receipt([{**line, **change}]))
        assert error(malformed) == (422, "INVALID_REQUEST"), malformed.text
    for body in (
        stock.receipt([]),
        stock.receipt([line] * 101),
        stock.receipt([line], reason="used"),
        stock.receipt([line], kind="write_off"),
        stock.receipt([line], reason="surplus", supplier_document="INV-1"),
    ):
        assert error(await stock.post(body)) == (422, "INVALID_REQUEST")

    # References: a known open material, a known open place of this company, a supplier
    # that is an active counterparty with that role.
    unknown = await stock.post(stock.receipt([{**line, "item_id": str(uuid7())}]))
    assert error(unknown) == (422, "INVALID_REFERENCE"), unknown.text
    nowhere = await stock.post(stock.receipt([line], place_id=str(uuid7())))
    assert error(nowhere) == (422, "INVALID_REFERENCE"), nowhere.text
    await Config(stock.inventory.client, stock.inventory.idp).publish(
        stock.inventory.manager,
        stock.tenant,
        1,
        ["booking_resources", "counterparties", "finance", "inventory"],
    )
    customer, supplier = uuid7(), uuid7()
    for number, (counterparty, role) in enumerate(((customer, "customer"), (supplier, "supplier"))):
        saved = await stock.inventory.client.put(
            f"/v1/businesses/{stock.tenant}/counterparties/{counterparty}",
            json=card(
                roles=[role],
                display_name=f"FAKE {role}",
                email=f"fake.{role}@example.test",
                phone=f"+1 555 010 200{number}",
            ),
            headers=stock.keyed(),
        )
        assert saved.status_code == 200, saved.text
    for stranger in (customer, uuid7()):
        refused = await stock.post(stock.receipt([line], supplier_id=str(stranger)))
        assert error(refused) == (422, "INVALID_REFERENCE"), refused.text
    old = await stock.inventory.item(quantity_scale=1)
    retired = await stock.inventory.put(
        f"/items/{old['item_id']}", {**shared.material_input(old), "archived": True}
    )
    assert retired.status_code == 200, retired.text
    stale = await stock.post(stock.receipt([{**line, "item_id": old["item_id"]}]))
    assert error(stale) == (409, "STOCK_ARCHIVED"), stale.text
    shut = await stock.inventory.place(stock.inventory.world.a.location_id)
    emptied = await stock.inventory.put(
        f"/places/{shut['place_id']}",
        {
            "expected_revision": 1,
            "location_id": shut["location_id"],
            "code": shut["code"],
            "name": shut["name"],
            "archived": True,
        },
    )
    assert emptied.status_code == 200, emptied.text
    sealed = await stock.post(stock.receipt([line], place_id=shut["place_id"]))
    assert error(sealed) == (409, "STOCK_ARCHIVED"), sealed.text

    # An archived account of the entry is named before anything is written.
    await stock.account("1400", "asset", "Prepaid expenses", 1, True)
    broken = await stock.post(stock.receipt([line]))
    assert error(broken) == (409, "STOCK_ACCOUNT_ARCHIVED"), broken.text
    assert broken.json()["error"]["details"] == {"account_id": str(stock.accounts["1400"])}
    assert set(stock.counts().values()) == {0}

    # With the account reopened the same receipt posts, with its supplier.
    await stock.account("1400", "asset", "Prepaid expenses", 2, False)
    good = await stock.post(
        stock.receipt([line], supplier_id=str(supplier), supplier_document="INV-7")
    )
    assert good.status_code == 200, good.text
    assert (good.json()["supplier_id"], good.json()["supplier_document"]) == (
        str(supplier),
        "INV-7",
    )
    assert stock.reconciled() == (300, 300)


async def test_branch_scope_rights_and_hidden_amounts(stock: Stock) -> None:
    assert (await stock.set_rules()).status_code == 200
    world = stock.inventory.world
    home = world.a.location_id
    away, _ = seed_other_branch(stock.inventory.owner_conn, world.a)
    remote_place = await stock.inventory.place(away)
    item = await stock.inventory.item(quantity_scale=0)
    line: dict[str, object] = {"item_id": item["item_id"], "quantity": "5", "amount": "10.00"}
    here = await stock.post(stock.receipt([line]))
    there = await stock.post(stock.receipt([line], place_id=remote_place["place_id"]))
    assert (here.status_code, there.status_code) == (200, 200), here.text + there.text
    local, branch = stock.inventory.member("manager", home)

    # A branch manager posts no receipt and reads quantities of the branch without money.
    denied = await stock.post(stock.receipt([line]), headers=branch)
    assert error(denied) == (403, "PERMISSION_DENIED"), denied.text
    listed = await stock.inventory.get("/documents", headers=branch)
    assert [row["document_id"] for row in listed.json()["items"]] == [here.json()["document_id"]]
    seen = await stock.inventory.get(f"/documents/{here.json()['document_id']}", headers=branch)
    assert seen.status_code == 200, seen.text
    assert seen.json()["money"] is None
    assert seen.json()["lines"] == [
        {"line_no": 1, "item_id": item["item_id"], "quantity": "5", "amount": None, **NO_SOURCE}
    ]
    hidden = await stock.inventory.get(f"/documents/{there.json()['document_id']}", headers=branch)
    assert error(hidden) == (404, "NOT_FOUND")
    balances = await stock.inventory.get("/balances", headers=branch)
    assert [(row["place_id"], row["quantity"]) for row in balances.json()["items"]] == [
        (stock.place["place_id"], "5")
    ]
    for path in ("/costs", f"/posting-rules/{stock.book}"):
        assert (await stock.inventory.get(path, headers=branch)).status_code == 403
    everything = await stock.inventory.get("/balances")
    assert len(everything.json()["items"]) == 2

    # Direct SQL in the branch scope reads no amounts and writes no receipt.
    async with tenant_transaction(stock.pool, stock.tenant) as conn:
        await conn.execute("select set_config('gba.location_id',%s,true)", (str(home),))
        for table in MONEY_TABLES:
            count = f"select count(*) from gba.{table}".encode()
            assert await (await conn.execute(count)).fetchone() == (0,), table
        visible = await (await conn.execute("select count(*) from gba.stock_documents")).fetchone()
        assert visible == (1,)
    head = (
        "insert into gba.stock_documents (tenant_id,id,kind,reason,legal_entity_id,place_id,"
        "location_id,document_date,line_count,created_by) "
        "values (%s,%s,'receipt','surplus',%s,%s,%s,%s,1,%s)"
    )
    values = (stock.tenant, uuid7(), stock.entity, stock.place["place_id"], home, DAY)
    author = (*values, local.user_id)
    for scope in (home, None):
        assert (
            await refused_sql(stock.pool, stock.tenant, local.user_id, head, author, scope)
            == "42501"
        )

    # Staff, another company and platform support get nothing.
    foreign = seed_user(stock.inventory.owner_conn, f"foreign-{uuid7()}")
    support = seed_user(stock.inventory.owner_conn, f"support-{uuid7()}")
    add_membership(
        stock.inventory.owner_conn,
        tenant_id=world.b.tenant_id,
        user_id=foreign.user_id,
        role="owner",
    )
    grant_platform_admin(
        stock.inventory.owner_conn, user_id=support.user_id, granted_by="test:stock"
    )
    for headers in (
        stock.inventory.member("artist", home)[1],
        stock.inventory.member("front_desk")[1],
        stock.inventory.idp.bearer(foreign.subject, email=foreign.email),
        stock.inventory.idp.bearer(support.subject, email=support.email),
    ):
        for path in ("/documents", "/balances", "/costs", f"/posting-rules/{stock.book}"):
            assert (await stock.inventory.get(path, headers=headers)).status_code == 403, path
        assert (await stock.post(stock.receipt([line]), headers=headers)).status_code == 403
    assert stock.counts()["stock_documents"] == 2


async def test_sql_keeps_documents_whole_and_stock_entries_owned(stock: Stock) -> None:
    assert (await stock.set_rules()).status_code == 200
    tenant, user = stock.tenant, stock.inventory.manager.user_id
    item = await stock.inventory.item(quantity_scale=0)
    posted = await stock.post(
        stock.receipt([{"item_id": item["item_id"], "quantity": "5", "amount": "10.00"}])
    )
    assert posted.status_code == 200, posted.text
    document = UUID(posted.json()["document_id"])
    entry = UUID(posted.json()["money"]["entry_id"])
    place, home = stock.place["place_id"], stock.place["location_id"]

    async def refused(statement: str, *values: object) -> str:
        return await refused_sql(stock.pool, tenant, user, statement, values)

    # Nothing joins a posted document later, and no movement exists without a document.
    late_line = (
        "insert into gba.stock_document_lines (tenant_id,document_id,line_no,location_id,"
        "item_id,quantity) values (%s,%s,2,%s,%s,1)"
    )
    assert await refused(late_line, tenant, document, home, item["item_id"]) == "23514"
    movement = (
        "insert into gba.stock_movements (tenant_id,document_id,line_no,direction,location_id,"
        "place_id,item_id,legal_entity_id,quantity) values (%s,%s,%s,%s,%s,%s,%s,%s,5)"
    )
    moved = (home, place, item["item_id"], stock.entity)
    assert await refused(movement, tenant, document, 1, "out", *moved) == "23514"
    assert await refused(movement, tenant, document, 1, "in", *moved) in ("23505", "23514")
    assert await refused(movement, tenant, uuid7(), 1, "in", *moved) in ("23503", "23514")
    valuation = (
        "insert into gba.stock_valuations (tenant_id,document_id,line_no,direction,"
        "legal_entity_id,item_id,quantity,amount_minor) values (%s,%s,1,'in',%s,%s,5,1)"
    )
    assert await refused(valuation, tenant, document, stock.entity, item["item_id"]) in (
        "23505",
        "23514",
    )

    # Running totals follow their movements: a direct change does not survive the commit.
    for change in (
        "update gba.stock_balances set quantity=quantity+1 where tenant_id=%s",
        "update gba.stock_costs set value_minor=value_minor+1 where tenant_id=%s",
        "update gba.stock_costs set quantity=quantity+1 where tenant_id=%s",
    ):
        assert await refused(change, tenant) == "23514", change
    balance = (
        "insert into gba.stock_balances (tenant_id,item_id,place_id,legal_entity_id,"
        "location_id,quantity) values (%s,%s,%s,%s,%s,9)"
    )
    spare = (await stock.inventory.item())["item_id"]
    assert await refused(balance, tenant, spare, place, stock.entity, home) == "23514"

    # A stock journal entry needs its document and is never reversed by the ledger.
    journal = (
        "insert into gba.journal_entries (tenant_id,id,book_id,entry_date,currency,source_kind,"
        "source_id,reverses_entry_id,created_by) values (%s,%s,%s,%s,'USD',%s,%s,%s,%s)"
    )
    for source in (str(uuid7()), str(document)):
        orphan = (tenant, uuid7(), stock.book, DAY, "stock", source, None, user)
        assert await refused(journal, *orphan) == "23514", source
    mirror = uuid7()
    reversal = (tenant, mirror, stock.book, DAY, "reversal", str(mirror), entry, user)
    assert await refused(journal, *reversal) == "23514"
    reversed_by_api = await stock.inventory.client.post(
        f"{stock.ledger}/entries/{entry}/reverse",
        json={"schema_version": 1, "reversal_entry_id": str(uuid7()), "entry_date": DAY},
        headers=stock.keyed(),
    )
    assert error(reversed_by_api) == (409, "LEDGER_STATE_INVALID"), reversed_by_api.text

    # Nothing recorded is rewritten or removed, by the runtime role or by the schema owner.
    for table in DOCUMENT_TABLES:
        assert await refused(f"delete from gba.{table} where tenant_id=%s", tenant) == "42501"
        rewrite = f"update gba.{table} set tenant_id=tenant_id where tenant_id=%s"
        assert await refused(rewrite, tenant) == "42501"
        with (
            pytest.raises(psycopg.errors.CheckViolation),
            owner_tenant_transaction(stock.inventory.owner_conn, tenant),
        ):
            stock.inventory.owner_conn.execute(f"delete from gba.{table}".encode())

    # The inventory account is fixed once a document is posted; the other accounts change.
    moved_account = await stock.set_rules(1, inventory="1500")
    assert error(moved_account) == (422, "INVALID_REFERENCE"), moved_account.text
    kept = await stock.set_rules(1, surplus="4000")
    assert (kept.status_code, kept.json()["revision"]) == (200, 2), kept.text
    # The posted document keeps the rules it was posted with.
    again = await stock.inventory.get(f"/documents/{document}")
    assert again.json()["money"]["rule_revision"] == 1
    assert stock.counts()["stock_documents"] == 1
    assert stock.reconciled() == (1000, 1000)


async def test_disabled_inventory_keeps_stock_reads_and_refuses_documents(stock: Stock) -> None:
    assert (await stock.set_rules()).status_code == 200
    item = await stock.inventory.item(quantity_scale=0)
    line: dict[str, object] = {"item_id": item["item_id"], "quantity": "2", "amount": "4.00"}
    posted = await stock.post(stock.receipt([line]))
    assert posted.status_code == 200, posted.text
    await Config(stock.inventory.client, stock.inventory.idp).publish(
        stock.inventory.manager, stock.tenant, 1, ["booking_resources", "finance"]
    )
    for path in (
        "/documents",
        f"/documents/{posted.json()['document_id']}",
        "/balances",
        "/costs",
        f"/posting-rules/{stock.book}",
    ):
        assert (await stock.inventory.get(path)).status_code == 200, path
    assert error(await stock.post(stock.receipt([line]))) == (409, "MODULE_DISABLED")
    rules = await stock.set_rules(1, surplus="4000")
    assert error(rules) == (409, "MODULE_DISABLED"), rules.text
    assert stock.counts()["stock_documents"] == 1
