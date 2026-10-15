"""Rows of the acceptance matrix of package J that earlier slices left untested.

J-12: a delegate of another company reaches no inventory route. J-13: a purchase and the
supplier's bill for the same amount on the same account leave nothing on that account.
Gap 10 of the independent review: accumulated totals stay in range with a named refusal,
a return never moves another owner's stock even by SQL, and archiving a material and a
receipt of it take one order.
"""

import asyncio
from uuid import uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.auth.principal import set_user_context
from gorgona_booking.business import modules
from gorgona_booking.business.readiness_registry import Readiness
from gorgona_booking.db.pool import tenant_transaction
from gorgona_booking.db.provisioning import add_membership
from tests.integration import test_stock as shared
from tests.integration.configuration_support import Config
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.seed import seed_user
from tests.integration.test_counterparties import card
from tests.integration.test_delegations import Parties
from tests.integration.test_inventory import ITEM_VERSION, error, item_body, refused_sql
from tests.integration.test_inventory_commands import reference, settle
from tests.integration.test_stock import DAY, Stock, entity_with_book
from tests.integration.test_stock_transfers import ROW_WAITERS, transfer
from tests.integration.test_stock_write_offs import received, write_off

pytestmark = pytest.mark.anyio
stock = shared.stock
inventory = shared.inventory
accepted = shared.accepted
client = shared.client
idp = shared.idp
manager_a = shared.manager_a


async def test_j13_revoked_readiness_refuses_new_actions_and_keeps_history_and_recovery(
    stock: Stock,
) -> None:
    """Revoke only this fixture's simulated acceptance after a real posting exists."""
    assert (await stock.set_rules()).status_code == 200
    item = (await stock.inventory.item(quantity_scale=0))["item_id"]
    shelf = await stock.inventory.place(stock.inventory.world.a.location_id)
    body = stock.receipt([{"item_id": item, "quantity": "5", "amount": "10.00"}])
    document, key = uuid7(), str(uuid7())
    posted = await stock.post(body, document, key)
    assert posted.status_code == 200, posted.text
    before = stock.counts()
    current = modules.MODULES_BY_ID["inventory"]
    with pytest.MonkeyPatch.context() as patch:
        patch.setitem(
            modules.MODULES_BY_ID,
            "inventory",
            current.model_copy(update={"enableable": False, "readiness": Readiness.IMPLEMENTED}),
        )
        commands = [
            stock.inventory.put(f"/items/{uuid7()}", item_body()),
            stock.inventory.put(
                f"/places/{uuid7()}",
                {
                    "expected_revision": 0,
                    "location_id": shelf["location_id"],
                    "code": "REVOKED",
                    "name": "FAKE revoked place",
                },
            ),
            stock.set_rules(1, surplus="4000"),
            stock.post(body),
            stock.post(write_off(stock, [{"item_id": item, "quantity": "1"}])),
            stock.post(transfer(stock, shelf, [{"item_id": item, "quantity": "1"}])),
            stock.post(
                {
                    "kind": "return",
                    "reason": "supplier_return",
                    "legal_entity_id": str(stock.entity),
                    "place_id": stock.place["place_id"],
                    "document_date": DAY,
                    "source_document_id": str(document),
                    "lines": [{"source_line_no": 1, "quantity": "1"}],
                }
            ),
        ]
        for command in commands:
            response = await command
            assert error(response) == (409, "MODULE_NOT_READY"), response.text
        for path in (
            "/items",
            "/places",
            "/balances",
            "/costs",
            "/documents",
            f"/documents/{document}",
            f"/posting-rules/{stock.book}",
        ):
            assert (await stock.inventory.get(path)).status_code == 200, path
        assert (await stock.inventory.get(f"/documents/{document}")).json() == posted.json()
        recovered = await settle(stock, key, reference("document", document))
        assert recovered.status_code == 200, recovered.text
        assert recovered.json()["state"] == "committed"
        missing = reference("document", uuid7())
        cancelled = await settle(stock, str(uuid7()), missing, "cancel")
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["state"] == "cancelled"
    assert stock.counts() == before
    assert stock.reconciled() == (1000, 1000)


