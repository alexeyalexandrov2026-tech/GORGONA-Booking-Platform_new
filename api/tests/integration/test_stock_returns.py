"""J4 returns against a line of an earlier receipt or write-off, on real PostgreSQL 18."""

from datetime import UTC, datetime, timedelta
from typing import TypedDict, Unpack
from uuid import UUID, uuid7

import psycopg
import pytest

from gorgona_booking.auth.principal import set_user_context
from gorgona_booking.db.pool import RuntimeConnection, RuntimePool, tenant_transaction
from tests.integration import test_stock as shared
from tests.integration.configuration_support import Config
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.test_counterparties import card
from tests.integration.test_inventory import error, material_input, refused_sql
from tests.integration.test_stock import DAY, Stock, entity_with_book
from tests.integration.test_stock_transfers import transfer
from tests.integration.test_stock_write_offs import behind_the_ledger_lock, write_off

pytestmark = pytest.mark.anyio
stock = shared.stock
inventory = shared.inventory
accepted = shared.accepted
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
type Body = dict[str, object]
# Journal lines as account code, side and minor amount.
type Lines = list[tuple[str, str, int]]
HEAD = (
    "insert into gba.stock_documents (tenant_id,id,kind,reason,legal_entity_id,place_id,"
    "location_id,source_document_id,document_date,line_count,created_by) "
    "values (%s,%s,%s,%s,%s,%s,%s,%s,%s,1,%s)"
)
LINE = (
    "insert into gba.stock_document_lines (tenant_id,document_id,line_no,location_id,item_id,"
    "quantity,source_document_id,source_line_no) values (%s,%s,1,%s,%s,%s,%s,%s)"
)


class Returned(TypedDict, total=False):
    """How a return written by SQL differs from two of five units worth 10.00 going back
    to the supplier: 4.00 leave the inventory account and 4.00 of the receipt line.
    """

    quantity: int
    # What leaves or enters the inventory account, and the share of the source line.
    amount: int
    basis: int
    way: str
    reason: str
    source_line: int
    journal: Lines


def giving_back(stock: Stock, source: object, lines: list[Body], **changes: object) -> Body:
    """A return to the supplier against a receipt, unless a test says otherwise."""
    return {
        "kind": "return",
        "reason": "supplier_return",
        "legal_entity_id": str(stock.entity),
        "place_id": stock.place["place_id"],
        "document_date": DAY,
        "source_document_id": str(source),
        "lines": lines,
        **changes,
    }


def back(line: int, quantity: str) -> Body:
    return {"source_line_no": line, "quantity": quantity}


async def posted(stock: Stock, body: Body) -> UUID:
    document = uuid7()
    response = await stock.post(body, document)
    assert response.status_code == 200, response.text
    return document


async def receipt_of(stock: Stock, item: object, quantity: str, amount: str) -> UUID:
    line: Body = {"item_id": item, "quantity": quantity, "amount": amount}
    return await posted(stock, stock.receipt([line]))


def entry_lines(stock: Stock, document: object) -> Lines:
    codes = {str(account): code for code, account in stock.accounts.items()}
    rows = stock.rows(
        "select l.account_id::text,l.side,l.amount_minor from gba.journal_lines l "
        "join gba.journal_entries e on e.tenant_id=l.tenant_id and e.id=l.entry_id "
        "where e.source_kind='stock' and e.source_id=%s order by l.line_no",
        str(document),
    )
    return [(codes[str(account)], str(side), int(str(amount))) for account, side, amount in rows]


def cost(stock: Stock, item: object) -> tuple[object, ...]:
    return stock.rows("select quantity,value_minor from gba.stock_costs where item_id=%s", item)[0]


