"""REST-01 Slice 3: independent checks, kitchen station tickets and STOCK-01 write-offs."""

from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid7

import pytest
from psycopg_pool import AsyncConnectionPool

from gorgona_booking.business import ledger
from gorgona_booking.business.ledger_contracts import BookInput
from gorgona_booking.db.pool import tenant_transaction
from tests.integration.test_delegations import client, idp, owner_a, owner_b
from tests.integration.test_restaurant_floor_and_tables import RestaurantEnv, rest_env
from tests.integration.test_restaurant_menu_and_recipes import _create_stock_item

pytestmark = pytest.mark.anyio
__all__ = ["client", "idp", "owner_a", "owner_b", "rest_env"]

DAY = "2026-10-01"


async def _setup_stock_books_and_place(
    env: RestaurantEnv,
    app_pool: AsyncConnectionPool,
    *,
    location_id: UUID,
) -> tuple[UUID, UUID, UUID, dict[str, UUID]]:
    entity_id = uuid7()
    book_id = uuid7()
    place_id = uuid7()

    res_ent = await env.client.put(
        f"/v1/businesses/{env.tenant}/legal-entities/{entity_id}",
        headers=env.headers(env.owner, key=f"rest-ent-{uuid7()}"),
        json={
            "expected_revision": 0,
            "code": "REST_LE",
            "legal_name": "Restaurant LLC",
        },
    )
    assert res_ent.status_code == 200, res_ent.text

    async with tenant_transaction(app_pool, env.tenant) as conn:
        await ledger.save_book(
            conn,
            business_id=env.tenant,
            book_id=book_id,
            user_id=env.owner.user_id,
            actor=f"user:{env.owner.user_id}",
            key=str(uuid7()),
            body=BookInput(
                expected_revision=0,
                legal_entity_id=entity_id,
                base_currency="USD",
                fiscal_year_start_month=1,
                accounting_start=date(2026, 1, 1),
            ),
        )
        listed = await ledger.list_accounts(conn, env.tenant, book_id, after=None, limit=100)
    accounts = {account.code: account.account_id for account in listed.items}

    rules_res = await env.client.put(
        f"/v1/businesses/{env.tenant}/inventory/posting-rules/{book_id}",
        headers=env.headers(env.owner, key=f"rest-rules-{uuid7()}"),
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "inventory_account_id": str(accounts["1300"]),
            "receipt_account_id": str(accounts["1400"]),
            "opening_account_id": str(accounts["3900"]),
            "surplus_account_id": str(accounts["4900"]),
            "consumption_account_id": str(accounts["5000"]),
            "loss_account_id": str(accounts["6900"]),
            "difference_account_id": str(accounts["6900"]),
        },
    )
    assert rules_res.status_code == 200, rules_res.text

    place_res = await env.client.put(
        f"/v1/businesses/{env.tenant}/inventory/places/{place_id}",
        headers=env.headers(env.owner, key=f"rest-place-{uuid7()}"),
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "location_id": str(location_id),
            "code": "KITCHEN_A",
            "name": "Main Kitchen Walk-In",
            "archived": False,
        },
    )
    assert place_res.status_code == 200, place_res.text
    return entity_id, book_id, place_id, accounts


