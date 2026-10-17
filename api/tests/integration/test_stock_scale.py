"""M2 of the independent review: what a long history costs a posting.

Each check of a balance once summed every movement of its material in its place, each check
of a cost every valuation of the material of its owner, and the guard of a stock journal
entry read every stock document of the company. The history is seeded as the database
superuser with triggers off, in pairs that leave the balance and the cost unchanged: a
receipt of one unit at zero value and a write-off of that unit, each with its line,
movement, zero posting and valuation, continuing the running totals from the head of each
history. The timed documents go through the API with every trigger and check on; the
history is the hundred thousand movements that the review asked to measure.
"""

import json
import os
import statistics
import time
from collections.abc import Iterator
from typing import Any
from uuid import UUID

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from tests.integration import test_stock as shared
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.test_stock import DAY, Stock
from tests.integration.test_stock_write_offs import write_off

pytestmark = pytest.mark.anyio
stock = shared.stock
inventory = shared.inventory
accepted = shared.accepted
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
TIMED = 15
MAX_MOVEMENT_ROWS = 100
ANALYZED = (
    "stock_documents",
    "stock_document_lines",
    "stock_movements",
    "stock_document_postings",
    "stock_valuations",
    "stock_balances",
    "stock_costs",
)

SEED = """
create temp table seed on commit drop as
  select n, gen_random_uuid() as received, gen_random_uuid() as written
    from generate_series(1, %(pairs)s) n;
insert into gba.stock_documents (tenant_id,id,kind,reason,legal_entity_id,place_id,location_id,
    document_date,line_count,created_by)
  select %(tenant)s, d.id, d.kind, d.reason, %(entity)s, %(place)s, %(location)s,
         %(day)s, 1, %(user)s
    from seed s cross join lateral (values (s.received,'receipt','purchase'),
                                           (s.written,'write_off','used')) d(id,kind,reason);
insert into gba.stock_document_lines (tenant_id,document_id,line_no,location_id,item_id,quantity)
  select %(tenant)s, d.id, 1, %(location)s, %(item)s, 1
    from seed s cross join lateral (values (s.received),(s.written)) d(id);
insert into gba.stock_movements (tenant_id,document_id,line_no,direction,location_id,place_id,
    item_id,legal_entity_id,quantity,sequence,balance_after)
  select %(tenant)s, d.id, 1, d.direction, %(location)s, %(place)s, %(item)s, %(entity)s, 1,
         d.sequence, d.after
    from seed s cross join lateral (values
         (s.received,'in',%(moved)s+2*s.n-1,%(held)s+1),
         (s.written,'out',%(moved)s+2*s.n,%(held)s)) d(id,direction,sequence,after);
insert into gba.stock_document_postings (tenant_id,document_id,book_id,rule_revision,entry_id,
    total_minor,created_by)
  select %(tenant)s, d.id, %(book)s, 1, null, 0, %(user)s
    from seed s cross join lateral (values (s.received),(s.written)) d(id);
insert into gba.stock_valuations (tenant_id,document_id,line_no,direction,legal_entity_id,
    item_id,quantity,amount_minor,sequence,quantity_after,value_after)
  select %(tenant)s, d.id, 1, d.direction, %(entity)s, %(item)s, 1, 0, d.sequence, d.stocked,
         %(worth)s
    from seed s cross join lateral (values
         (s.received,'in',%(valued)s+2*s.n-1,%(stocked)s+1),
         (s.written,'out',%(valued)s+2*s.n,%(stocked)s)) d(id,direction,sequence,stocked);
"""


async def timed(stock: Stock, item: object) -> list[float]:
    """Alternate one-line receipts and write-offs of one unit; each posting's seconds."""
    seconds = []
    for n in range(TIMED):
        line: dict[str, object] = {"item_id": item, "quantity": "1"}
        body = (
            stock.receipt([{**line, "amount": "2.50"}]) if n % 2 == 0 else write_off(stock, [line])
        )
        began = time.perf_counter()
        posted = await stock.post(body)
        seconds.append(time.perf_counter() - began)
        assert posted.status_code == 200, posted.text
    return seconds


def summary(name: str, seconds: list[float]) -> str:
    ms = sorted(round(s * 1000, 1) for s in seconds)
    return (
        f"{name}: median {statistics.median(ms)} ms, min {ms[0]} ms, max {ms[-1]} ms, n={len(ms)}"
    )