async def return_sql(
    conn: RuntimeConnection, stock: Stock, source: object, item: object, **how: Unpack[Returned]
) -> UUID:
    """One return line written by SQL alone, in the order the service writes it."""
    tenant, user = stock.tenant, stock.inventory.manager.user_id
    quantity, amount = how.get("quantity", 2), how.get("amount", 400)
    basis, way = how.get("basis", 400), how.get("way", "out")
    journal = how.get("journal", [("1400", "debit", 400), ("1300", "credit", 400)])
    document = uuid7()
    entry = uuid7() if journal else None
    place, home = stock.place["place_id"], stock.place["location_id"]
    reason = how.get("reason", "supplier_return")
    await conn.execute(
        HEAD, (tenant, document, "return", reason, stock.entity, place, home, source, DAY, user)
    )
    await conn.execute(
        LINE, (tenant, document, home, item, quantity, source, how.get("source_line", 1))
    )
    await conn.execute(
        "insert into gba.stock_document_postings (tenant_id,document_id,book_id,"
        "rule_revision,entry_id,total_minor,created_by) values (%s,%s,%s,1,%s,%s,%s)",
        (tenant, document, stock.book, entry, amount, user),
    )
    await conn.execute(
        "insert into gba.stock_valuations (tenant_id,document_id,line_no,direction,"
        "legal_entity_id,item_id,quantity,amount_minor,basis_minor) "
        "values (%s,%s,1,%s,%s,%s,%s,%s,%s)",
        (tenant, document, way, stock.entity, item, quantity, amount, basis),
    )
    await conn.execute(
        "insert into gba.stock_movements (tenant_id,document_id,line_no,direction,"
        "location_id,place_id,item_id,legal_entity_id,quantity) "
        "values (%s,%s,1,%s,%s,%s,%s,%s,%s)",
        (tenant, document, way, home, place, item, stock.entity, quantity),
    )
    if entry is not None:
        await conn.execute(
            "insert into gba.journal_entries (tenant_id,id,book_id,entry_date,currency,"
            "source_kind,source_id,created_by) values (%s,%s,%s,%s,'USD','stock',%s,%s)",
            (tenant, entry, stock.book, DAY, str(document), user),
        )
        for number, (code, side, minor) in enumerate(journal, start=1):
            await conn.execute(
                "insert into gba.journal_lines (tenant_id,entry_id,line_no,book_id,account_id,"
                "side,amount_minor) values (%s,%s,%s,%s,%s,%s,%s)",
                (tenant, entry, number, stock.book, stock.accounts[code], side, minor),
            )
    return document


async def hand_return(
    stock: Stock,
    source: object,
    item: object,
    pool: RuntimePool | None = None,
    **how: Unpack[Returned],
) -> UUID:
    async with tenant_transaction(pool or stock.pool, stock.tenant) as conn:
        await set_user_context(conn, stock.inventory.manager.user_id)
        return await return_sql(conn, stock, source, item, **how)


async def test_return_to_supplier_leaves_at_average_cost_and_posts_the_price_difference(
    stock: Stock,
) -> None:
    assert (await stock.set_rules(difference="6400")).status_code == 200
    item = (await stock.inventory.item(quantity_scale=0))["item_id"]
    cheap = await receipt_of(stock, item, "10", "100.00")
    dear = await receipt_of(stock, item, "10", "200.00")
    # Twenty units are worth 300.00. Four go back against the dear receipt: 60.00 leave
    # inventory at the average and 80.00 of the receipt line; 20.00 is the difference.
    document = uuid7()
    first = await stock.post(giving_back(stock, dear, [back(1, "4")]), document)
    assert first.status_code == 200, first.text
    view = first.json()
    entry = view["money"]["entry_id"]
    assert entry is not None
    assert {name: value for name, value in view.items() if name != "created_at"} == {
        "schema_version": 1,
        "business_id": str(stock.tenant),
        "document_id": str(document),
        "kind": "return",
        "reason": "supplier_return",
        "legal_entity_id": str(stock.entity),
        "place_id": stock.place["place_id"],
        "location_id": stock.place["location_id"],
        "to_place_id": None,
        "to_location_id": None,
        "source_document_id": str(dear),
        "document_date": DAY,
        "supplier_id": None,
        "supplier_document": None,
        "lines": [
            {
                "line_no": 1,
                "item_id": item,
                "quantity": "4",
                "amount": "60.00",
                "source_line_no": 1,
                "source_amount": "80.00",
            }
        ],
        "money": {
            "book_id": str(stock.book),
            "rule_revision": 1,
            "currency": "USD",
            "total": "60.00",
            "entry_id": entry,
        },
    }
    assert (await stock.inventory.get(f"/documents/{document}")).json() == view
    listed = (await stock.inventory.get("/documents")).json()["items"]
    assert [(row["kind"], row["source_document_id"]) for row in listed] == [
        ("receipt", None),
        ("receipt", None),
        ("return", str(dear)),
    ]
    assert entry_lines(stock, document) == [
        ("1400", "debit", 8000),
        ("6400", "credit", 2000),
        ("1300", "credit", 6000),
    ]
    movement = stock.rows(
        "select direction,quantity from gba.stock_movements where document_id=%s", document
    )
    assert movement == [("out", 4)]
    assert cost(stock, item) == (16, 24000)
    audit = stock.rows(
        "select action,target_type,details from gba.audit_events where target_id=%s",
        str(document),
    )
    assert audit == [("inventory.document", "stock_document", {"kind": "return", "lines": 1})]

    # The return that completes the line takes what is left of its amount: 120.00.
    rest = await posted(stock, giving_back(stock, dear, [back(1, "6")]))
    assert entry_lines(stock, rest) == [
        ("1400", "debit", 12000),
        ("6400", "credit", 3000),
        ("1300", "credit", 9000),
    ]
    assert cost(stock, item) == (10, 15000)
    more = await stock.post(giving_back(stock, dear, [back(1, "1")]))
    assert error(more) == (409, "STOCK_RETURN_EXCEEDED"), more.text
    assert more.json()["error"]["details"] == {"line": 1, "available": "0"}

    # A receipt cheaper than the average: the difference is debited instead.
    low = await posted(stock, giving_back(stock, cheap, [back(1, "2")], reason="entry_error"))
    assert entry_lines(stock, low) == [
        ("1400", "debit", 2000),
        ("6400", "debit", 1000),
        ("1300", "credit", 3000),
    ]
    assert cost(stock, item) == (8, 12000)
    assert stock.rows("select quantity from gba.stock_balances") == [(8,)]
    assert stock.counts() == {
        "stock_documents": 5,
        "stock_document_lines": 5,
        "stock_movements": 5,
        "stock_balances": 1,
        "stock_document_postings": 5,
        "stock_valuations": 5,
        "stock_costs": 1,
        "stock_entries": 5,
    }
    assert stock.reconciled() == (12000, 12000)