async def test_j12_a_delegate_of_another_company_reaches_no_inventory_route(
    stock: Stock,
) -> None:
    inventory = stock.inventory
    owners = [seed_user(inventory.owner_conn, f"FAKE-j12-owner-{uuid7()}") for _ in range(2)]
    for salon, user in zip((inventory.world.a, inventory.world.b), owners, strict=True):
        add_membership(
            inventory.owner_conn, tenant_id=salon.tenant_id, user_id=user.user_id, role="owner"
        )
    # The other company serves bookings of this one under an active grant.
    parties = Parties(inventory.client, inventory.idp, inventory.world)
    await parties.active_grant(owners[0], owners[1], [owners[1]])
    auth = inventory.idp.bearer(owners[1].subject, email=owners[1].email)
    assert (await stock.set_rules()).status_code == 200
    item = (await inventory.item(quantity_scale=0))["item_id"]
    await received(stock, item, "5", "10.00")
    document = stock.rows("select id from gba.stock_documents")[0][0]
    before = stock.counts()
    base = f"/v1/businesses/{stock.tenant}/inventory"
    for path in (
        "/items",
        f"/items/{item}",
        "/places",
        f"/places/{stock.place['place_id']}",
        "/balances",
        "/costs",
        "/documents",
        f"/documents/{document}",
        f"/posting-rules/{stock.book}",
    ):
        read = await inventory.client.get(base + path, headers=auth)
        assert read.status_code == 403, path
    line = {"item_id": item, "quantity": "1", "amount": "2.00"}
    for path, body in (
        (f"/items/{uuid7()}", item_body()),
        (f"/documents/{uuid7()}", stock.receipt([line])),
        (f"/posting-rules/{stock.book}", stock.rules(1)),
    ):
        written = await inventory.client.put(
            base + path, json=body, headers={**auth, "Idempotency-Key": str(uuid7())}
        )
        assert written.status_code == 403, path
    reference = {
        "schema_version": 1,
        "operation": "document",
        "subject_id": str(uuid7()),
        "revision": 0,
    }
    for action in ("resolve", "cancel"):
        settled = await inventory.client.post(
            f"{base}/commands/FAKE-j12-command/{action}", json=reference, headers=auth
        )
        assert settled.status_code == 403, action
    assert stock.counts() == before


async def test_j13_a_purchase_and_its_bill_leave_nothing_on_the_receipt_account(
    stock: Stock,
) -> None:
    inventory = stock.inventory
    assert (await stock.set_rules()).status_code == 200
    await Config(inventory.client, inventory.idp).publish(
        inventory.manager,
        stock.tenant,
        1,
        ["booking_resources", "counterparties", "finance", "finance_documents", "inventory"],
    )
    supplier = uuid7()
    saved = await inventory.client.put(
        f"/v1/businesses/{stock.tenant}/counterparties/{supplier}",
        json=card(
            roles=["supplier"],
            display_name="FAKE supplier",
            email="fake.supplier@example.test",
            phone="+1 555 010 2009",
        ),
        headers=stock.keyed(),
    )
    assert saved.status_code == 200, saved.text
    item = (await inventory.item(quantity_scale=0))["item_id"]
    line = {"item_id": item, "quantity": "4", "amount": "25.00"}
    posted = await stock.post(
        stock.receipt([line], supplier_id=str(supplier), supplier_document="FAKE-BILL-1")
    )
    assert posted.status_code == 200, posted.text
    # The supplier's bill: the payable on the control account, the receipt account debited.
    bill = uuid7()
    bills = f"/v1/businesses/{stock.tenant}/financial-documents/books/{stock.book}/invoices"
    drafted = await inventory.client.put(
        f"{bills}/{bill}",
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "direction": "payable",
            "counterparty_id": str(supplier),
            "counterparty_revision": 1,
            "currency": "USD",
            "invoice_date": DAY,
            "control_account_id": str(stock.accounts["2000"]),
            "title": "FAKE supplier bill",
            "number": "FAKE-BILL-1",
            "lines": [
                {
                    "line_id": str(uuid7()),
                    "counter_account_id": str(stock.accounts["1400"]),
                    "description": "FAKE materials",
                    "amount": "25.00",
                }
            ],
        },
        headers=stock.keyed(),
    )
    assert drafted.status_code == 200, drafted.text
    issued = await inventory.client.post(
        f"{bills}/{bill}/issue",
        json={
            "schema_version": 1,
            "expected_revision": 1,
            "entry_date": DAY,
            "attestation": "confirmed_account_treatment",
        },
        headers=stock.keyed(),
    )
    assert issued.status_code == 200, issued.text

    def net(code: str) -> int:
        row = stock.rows(
            "select coalesce(sum(case side when 'debit' then amount_minor else -amount_minor "
            "end),0) from gba.journal_lines where account_id=%s",
            stock.accounts[code],
        )
        return int(str(row[0][0]))

    assert (net("1400"), net("1300"), net("2000")) == (0, 2500, -2500)