async def test_takeout_check_modifiers_kitchen_stations_and_stock_write_off(
    rest_env: RestaurantEnv,
    app_pool: AsyncConnectionPool,
) -> None:
    # 1. Provision STOCK-01 books, storage place, materials, and opening receipt
    entity_id, _book_id, place_id, _ = await _setup_stock_books_and_place(
        rest_env, app_pool, location_id=rest_env.branch_a
    )
    beef_id = await _create_stock_item(
        rest_env, code="BEEF_01", name="Beef Patty", unit="g", quantity_scale=0
    )
    cheese_id = await _create_stock_item(
        rest_env, code="CHEESE_01", name="Cheddar", unit="g", quantity_scale=1
    )
    cola_id = await _create_stock_item(
        rest_env, code="COLA_CAN", name="Cola Can", unit="pcs", quantity_scale=0
    )

    receipt_res = await rest_env.client.put(
        f"/v1/businesses/{rest_env.tenant}/inventory/documents/{uuid7()}",
        headers=rest_env.headers(rest_env.owner, key=f"rest-rcpt-{uuid7()}"),
        json={
            "schema_version": 1,
            "kind": "receipt",
            "reason": "opening_balance",
            "legal_entity_id": str(entity_id),
            "place_id": str(place_id),
            "document_date": DAY,
            "lines": [
                {"item_id": str(beef_id), "quantity": "1000", "amount": "20.00"},
                {"item_id": str(cheese_id), "quantity": "100.0", "amount": "10.00"},
                {"item_id": str(cola_id), "quantity": "20", "amount": "20.00"},
            ],
        },
    )
    assert receipt_res.status_code == 200, receipt_res.text

    # 2. Create menu items on different stations (hot + bar), modifier group, and recipes
    burger_id = uuid7()
    assert (
        await rest_env.client.put(
            rest_env.url(f"/menu-items/{burger_id}"),
            headers=rest_env.headers(rest_env.branch_a_mgr, key="rest-s3-burger"),
            json={
                "schema_version": 1,
                "expected_revision": 0,
                "location_id": str(rest_env.branch_a),
                "code": "BURGER_S3",
                "name": "Grill Burger",
                "category": "Mains",
                "kitchen_station": "hot",
                "price_minor": 1500,
                "currency": "USD",
            },
        )
    ).status_code == 200

    drink_id = uuid7()
    assert (
        await rest_env.client.put(
            rest_env.url(f"/menu-items/{drink_id}"),
            headers=rest_env.headers(rest_env.branch_a_mgr, key="rest-s3-drink"),
            json={
                "schema_version": 1,
                "expected_revision": 0,
                "location_id": str(rest_env.branch_a),
                "code": "COLA_S3",
                "name": "Craft Cola",
                "category": "Drinks",
                "kitchen_station": "bar",
                "price_minor": 400,
                "currency": "USD",
            },
        )
    ).status_code == 200

    # Required modifier group (min/max=1) + optional toppings with cheese stock link
    temp_grp = uuid7()
    assert (
        await rest_env.client.put(
            rest_env.url(f"/modifier-groups/{temp_grp}"),
            headers=rest_env.headers(rest_env.branch_a_mgr, key="rest-s3-temp-grp"),
            json={
                "schema_version": 1,
                "expected_revision": 0,
                "location_id": str(rest_env.branch_a),
                "code": "TEMP_S3",
                "name": "Doneness",
                "min_select": 1,
                "max_select": 1,
                "currency": "USD",
            },
        )
    ).status_code == 200
    med_opt = uuid7()
    assert (
        await rest_env.client.put(
            rest_env.url(f"/modifier-groups/{temp_grp}/options/{med_opt}"),
            headers=rest_env.headers(rest_env.branch_a_mgr, key="rest-s3-opt-med"),
            json={
                "schema_version": 1,
                "expected_revision": 0,
                "code": "MEDIUM",
                "name": "Medium",
                "price_delta_minor": 0,
            },
        )
    ).status_code == 200

    extra_grp = uuid7()
    assert (
        await rest_env.client.put(
            rest_env.url(f"/modifier-groups/{extra_grp}"),
            headers=rest_env.headers(rest_env.branch_a_mgr, key="rest-s3-extra-grp"),
            json={
                "schema_version": 1,
                "expected_revision": 0,
                "location_id": str(rest_env.branch_a),
                "code": "EXTRAS_S3",
                "name": "Extras",
                "min_select": 0,
                "max_select": 2,
                "currency": "USD",
            },
        )
    ).status_code == 200
    cheese_opt = uuid7()
    assert (
        await rest_env.client.put(
            rest_env.url(f"/modifier-groups/{extra_grp}/options/{cheese_opt}"),
            headers=rest_env.headers(rest_env.branch_a_mgr, key="rest-s3-opt-chs"),
            json={
                "schema_version": 1,
                "expected_revision": 0,
                "code": "EXTRA_CHS",
                "name": "Extra Cheddar",
                "price_delta_minor": 200,
                "stock_item_id": str(cheese_id),
                "stock_quantity": 250,  # 25.0g at scale 1
            },
        )
    ).status_code == 200

    assert (
        await rest_env.client.put(
            rest_env.url(f"/menu-items/{burger_id}/modifier-groups"),
            headers=rest_env.headers(rest_env.branch_a_mgr, key="rest-s3-attach"),
            json={"schema_version": 1, "modifier_group_ids": [str(temp_grp), str(extra_grp)]},
        )
    ).status_code == 200

    assert (
        await rest_env.client.post(
            rest_env.url(f"/menu-items/{burger_id}/recipes"),
            headers=rest_env.headers(rest_env.branch_a_mgr, key="rest-s3-rec-bg"),
            json={
                "schema_version": 1,
                "expected_revision": 0,
                "lines": [{"stock_item_id": str(beef_id), "quantity": 180}],
            },
        )
    ).status_code == 200
    assert (
        await rest_env.client.post(
            rest_env.url(f"/menu-items/{drink_id}/recipes"),
            headers=rest_env.headers(rest_env.branch_a_mgr, key="rest-s3-rec-dr"),
            json={
                "schema_version": 1,
                "expected_revision": 0,
                "lines": [{"stock_item_id": str(cola_id), "quantity": 1}],
            },
        )
    ).status_code == 200

    # 3. Open an independent TAKEOUT check (no table, no reservation, no shift!)
    open_res = await rest_env.client.post(
        rest_env.url("/checks"),
        headers=rest_env.headers(rest_env.front_desk_a, key="rest-s3-open-1"),
        json={
            "schema_version": 1,
            "location_id": str(rest_env.branch_a),
            "service_mode": "takeout",
            "currency": "USD",
            "guest_name": "Alex Takeout",
        },
    )
    assert open_res.status_code == 200, open_res.text
    check_id = open_res.json()["check_id"]
    assert open_res.json()["table_id"] is None
    assert open_res.json()["subtotal_minor"] == 0

    # Missing required modifier group (Doneness min_select=1) is rejected with 409
    bad_line = await rest_env.client.post(
        rest_env.url(f"/checks/{check_id}/lines"),
        headers=rest_env.headers(rest_env.front_desk_a, key="rest-s3-line-bad"),
        json={
            "schema_version": 1,
            "menu_item_id": str(burger_id),
            "quantity": 1,
            "modifier_option_ids": [],
        },
    )
    assert bad_line.status_code == 409

    # Add 2 Burgers with Medium + Extra Cheddar -> (1500 + 200) * 2 = 3400
    add_bg = await rest_env.client.post(
        rest_env.url(f"/checks/{check_id}/lines"),
        headers=rest_env.headers(rest_env.front_desk_a, key="rest-s3-line-bg"),
        json={
            "schema_version": 1,
            "menu_item_id": str(burger_id),
            "quantity": 2,
            "modifier_option_ids": [str(med_opt), str(cheese_opt)],
        },
    )
    assert add_bg.status_code == 200, add_bg.text
    assert add_bg.json()["subtotal_minor"] == 3400

    # Add 1 Cola (bar station) -> +400 = 3800
    add_dr = await rest_env.client.post(
        rest_env.url(f"/checks/{check_id}/lines"),
        headers=rest_env.headers(rest_env.front_desk_a, key="rest-s3-line-dr"),
        json={
            "schema_version": 1,
            "menu_item_id": str(drink_id),
            "quantity": 1,
        },
    )
    assert add_dr.status_code == 200, add_dr.text
    assert add_dr.json()["subtotal_minor"] == 3800

    # Add a third draft Cola and void it before firing (front_desk can void draft!)
    add_dr2 = await rest_env.client.post(
        rest_env.url(f"/checks/{check_id}/lines"),
        headers=rest_env.headers(rest_env.front_desk_a, key="rest-s3-line-dr2"),
        json={"schema_version": 1, "menu_item_id": str(drink_id), "quantity": 1},
    )
    assert add_dr2.status_code == 200
    dr2_line_id = add_dr2.json()["lines"][-1]["line_id"]
    assert add_dr2.json()["subtotal_minor"] == 4200

    void_dr2 = await rest_env.client.post(
        rest_env.url(f"/checks/{check_id}/lines/{dr2_line_id}/void"),
        headers=rest_env.headers(rest_env.front_desk_a, key="rest-s3-void-dr2"),
        json={"schema_version": 1, "reason": "Entered twice"},
    )
    assert void_dr2.status_code == 200, void_dr2.text
    assert void_dr2.json()["subtotal_minor"] == 3800

    # Change menu item price AFTER ordering -> frozen check line MUST NOT change!
    assert (
        await rest_env.client.put(
            rest_env.url(f"/menu-items/{burger_id}"),
            headers=rest_env.headers(rest_env.branch_a_mgr, key="rest-s3-price-up"),
            json={
                "schema_version": 1,
                "expected_revision": 1,
                "location_id": str(rest_env.branch_a),
                "code": "BURGER_S3",
                "name": "Grill Burger",
                "category": "Mains",
                "kitchen_station": "hot",
                "price_minor": 2999,
                "currency": "USD",
            },
        )
    ).status_code == 200

    # 4. Fire draft lines -> produces 2 station-routed tickets: bar & hot
    fire = await rest_env.client.post(
        rest_env.url(f"/checks/{check_id}/fire"),
        headers=rest_env.headers(rest_env.front_desk_a, key="rest-s3-fire-1"),
        json={"schema_version": 1},
    )
    assert fire.status_code == 200, fire.text
    tickets = fire.json()["tickets"]
    assert [t["kitchen_station"] for t in tickets] == ["bar", "hot"]
    bar_ticket, hot_ticket = tickets[0], tickets[1]

    # Front desk CANNOT void a fired line (requires restaurant.manage -> 403)
    burger_line_id = hot_ticket["lines"][0]["line_id"]
    assert (
        await rest_env.client.post(
            rest_env.url(f"/checks/{check_id}/lines/{burger_line_id}/void"),
            headers=rest_env.headers(rest_env.front_desk_a, key="rest-s3-fd-void-fired"),
            json={"schema_version": 1, "reason": "Try void"},
        )
    ).status_code == 403

    # Kitchen staff (artist role -> restaurant.kitchen) advances both tickets to served
    for ticket in (bar_ticket, hot_ticket):
        tid = ticket["ticket_id"]
        for rev, action in ((1, "start"), (2, "mark_ready"), (3, "serve")):
            ev_res = await rest_env.client.post(
                rest_env.url(f"/kitchen/tickets/{tid}/events"),
                headers=rest_env.headers(rest_env.kitchen_a, key=f"rest-s3-ev-{tid}-{action}"),
                json={"schema_version": 1, "expected_revision": rev, "action": action},
            )
            assert ev_res.status_code == 200, ev_res.text
            assert ev_res.json()["revision"] == rev + 1

    # Verify check lines are now 'served' and frozen price stayed 1500 + 200 = 1700
    chk_after = (
        await rest_env.client.get(
            rest_env.url(f"/checks/{check_id}"),
            headers=rest_env.headers(rest_env.front_desk_a),
        )
    ).json()
    assert chk_after["subtotal_minor"] == 3800
    assert chk_after["lines"][0]["base_price_minor"] == 1500
    assert chk_after["lines"][0]["status"] == "served"
    assert chk_after["lines"][1]["status"] == "served"

    # 5. Preview planned consumption: Beef 180*2=360g, Cheddar 25.0*2=50.0g (500), Cola 1
    preview = await rest_env.client.get(
        rest_env.url(f"/checks/{check_id}/consumption"),
        headers=rest_env.headers(rest_env.front_desk_a),
    )
    assert preview.status_code == 200
    assert preview.json()["posted"] is False
    assert [(x["stock_item_code"], x["quantity"]) for x in preview.json()["lines"]] == [
        ("BEEF_01", 360),
        ("CHEESE_01", 500),
        ("COLA_CAN", 1),
    ]

    # Branch manager CANNOT post STOCK-01 write-off (company-wide only -> 403)
    assert (
        await rest_env.client.post(
            rest_env.url(f"/checks/{check_id}/post-consumption"),
            headers=rest_env.headers(rest_env.branch_a_mgr, key="rest-s3-cons-branch-deny"),
            json={
                "schema_version": 1,
                "legal_entity_id": str(entity_id),
                "place_id": str(place_id),
                "document_date": DAY,
            },
        )
    ).status_code == 403

    # Company-wide owner posts coordinated STOCK-01 write-off ONCE
    posted = await rest_env.client.post(
        rest_env.url(f"/checks/{check_id}/post-consumption"),
        headers=rest_env.headers(rest_env.owner, key="rest-s3-cons-post-1"),
        json={
            "schema_version": 1,
            "legal_entity_id": str(entity_id),
            "place_id": str(place_id),
            "document_date": DAY,
        },
    )
    assert posted.status_code == 200, posted.text
    cons = posted.json()
    assert cons["posted"] is True
    assert cons["stock_document_id"] is not None

    # Idempotent replay returns exact same posted record without double write-off
    replay = await rest_env.client.post(
        rest_env.url(f"/checks/{check_id}/post-consumption"),
        headers=rest_env.headers(rest_env.owner, key="rest-s3-cons-post-1"),
        json={
            "schema_version": 1,
            "legal_entity_id": str(entity_id),
            "place_id": str(place_id),
            "document_date": DAY,
        },
    )
    assert replay.status_code == 200
    assert replay.json() == cons

    # A second post-consumption with a new key is rejected with 409 (no double write-off!)
    double = await rest_env.client.post(
        rest_env.url(f"/checks/{check_id}/post-consumption"),
        headers=rest_env.headers(rest_env.owner, key="rest-s3-cons-post-2"),
        json={
            "schema_version": 1,
            "legal_entity_id": str(entity_id),
            "place_id": str(place_id),
            "document_date": DAY,
        },
    )
    assert double.status_code == 409

    # Close the check cleanly
    closed = await rest_env.client.post(
        rest_env.url(f"/checks/{check_id}/close"),
        headers=rest_env.headers(rest_env.front_desk_a, key="rest-s3-close-1"),
        json={"schema_version": 1, "expected_revision": chk_after["revision"]},
    )
    assert closed.status_code == 200, closed.text
    assert closed.json()["status"] == "closed"

    # Verify PostgreSQL STOCK-01 balances: Beef 640, Cheese 500, Cola 19
    async with tenant_transaction(app_pool, rest_env.tenant) as conn:
        bals = await (
            await conn.execute(
                "select s.code, b.quantity from gba.stock_balances b "
                "join gba.stock_items s on s.tenant_id = b.tenant_id and s.id = b.item_id "
                "where b.tenant_id = %s and b.place_id = %s order by s.code",
                (rest_env.tenant, place_id),
            )
        ).fetchall()
    assert bals == [("BEEF_01", 640), ("CHEESE_01", 500), ("COLA_CAN", 19)]