async def test_return_of_a_write_off_comes_back_at_its_share_of_the_cost(stock: Stock) -> None:
    assert (await stock.set_rules()).status_code == 200
    item = (await stock.inventory.item(quantity_scale=0))["item_id"]
    await receipt_of(stock, item, "10", "100.01")
    # Three of ten units worth 100.01 were used: 30.00 left inventory.
    used = await posted(stock, write_off(stock, [{"item_id": item, "quantity": "3"}]))
    assert cost(stock, item) == (7, 7001)
    document = uuid7()
    unused = await stock.post(giving_back(stock, used, [back(1, "1")], reason="unused"), document)
    assert unused.status_code == 200, unused.text
    view = unused.json()
    assert (view["kind"], view["reason"], view["source_document_id"]) == (
        "return",
        "unused",
        str(used),
    )
    assert view["lines"] == [
        {
            "line_no": 1,
            "item_id": item,
            "quantity": "1",
            "amount": "10.00",
            "source_line_no": 1,
            "source_amount": "10.00",
        }
    ]
    assert view["money"]["total"] == "10.00"
    # It comes back into inventory from the account the write-off debited.
    assert entry_lines(stock, document) == [("1300", "debit", 1000), ("5000", "credit", 1000)]
    movement = stock.rows(
        "select direction,quantity from gba.stock_movements where document_id=%s", document
    )
    assert movement == [("in", 1)]
    assert cost(stock, item) == (8, 8001)

    # The rest of the line comes back as an entry error: the owner holds what it held.
    rest = await posted(stock, giving_back(stock, used, [back(1, "2")], reason="entry_error"))
    assert entry_lines(stock, rest) == [("1300", "debit", 2000), ("5000", "credit", 2000)]
    assert cost(stock, item) == (10, 10001)
    more = await stock.post(giving_back(stock, used, [back(1, "1")], reason="unused"))
    assert error(more) == (409, "STOCK_RETURN_EXCEEDED"), more.text

    # What was written off as damaged comes back from the account of losses.
    damaged = await posted(
        stock, write_off(stock, [{"item_id": item, "quantity": "4"}], reason="damaged")
    )
    assert cost(stock, item) == (6, 6001)
    found = await posted(stock, giving_back(stock, damaged, [back(1, "4")], reason="entry_error"))
    assert entry_lines(stock, found) == [("1300", "debit", 4000), ("6900", "credit", 4000)]
    assert cost(stock, item) == (10, 10001)
    assert stock.rows("select quantity from gba.stock_balances") == [(10,)]
    assert stock.reconciled() == (10001, 10001)