async def test_gap10_accumulated_totals_stay_in_range_with_a_named_refusal(
    stock: Stock,
) -> None:
    assert (await stock.set_rules()).status_code == 200
    many = (await stock.inventory.item(quantity_scale=0))["item_id"]
    dear = (await stock.inventory.item(quantity_scale=0))["item_id"]
    # Ten receipts of a hundred largest lines bring each total next to its limit.
    for lines in (
        [{"item_id": many, "quantity": "999999999999", "amount": "0.01"}] * 100,
        [{"item_id": dear, "quantity": "1", "amount": "9999999999999.99"}] * 100,
    ):
        for _ in range(10):
            posted = await stock.post(stock.receipt(lines))
            assert posted.status_code == 200, posted.text
    totals = stock.rows("select item_id,quantity,value_minor from gba.stock_costs")
    assert sorted((str(i), q, v) for i, q, v in totals) == sorted(
        [(str(many), 999999999999000, 1000), (str(dear), 1000, 999999999999999000)]
    )
    before = stock.counts()
    more = await stock.post(
        stock.receipt([{"item_id": many, "quantity": "1000", "amount": "0.01"}])
    )
    assert error(more) == (422, "STOCK_QUANTITY_INVALID"), more.text
    dearer = await stock.post(
        stock.receipt([{"item_id": dear, "quantity": "1", "amount": "10.00"}])
    )
    assert error(dearer) == (422, "STOCK_AMOUNT_INVALID"), dearer.text
    assert stock.counts() == before
    value, booked = stock.reconciled()
    assert value == booked


async def test_gap10_a_return_never_moves_another_owners_stock_by_sql(stock: Stock) -> None:
    assert (await stock.set_rules()).status_code == 200
    item = (await stock.inventory.item(quantity_scale=0))["item_id"]
    await received(stock, item, "5", "10.00")
    source = stock.rows("select id from gba.stock_documents")[0][0]
    other, _, _ = await entity_with_book(stock.inventory, stock.pool, "OTHER")
    before = stock.counts()
    user = stock.inventory.manager.user_id
    state = await refused_sql(
        stock.pool,
        stock.tenant,
        user,
        "insert into gba.stock_documents (tenant_id,id,kind,reason,legal_entity_id,place_id,"
        "location_id,document_date,line_count,created_by,source_document_id) "
        "values (%s,%s,'return','supplier_return',%s,%s,%s,%s,1,%s,%s)",
        (
            stock.tenant,
            uuid7(),
            other,
            stock.place["place_id"],
            stock.place["location_id"],
            DAY,
            user,
            source,
        ),
    )
    assert state == "23514"
    assert stock.counts() == before


async def test_gap10_archiving_a_material_and_a_receipt_of_it_take_one_order(
    stock: Stock, test_database: ProvisionedDatabase
) -> None:
    """The receipt waits for the archive and is then refused by name.

    The race counts only when the receipt is seen in pg_locks waiting for a row lock.
    """
    assert (await stock.set_rules()).status_code == 200
    item = (await stock.inventory.item(quantity_scale=0))["item_id"]
    await received(stock, item, "5", "10.00")
    before = stock.counts()
    monitor = await psycopg.AsyncConnection.connect(
        test_database.admin_dsn, dbname=test_database.name, autocommit=True
    )
    follower: asyncio.Task[httpx.Response] | None = None
    try:
        async with tenant_transaction(stock.pool, stock.tenant) as leader:
            user = stock.inventory.manager.user_id
            await set_user_context(leader, user)
            # The archive takes the row of the material and adds its archived version.
            await leader.execute(
                "select 1 from gba.stock_items where tenant_id=%s and id=%s for update",
                (stock.tenant, item),
            )
            await leader.execute(
                ITEM_VERSION.replace("false", "true"), (stock.tenant, item, 2, user)
            )
            line = {"item_id": item, "quantity": "1", "amount": "2.00"}
            follower = asyncio.create_task(stock.post(stock.receipt([line])))
            deadline = asyncio.get_running_loop().time() + 8
            while asyncio.get_running_loop().time() < deadline:
                row = await (await monitor.execute(ROW_WAITERS)).fetchone()
                if row is not None and row[0] >= 1:
                    break
                await asyncio.sleep(0.01)
            else:
                pytest.fail("The receipt must be seen in pg_locks waiting for a row lock")
            assert not follower.done()
        refused = await asyncio.wait_for(follower, 15)
    finally:
        if follower is not None and not follower.done():
            follower.cancel()
        await monitor.close()
    assert error(refused) == (409, "STOCK_ARCHIVED"), refused.text
    assert stock.counts() == before