async def test_dine_in_table_reservation_mismatch_and_branch_rls(
    rest_env: RestaurantEnv,
) -> None:
    # Create area, two tables, and a reservation on table 1
    area_id = uuid7()
    assert (
        await rest_env.client.put(
            rest_env.url(f"/areas/{area_id}"),
            headers=rest_env.headers(rest_env.branch_a_mgr, key="rest-s3-area-1"),
            json={
                "schema_version": 1,
                "expected_revision": 0,
                "location_id": str(rest_env.branch_a),
                "name": "Main Hall",
                "service_style": "dining",
            },
        )
    ).status_code == 200

    t1, t2 = uuid7(), uuid7()
    for code, tid in (("T1", t1), ("T2", t2)):
        assert (
            await rest_env.client.put(
                rest_env.url(f"/tables/{tid}"),
                headers=rest_env.headers(rest_env.branch_a_mgr, key=f"rest-s3-tbl-{code}"),
                json={
                    "schema_version": 1,
                    "expected_revision": 0,
                    "location_id": str(rest_env.branch_a),
                    "area_id": str(area_id),
                    "code": code,
                    "min_covers": 1,
                    "max_covers": 4,
                },
            )
        ).status_code == 200

    start = datetime.now(UTC) + timedelta(hours=2)
    res_id = uuid7()
    assert (
        await rest_env.client.put(
            rest_env.url(f"/reservations/{res_id}"),
            headers=rest_env.headers(rest_env.front_desk_a, key="rest-s3-res-1"),
            json={
                "schema_version": 1,
                "table_id": str(t1),
                "guest_name": "Maria",
                "party_size": 2,
                "starts_at": start.isoformat(),
                "ends_at": (start + timedelta(hours=2)).isoformat(),
            },
        )
    ).status_code == 200

    # Opening check with table T2 + reservation on T1 is rejected with 409
    mismatch = await rest_env.client.post(
        rest_env.url("/checks"),
        headers=rest_env.headers(rest_env.front_desk_a, key="rest-s3-mismatch"),
        json={
            "schema_version": 1,
            "location_id": str(rest_env.branch_a),
            "service_mode": "dine_in",
            "table_id": str(t2),
            "reservation_id": str(res_id),
            "currency": "USD",
        },
    )
    assert mismatch.status_code == 409

    # Opening check with matching table T1 + reservation succeeds
    ok = await rest_env.client.post(
        rest_env.url("/checks"),
        headers=rest_env.headers(rest_env.front_desk_a, key="rest-s3-dine-ok"),
        json={
            "schema_version": 1,
            "location_id": str(rest_env.branch_a),
            "service_mode": "dine_in",
            "table_id": str(t1),
            "reservation_id": str(res_id),
            "currency": "USD",
        },
    )
    assert ok.status_code == 200, ok.text
    cid = ok.json()["check_id"]

    # Branch B manager cannot see Branch A check (404), delegate cannot access (403)
    assert (
        await rest_env.client.get(
            rest_env.url(f"/checks/{cid}"),
            headers=rest_env.headers(rest_env.branch_b_mgr),
        )
    ).status_code == 404
    assert (
        await rest_env.client.get(
            rest_env.url("/checks"),
            headers=rest_env.headers(rest_env.delegate_b),
        )
    ).status_code == 403