async def test_shares_are_rounded_once_and_a_completed_line_returns_its_whole_amount(
    stock: Stock,
) -> None:
    assert (await stock.set_rules()).status_code == 200
    item = (await stock.inventory.item(quantity_scale=0))["item_id"]
    source = await receipt_of(stock, item, "3", "1.00")
    # 1.00 over three units: 0.33, then half of the 0.67 that is left, half up, then the rest.
    shares = []
    for expected in (33, 34, 33):
        one = await posted(stock, giving_back(stock, source, [back(1, "1")]))
        assert entry_lines(stock, one) == [
            ("1400", "debit", expected),
            ("1300", "credit", expected),
        ]
        shares.append(expected)
    assert sum(shares) == 100
    assert cost(stock, item) == (0, 0)
    assert stock.reconciled() == (0, 0)

    # A material received for nothing goes back for nothing and posts no entry.
    free = (await stock.inventory.item(quantity_scale=0))["item_id"]
    gift = await receipt_of(stock, free, "2", "0.00")
    entries = stock.counts()["stock_entries"]
    document = uuid7()
    nothing = await stock.post(giving_back(stock, gift, [back(1, "1")]), document)
    assert nothing.status_code == 200, nothing.text
    assert nothing.json()["money"] == {
        "book_id": str(stock.book),
        "rule_revision": 1,
        "currency": "USD",
        "total": "0.00",
        "entry_id": None,
    }
    line = nothing.json()["lines"][0]
    assert (line["amount"], line["source_amount"]) == ("0.00", "0.00")
    assert entry_lines(stock, document) == []
    assert stock.counts()["stock_entries"] == entries

    # The share of the line can be above zero while the average cost rounds to zero: the
    # entry then moves the receipt account and the difference only.
    mixed = (await stock.inventory.item(quantity_scale=0))["item_id"]
    await receipt_of(stock, mixed, "5", "0.00")
    cent = await receipt_of(stock, mixed, "5", "0.01")
    document = uuid7()
    odd = await stock.post(giving_back(stock, cent, [back(1, "3")]), document)
    assert odd.status_code == 200, odd.text
    assert odd.json()["money"]["total"] == "0.00"
    assert odd.json()["money"]["entry_id"] is not None
    assert entry_lines(stock, document) == [("1400", "debit", 1), ("6900", "credit", 1)]
    assert cost(stock, mixed) == (7, 1)
    assert stock.reconciled() == (1, 1)