async def measure(
    stock: Stock, test_database: ProvisionedDatabase, pairs: int
) -> tuple[list[float], list[float], str, tuple[int, str]]:
    """Postings timed on an empty history, then after `pairs` seeded pairs."""
    assert (await stock.set_rules()).status_code == 200
    item = (await stock.inventory.item(quantity_scale=0))["item_id"]
    line: dict[str, object] = {"item_id": item, "quantity": "100", "amount": "250.00"}
    assert (await stock.post(stock.receipt([line]))).status_code == 200
    admin = make_conninfo(test_database.admin_dsn, dbname=test_database.name)
    # Statistics of a short history, never refreshed after the seed: the state a database
    # reaches when autovacuum analyzed the tables before a burst of postings (K1h).
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f"analyze {','.join('gba.' + table for table in ANALYZED)}".encode())
    before = await timed(stock, item)

    values = {
        "pairs": pairs,
        "tenant": stock.tenant,
        "entity": stock.entity,
        "place": UUID(str(stock.place["place_id"])),
        "location": UUID(str(stock.place["location_id"])),
        "item": UUID(str(item)),
        "book": stock.book,
        "user": stock.inventory.manager.user_id,
        "day": DAY,
    }
    # Where the histories stand: the seed continues them.
    head = stock.rows(
        "select (select m.sequence from gba.stock_movements m where m.item_id=%s "
        "and m.place_id=%s order by m.sequence desc limit 1),"
        "(select b.quantity from gba.stock_balances b where b.item_id=%s and b.place_id=%s),"
        "(select v.sequence from gba.stock_valuations v where v.item_id=%s "
        "order by v.sequence desc limit 1),"
        "(select c.quantity from gba.stock_costs c where c.item_id=%s),"
        "(select c.value_minor from gba.stock_costs c where c.item_id=%s)",
        item,
        stock.place["place_id"],
        item,
        stock.place["place_id"],
        item,
        item,
        item,
    )[0]
    values |= dict(zip(("moved", "held", "valued", "stocked", "worth"), head, strict=True))
    began = time.perf_counter()
    with psycopg.connect(admin) as conn, conn.transaction():
        # Triggers (and with them foreign keys) are off for this seed only.
        conn.execute("set local session_replication_role = replica")
        for statement in SEED.split(";\n"):
            if statement.strip():
                conn.execute(statement.encode("utf-8"), values)
    seeded = time.perf_counter() - began
    history = stock.rows(
        "select (select count(*) from gba.stock_movements where item_id=%s),"
        "(select count(*) from gba.stock_valuations where item_id=%s)",
        item,
        item,
    )
    # No statistics are refreshed after the seed, as right after a burst of postings: a
    # check must find its rows by an index whatever the planner believes about the tables.
    # The statistics analyzed above describe a short history and now underestimate it.
    after = await timed(stock, item)
    # Every later document still meets consistent totals.
    value, booked = stock.reconciled()
    assert value == booked
    touched = movement_rows_checked(stock, test_database, item)
    report = "\n".join(
        (
            f"M2 history: {history[0][0]} movements and {history[0][1]} valuations of one "
            f"material, place and owner (seeded in {seeded:.1f} s)",
            summary("before", before),
            summary("after", after),
            f"assert_stock_document: at most {touched[0]} stock rows per plan node ({touched[1]})",
        )
    )
    return before, after, report, touched


def _nodes(plan: dict[str, Any]) -> Iterator[dict[str, Any]]:
    yield plan
    for child in plan.get("Plans", []):
        yield from _nodes(child)


def movement_rows_checked(
    stock: Stock, test_database: ProvisionedDatabase, item: object
) -> tuple[int, str]:
    """Re-run the document check of the last posting under auto_explain as the runtime role.

    Returns the most rows of a stock table that one plan node returned or filtered out, which
    does not depend on machine load.
    """
    document = stock.rows(
        "select m.document_id from gba.stock_movements m where m.item_id=%s and m.place_id=%s "
        "order by m.sequence desc limit 1",
        item,
        stock.place["place_id"],
    )[0][0]
    runtime = str(conninfo_to_dict(test_database.app_dsn)["user"])
    plans: list[tuple[dict[str, Any], str]] = []

    def collect(notice: psycopg.errors.Diagnostic) -> None:
        message = notice.message_primary or ""
        if "plan:" in message:
            explained = json.loads(message[message.index("{") :])
            plans.append((explained["Plan"], " ".join(explained.get("Query Text", "").split())))

    admin = make_conninfo(test_database.admin_dsn, dbname=test_database.name)
    with psycopg.connect(admin) as conn:
        conn.add_notice_handler(collect)
        conn.execute("load 'auto_explain'")
        with conn.transaction():
            for setting in (
                "set local auto_explain.log_min_duration = 0",
                "set local auto_explain.log_nested_statements = on",
                "set local auto_explain.log_analyze = on",
                "set local auto_explain.log_format = json",
                "set local client_min_messages = log",
            ):
                conn.execute(setting.encode())
            conn.execute(
                "select pg_catalog.set_config('gba.tenant_id', %s, true)", (str(stock.tenant),)
            )
            conn.execute(sql.SQL("set local role {}").format(sql.Identifier(runtime)))
            conn.execute("select gba.assert_stock_document(%s, %s)", (stock.tenant, document))
    rows = [
        (
            int(
                (node.get("Actual Rows", 0) + node.get("Rows Removed by Filter", 0))
                * node.get("Actual Loops", 1)
            ),
            f"{node.get('Node Type')} {node.get('Index Name', '')} in: {query[:120]}",
        )
        for plan, query in plans
        for node in _nodes(plan)
        if str(node.get("Relation Name", "")).startswith("stock_")
    ]
    assert rows, "auto_explain reported no stock table access"
    return max(rows)


async def test_posting_time_does_not_grow_with_a_long_history(
    stock: Stock, test_database: ProvisionedDatabase
) -> None:
    """A hundred thousand movements, valuations and documents leave a posting nearly as fast.

    Before migration 0042 every check summed the whole history and the guard of a stock
    journal entry read every stock document of the company.
    """
    pairs = int(os.environ.get("GBA_MEASURE_STOCK_PAIRS", "50000"))
    before, after, report, touched = await measure(stock, test_database, pairs)
    print(report)  # noqa: T201 - the timings are the evidence of this test
    # Load-independent: the check of one document reads that document, not the history (K1h).
    assert touched[0] <= MAX_MOVEMENT_ROWS, report
    assert statistics.median(after) < 3 * statistics.median(before) + 0.05, report