async def test_return_keeps_its_limits_and_its_shape(stock: Stock) -> None:
    assert (await stock.set_rules()).status_code == 200
    await Config(stock.inventory.client, stock.inventory.idp).publish(
        stock.inventory.manager,
        stock.tenant,
        1,
        ["booking_resources", "counterparties", "finance", "inventory"],
    )
    supplier = uuid7()
    saved = await stock.inventory.client.put(
        f"/v1/businesses/{stock.tenant}/counterparties/{supplier}",
        json=card(
            roles=["supplier"],
            display_name="FAKE supplier",
            email="fake.supplier@example.test",
            phone="+1 555 010 2001",
        ),
        headers=stock.keyed(),
    )
    assert saved.status_code == 200, saved.text
    shelf = await stock.inventory.place(stock.inventory.world.a.location_id)
    item = (await stock.inventory.item(quantity_scale=0))["item_id"]
    other_item = (await stock.inventory.item(quantity_scale=0))["item_id"]
    source = await posted(
        stock,
        stock.receipt(
            [
                {"item_id": item, "quantity": "5", "amount": "10.00"},
                {"item_id": other_item, "quantity": "2", "amount": "2.00"},
            ]
        ),
    )
    used = await posted(stock, write_off(stock, [{"item_id": item, "quantity": "2"}]))
    moved = await posted(stock, transfer(stock, shelf, [{"item_id": other_item, "quantity": "1"}]))
    # One unit goes back with the supplier and the number of the supplier's document.
    given = uuid7()
    good = await stock.post(
        giving_back(
            stock,
            source,
            [back(1, "1")],
            supplier_id=str(supplier),
            supplier_document=" CN-1 ",
        ),
        given,
    )
    assert good.status_code == 200, good.text
    assert (good.json()["supplier_id"], good.json()["supplier_document"]) == (
        str(supplier),
        "CN-1",
    )
    other, _, _ = await entity_with_book(stock.inventory, stock.pool, "OTHER", book=False)
    baseline = stock.counts()

    unknown = await stock.post(giving_back(stock, uuid7(), [back(1, "1")]))
    assert error(unknown) == (422, "INVALID_REFERENCE"), unknown.text
    # A return names a receipt or a write-off of the same owner, a reason of that kind
    # and lines of that document.
    for body in (
        giving_back(stock, moved, [back(1, "1")]),
        giving_back(stock, given, [back(1, "1")]),
        giving_back(stock, source, [back(1, "1")], legal_entity_id=str(other)),
        giving_back(stock, source, [back(1, "1")], reason="unused"),
        giving_back(stock, used, [back(1, "1")]),
        giving_back(stock, source, [back(3, "1")]),
    ):
        wrong = await stock.post(body)
        assert error(wrong) == (422, "STOCK_RETURN_INVALID"), wrong.text
    for body in (
        giving_back(stock, source, [back(1, "1"), back(1, "1")]),
        giving_back(stock, source, [{**back(1, "1"), "amount": "2.00"}]),
        giving_back(stock, source, [{**back(1, "1"), "item_id": item}]),
        giving_back(stock, source, [back(0, "1")]),
        giving_back(stock, source, [back(1, "1")], reason="purchase"),
        giving_back(stock, source, [back(1, "1")], reason="entry_error", supplier_document="X"),
        giving_back(stock, source, [back(1, "1")], to_place_id=shelf["place_id"]),
        giving_back(stock, source, []),
        giving_back(stock, source, [back(1, "1")] * 101),
        {
            name: value
            for name, value in giving_back(stock, source, [back(1, "1")]).items()
            if name != "source_document_id"
        },
    ):
        assert error(await stock.post(body)) == (422, "INVALID_REQUEST")
    for quantity in ("0", "1.5"):
        odd = await stock.post(giving_back(stock, source, [back(1, quantity)]))
        assert error(odd) == (422, "STOCK_QUANTITY_INVALID"), odd.text
    stranger = await stock.post(
        giving_back(stock, source, [back(1, "1")], supplier_id=str(uuid7()))
    )
    assert error(stranger) == (422, "INVALID_REFERENCE"), stranger.text
    # No more than is left of the line: one of five went back already.
    for lines, number in (([back(1, "5")], 1), ([back(2, "1"), back(1, "5")], 2)):
        over = await stock.post(giving_back(stock, source, lines))
        assert error(over) == (409, "STOCK_RETURN_EXCEEDED"), over.text
        assert over.json()["error"]["details"] == {"line": number, "available": "4"}
    # And no more than the place holds: two were used, so two of the four are there.
    short = await stock.post(giving_back(stock, source, [back(1, "3")]))
    assert error(short) == (409, "STOCK_INSUFFICIENT"), short.text
    assert short.json()["error"]["details"] == {"line": 1, "available": "2"}
    future = (datetime.now(UTC).date() + timedelta(days=2)).isoformat()
    for day in (future, "2025-12-31"):
        dated = await stock.post(giving_back(stock, source, [back(1, "1")], document_date=day))
        assert error(dated) == (422, "STOCK_DATE_INVALID"), dated.text
    closed = await stock.inventory.client.post(
        f"{stock.ledger}/periods/2026-09/close",
        json={"schema_version": 1, "expected_sequence": 0},
        headers=stock.keyed(),
    )
    assert closed.status_code == 200, closed.text
    late = await stock.post(giving_back(stock, source, [back(1, "1")], document_date="2026-09-20"))
    assert error(late) == (409, "LEDGER_PERIOD_CLOSED"), late.text
    assert stock.counts() == baseline

    # The command is idempotent like every other document.
    document, key = uuid7(), str(uuid7())
    body = giving_back(stock, source, [back(1, "2"), back(2, "1")])
    first = await stock.post(body, document, key)
    assert first.status_code == 200, first.text
    assert [line["quantity"] for line in first.json()["lines"]] == ["2", "1"]
    assert (await stock.post(body, document, key)).json() == first.json()
    reused = await stock.post(giving_back(stock, source, [back(1, "1")]), document, key)
    assert error(reused) == (422, "IDEMPOTENCY_KEY_REUSED"), reused.text
    again = await stock.post(body, document)
    assert error(again) == (409, "INVENTORY_CONFLICT"), again.text
    assert stock.counts()["stock_documents"] == baseline["stock_documents"] + 1
    value, entries = stock.reconciled()
    assert value == entries


async def test_return_follows_the_material_and_respects_the_archive(stock: Stock) -> None:
    assert (await stock.set_rules()).status_code == 200
    home = stock.inventory.world.a.location_id
    shelf = await stock.inventory.place(home)
    item = (await stock.inventory.item(quantity_scale=0))["item_id"]
    source = await receipt_of(stock, item, "5", "10.00")
    await posted(stock, transfer(stock, shelf, [{"item_id": item, "quantity": "3"}]))
    # The material goes back to the supplier from the place it is in now.
    away = await stock.post(giving_back(stock, source, [back(1, "3")], place_id=shelf["place_id"]))
    assert (away.status_code, away.json()["place_id"]) == (200, shelf["place_id"]), away.text
    held = stock.rows("select place_id::text,quantity from gba.stock_balances")
    assert set(held) == {(stock.place["place_id"], 2), (shelf["place_id"], 0)}

    # An archived material and an archived place take nothing in and still let it leave.
    old = await stock.inventory.item(quantity_scale=0)
    sealed = await stock.inventory.place(home)
    bought = await posted(
        stock,
        stock.receipt(
            [{"item_id": old["item_id"], "quantity": "4", "amount": "8.00"}],
            place_id=sealed["place_id"],
        ),
    )
    used = await posted(
        stock,
        write_off(
            stock, [{"item_id": old["item_id"], "quantity": "2"}], place_id=sealed["place_id"]
        ),
    )
    retired = await stock.inventory.put(
        f"/items/{old['item_id']}", {**material_input(old), "archived": True}
    )
    assert retired.status_code == 200, retired.text
    back_in = giving_back(stock, used, [back(1, "1")], reason="unused", place_id=sealed["place_id"])
    assert error(await stock.post(back_in)) == (409, "STOCK_ARCHIVED")
    reopened = await stock.inventory.put(
        f"/items/{old['item_id']}",
        {**material_input(old), "expected_revision": 2, "archived": False},
    )
    assert reopened.status_code == 200, reopened.text
    shut = await stock.inventory.put(
        f"/places/{sealed['place_id']}",
        {
            "expected_revision": 1,
            "location_id": sealed["location_id"],
            "code": sealed["code"],
            "name": sealed["name"],
            "archived": True,
        },
    )
    assert shut.status_code == 200, shut.text
    assert error(await stock.post(back_in)) == (409, "STOCK_ARCHIVED")
    # Into an open place the unused unit comes back; out of the archived one it leaves.
    elsewhere = await stock.post({**back_in, "place_id": stock.place["place_id"]})
    assert elsewhere.status_code == 200, elsewhere.text
    leaving = await stock.post(
        giving_back(stock, bought, [back(1, "2")], place_id=sealed["place_id"])
    )
    assert leaving.status_code == 200, leaving.text
    value, entries = stock.reconciled()
    assert value == entries


async def test_only_a_company_wide_finance_member_posts_a_return(stock: Stock) -> None:
    assert (await stock.set_rules()).status_code == 200
    home = stock.inventory.world.a.location_id
    item = (await stock.inventory.item(quantity_scale=0))["item_id"]
    source = await receipt_of(stock, item, "5", "10.00")
    document = await posted(stock, giving_back(stock, source, [back(1, "1")]))
    local, branch = stock.inventory.member("manager", home)
    body = giving_back(stock, source, [back(1, "1")])
    for headers in (
        branch,
        stock.inventory.member("artist", home)[1],
        stock.inventory.member("front_desk")[1],
    ):
        assert (await stock.post(body, headers=headers)).status_code == 403
    # By SQL alone a branch manager posts no return either, with the branch scope or
    # without it.
    values = (
        stock.tenant,
        uuid7(),
        "return",
        "supplier_return",
        stock.entity,
        stock.place["place_id"],
        home,
        source,
        DAY,
        local.user_id,
    )
    for scope in (home, None):
        assert (
            await refused_sql(stock.pool, stock.tenant, local.user_id, HEAD, values, scope)
            == "42501"
        )
    # The branch manager reads the return of the branch without any amount.
    seen = await stock.inventory.get(f"/documents/{document}", headers=branch)
    assert seen.status_code == 200, seen.text
    assert seen.json()["source_document_id"] == str(source)
    assert seen.json()["lines"] == [
        {
            "line_no": 1,
            "item_id": item,
            "quantity": "1",
            "amount": None,
            "source_line_no": 1,
            "source_amount": None,
        }
    ]
    assert seen.json()["money"] is None

    await Config(stock.inventory.client, stock.inventory.idp).publish(
        stock.inventory.manager, stock.tenant, 1, ["booking_resources", "finance"]
    )
    assert error(await stock.post(body)) == (409, "MODULE_DISABLED")
    with pytest.raises(psycopg.DatabaseError) as gated:
        await hand_return(stock, source, item, quantity=1, amount=200, basis=200)
    assert gated.value.sqlstate == "GBM01"
    assert stock.counts()["stock_documents"] == 2
    assert cost(stock, item) == (4, 800)


async def test_sql_return_carries_exactly_the_amounts_of_the_database(stock: Stock) -> None:
    assert (await stock.set_rules()).status_code == 200
    item = (await stock.inventory.item(quantity_scale=0))["item_id"]
    other_item = (await stock.inventory.item(quantity_scale=0))["item_id"]
    source = await receipt_of(stock, item, "5", "10.00")
    await receipt_of(stock, other_item, "5", "10.00")
    # Written whole by SQL alone a return is accepted: the database holds the rules.
    await hand_return(stock, source, item)
    assert cost(stock, item) == (3, 600)
    counts = stock.counts()
    one: Lines = [("1400", "debit", 200), ("1300", "credit", 200)]
    attempts: tuple[tuple[Returned, str], ...] = (
        # The share of the line and the value at the average, each one off both ways.
        ({"quantity": 1, "amount": 200, "basis": 199, "journal": one}, "23514"),
        ({"quantity": 1, "amount": 200, "basis": 201, "journal": one}, "23514"),
        ({"quantity": 1, "amount": 199, "basis": 200, "journal": one}, "23514"),
        ({"quantity": 1, "amount": 201, "basis": 200, "journal": one}, "23514"),
        # The wrong direction, another account, another amount and no entry at all.
        ({"quantity": 1, "amount": 200, "basis": 200, "journal": one, "way": "in"}, "23514"),
        (
            {
                "quantity": 1,
                "amount": 200,
                "basis": 200,
                "journal": [("1400", "debit", 200), ("6900", "credit", 200)],
            },
            "23514",
        ),
        (
            {
                "quantity": 1,
                "amount": 200,
                "basis": 200,
                "journal": [("1400", "debit", 199), ("1300", "credit", 199)],
            },
            "23514",
        ),
        ({"quantity": 1, "amount": 200, "basis": 200, "journal": []}, "23514"),
        # A reason of a returned write-off, a line the receipt does not have and more
        # than is left of the line.
        (
            {"quantity": 1, "amount": 200, "basis": 200, "journal": one, "reason": "unused"},
            "23514",
        ),
        (
            {"quantity": 1, "amount": 200, "basis": 200, "journal": one, "source_line": 2},
            "23514",
        ),
        ({"quantity": 4, "amount": 600, "basis": 600}, "GBS03"),
    )
    for how, state in attempts:
        with pytest.raises(psycopg.DatabaseError) as caught:
            await hand_return(stock, source, item, **how)
        assert caught.value.sqlstate == state, how
    # A line of another material does not return this one.
    with pytest.raises(psycopg.DatabaseError) as caught:
        await hand_return(stock, source, other_item, quantity=1, amount=200, basis=200, journal=one)
    assert caught.value.sqlstate == "23514"
    # Only a return names a source: a write-off line with one and a write-off document
    # with one are refused.
    user, home = stock.inventory.manager.user_id, stock.place["location_id"]
    place = stock.place["place_id"]

    async def stray_line() -> None:
        async with tenant_transaction(stock.pool, stock.tenant) as conn:
            await set_user_context(conn, user)
            document = uuid7()
            head = (stock.tenant, document, "write_off", "used", stock.entity, place, home)
            await conn.execute(HEAD, (*head, None, DAY, user))
            await conn.execute(LINE, (stock.tenant, document, home, item, 1, source, 1))

    with pytest.raises(psycopg.DatabaseError) as caught:
        await stray_line()
    assert caught.value.sqlstate == "23514"
    for kind, reason, origin in (
        ("write_off", "used", source),
        ("return", "supplier_return", None),
    ):
        values = (stock.tenant, uuid7(), kind, reason, stock.entity, place, home, origin, DAY, user)
        assert await refused_sql(stock.pool, stock.tenant, user, HEAD, values) == "23514", kind
    assert stock.counts() == counts
    assert cost(stock, item) == (3, 600)

    # A returned write-off enters at its share of the cost and at nothing else.
    used = await posted(stock, write_off(stock, [{"item_id": item, "quantity": "2"}]))
    assert cost(stock, item) == (1, 200)
    unused: Lines = [("1300", "debit", 200), ("5000", "credit", 200)]
    with pytest.raises(psycopg.DatabaseError) as caught:
        await hand_return(
            stock,
            used,
            item,
            quantity=1,
            way="in",
            reason="unused",
            amount=150,
            basis=200,
            journal=[("1300", "debit", 150), ("5000", "credit", 150)],
        )
    assert caught.value.sqlstate == "23514"
    await hand_return(
        stock,
        used,
        item,
        quantity=1,
        way="in",
        reason="unused",
        amount=200,
        basis=200,
        journal=unused,
    )
    assert cost(stock, item) == (2, 400)
    assert stock.reconciled() == (1400, 1400)


@pytest.mark.parametrize("raw_sql", [False, True])
async def test_two_returns_of_the_last_quantity_have_one_winner(
    stock: Stock, test_database: ProvisionedDatabase, raw_sql: bool
) -> None:
    assert (await stock.set_rules()).status_code == 200
    item = (await stock.inventory.item(quantity_scale=0))["item_id"]
    source = await receipt_of(stock, item, "5", "10.00")
    body = giving_back(stock, source, [back(1, "5")])
    whole: Lines = [("1400", "debit", 1000), ("1300", "credit", 1000)]

    async def racer() -> str:
        if raw_sql:
            try:
                await hand_return(
                    stock, source, item, quantity=5, amount=1000, basis=1000, journal=whole
                )
            except psycopg.DatabaseError as exc:
                if exc.sqlstate != "GBS03":
                    raise
                return "over"
            return "returned"
        response = await stock.post(body)
        if response.status_code == 200:
            return "returned"
        assert error(response) == (409, "STOCK_RETURN_EXCEEDED"), response.text
        return "over"

    results = await behind_the_ledger_lock(stock, test_database, [racer, racer])
    assert sorted(results) == ["over", "returned"]
    assert cost(stock, item) == (0, 0)
    assert stock.rows("select quantity from gba.stock_balances") == [(0,)]
    assert stock.counts()["stock_documents"] == 2
    assert stock.reconciled() == (0, 0)


async def test_return_uses_the_accounts_of_its_source_and_the_current_difference_account(
    stock: Stock,
) -> None:
    assert (await stock.set_rules(difference="6400")).status_code == 200
    item = (await stock.inventory.item(quantity_scale=0))["item_id"]
    await receipt_of(stock, item, "10", "100.00")
    dear = await receipt_of(stock, item, "10", "200.00")
    # The rules change after the receipt: another account for receipts and for differences.
    assert (await stock.set_rules(1, receipt="1500", difference="6300")).status_code == 200
    document = uuid7()
    first = await stock.post(giving_back(stock, dear, [back(1, "4")]), document)
    assert first.status_code == 200, first.text
    assert first.json()["money"]["rule_revision"] == 2
    # The account the receipt credited is debited; the difference goes where the current
    # rules say.
    assert entry_lines(stock, document) == [
        ("1400", "debit", 8000),
        ("6300", "credit", 2000),
        ("1300", "credit", 6000),
    ]
    # When both are one account, the entry carries one line for it: 40.00 of the receipt
    # line less a difference of 10.00.
    assert (await stock.set_rules(2, receipt="1500", difference="1400")).status_code == 200
    netted = await posted(stock, giving_back(stock, dear, [back(1, "2")]))
    assert entry_lines(stock, netted) == [("1400", "debit", 3000), ("1300", "credit", 3000)]
    assert cost(stock, item) == (14, 21000)
    assert stock.reconciled() == (21000, 21000)
    # A receipt of an opening balance or of a surplus is returned against its own account.
    for reason, code in (("opening_balance", "3900"), ("surplus", "4900")):
        other = (await stock.inventory.item(quantity_scale=0))["item_id"]
        entered = await posted(
            stock,
            stock.receipt([{"item_id": other, "quantity": "2", "amount": "5.00"}], reason=reason),
        )
        undone = await posted(
            stock, giving_back(stock, entered, [back(1, "1")], reason="entry_error")
        )
        assert entry_lines(stock, undone) == [(code, "debit", 250), ("1300", "credit", 250)]
    assert stock.reconciled() == (21500, 21500)
