"""REST-01 Slice 2: versioned menu items, modifiers, STOCK-01 recipe BOMs and RLS."""

from uuid import UUID, uuid7

import psycopg
import pytest
from psycopg_pool import AsyncConnectionPool

from gorgona_booking.db.pool import tenant_transaction
from tests.integration.test_delegations import client, idp, owner_a, owner_b
from tests.integration.test_restaurant_floor_and_tables import RestaurantEnv, rest_env

pytestmark = pytest.mark.anyio
__all__ = ["client", "idp", "owner_a", "owner_b", "rest_env"]


async def _create_stock_item(
    env: RestaurantEnv,
    *,
    code: str,
    name: str,
    unit: str,
    quantity_scale: int,
    archived: bool = False,
    item_id: UUID | None = None,
    expected_revision: int = 0,
) -> UUID:
    sid = item_id or uuid7()
    res = await env.client.put(
        f"/v1/businesses/{env.tenant}/inventory/items/{sid}",
        headers=env.headers(env.owner, key=f"stock-{code}-{expected_revision}-{uuid7()}"),
        json={
            "schema_version": 1,
            "expected_revision": expected_revision,
            "code": code,
            "name": name,
            "unit": unit,
            "quantity_scale": quantity_scale,
            "archived": archived,
        },
    )
    assert res.status_code == 200, res.text
    return sid


async def test_menu_items_versioning_revisions_and_filters(rest_env: RestaurantEnv) -> None:
    item_id = uuid7()
    payload_v1 = {
        "schema_version": 1,
        "expected_revision": 0,
        "location_id": str(rest_env.branch_a),
        "code": "BURGER_CLASSIC",
        "name": "Classic Burger",
        "category": "Mains",
        "kitchen_station": "hot",
        "price_minor": 1450,
        "currency": "USD",
        "description": "Beef patty on brioche bun",
        "is_active": True,
    }
    res = await rest_env.client.put(
        rest_env.url(f"/menu-items/{item_id}"),
        headers=rest_env.headers(rest_env.branch_a_mgr, key="rest-menu-menu-v1"),
        json=payload_v1,
    )
    assert res.status_code == 200, res.text
    v1 = res.json()
    assert v1["revision"] == 1
    assert v1["price_minor"] == 1450
    assert v1["kitchen_station"] == "hot"
    assert v1["modifier_group_ids"] == []
    assert v1["latest_recipe_revision"] is None

    # Idempotent replay returns exact same view
    replay = await rest_env.client.put(
        rest_env.url(f"/menu-items/{item_id}"),
        headers=rest_env.headers(rest_env.branch_a_mgr, key="rest-menu-menu-v1"),
        json=payload_v1,
    )
    assert replay.status_code == 200
    assert replay.json() == v1

    # Duplicate code in same branch is rejected with 409
    dup = await rest_env.client.put(
        rest_env.url(f"/menu-items/{uuid7()}"),
        headers=rest_env.headers(rest_env.branch_a_mgr, key="rest-menu-menu-dup"),
        json=payload_v1,
    )
    assert dup.status_code == 409

    # Update to revision 2 changes price and description while preserving revision 1
    payload_v2 = {
        **payload_v1,
        "expected_revision": 1,
        "price_minor": 1590,
        "description": "Dry-aged beef patty on toasted brioche",
    }
    res2 = await rest_env.client.put(
        rest_env.url(f"/menu-items/{item_id}"),
        headers=rest_env.headers(rest_env.branch_a_mgr, key="rest-menu-menu-v2"),
        json=payload_v2,
    )
    assert res2.status_code == 200, res2.text
    assert res2.json()["revision"] == 2
    assert res2.json()["price_minor"] == 1590

    # Stale revision fails with 409
    stale = await rest_env.client.put(
        rest_env.url(f"/menu-items/{item_id}"),
        headers=rest_env.headers(rest_env.branch_a_mgr, key="menu-stale"),
        json=payload_v2,
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "RESTAURANT_REVISION_CONFLICT"

    # Changing immutable code is rejected
    bad_code = await rest_env.client.put(
        rest_env.url(f"/menu-items/{item_id}"),
        headers=rest_env.headers(rest_env.branch_a_mgr, key="menu-bad-code"),
        json={**payload_v2, "expected_revision": 2, "code": "BURGER_NEW"},
    )
    assert bad_code.status_code == 422

    # Read historical revision 1 and full revision history
    old_view = await rest_env.client.get(
        rest_env.url(f"/menu-items/{item_id}?revision=1"),
        headers=rest_env.headers(rest_env.front_desk_a),
    )
    assert old_view.status_code == 200
    assert old_view.json()["price_minor"] == 1450
    assert old_view.json()["revision"] == 1

    revs = await rest_env.client.get(
        rest_env.url(f"/menu-items/{item_id}/revisions"),
        headers=rest_env.headers(rest_env.kitchen_a),
    )
    assert revs.status_code == 200
    assert [r["price_minor"] for r in revs.json()["items"]] == [1450, 1590]

    # Add a second item on pastry station and verify filtering
    cake_id = uuid7()
    res_cake = await rest_env.client.put(
        rest_env.url(f"/menu-items/{cake_id}"),
        headers=rest_env.headers(rest_env.branch_a_mgr, key="rest-menu-cake-v1"),
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "location_id": str(rest_env.branch_a),
            "code": "CAKE_CHOC",
            "name": "Chocolate Cake",
            "category": "Desserts",
            "kitchen_station": "pastry",
            "price_minor": 850,
            "currency": "USD",
            "is_active": False,
        },
    )
    assert res_cake.status_code == 200

    pastry = await rest_env.client.get(
        rest_env.url("/menu-items?kitchen_station=pastry"),
        headers=rest_env.headers(rest_env.front_desk_a),
    )
    assert [i["menu_item_id"] for i in pastry.json()["items"]] == [str(cake_id)]

    active = await rest_env.client.get(
        rest_env.url("/menu-items?active_only=true"),
        headers=rest_env.headers(rest_env.front_desk_a),
    )
    assert [i["menu_item_id"] for i in active.json()["items"]] == [str(item_id)]


async def test_modifiers_stock_links_currency_guards_and_recipes(
    rest_env: RestaurantEnv,
    app_pool: AsyncConnectionPool,
) -> None:
    beef_id = await _create_stock_item(
        rest_env, code="BEEF_PATTY", name="Beef Patty", unit="g", quantity_scale=0
    )
    bun_id = await _create_stock_item(
        rest_env, code="BRIOCHE_BUN", name="Brioche Bun", unit="pcs", quantity_scale=0
    )
    cheese_id = await _create_stock_item(
        rest_env, code="CHEDDAR", name="Cheddar Slice", unit="g", quantity_scale=1
    )
    archived_id = await _create_stock_item(
        rest_env, code="OLD_SAUCE", name="Old Sauce", unit="ml", quantity_scale=0
    )
    await _create_stock_item(
        rest_env,
        code="OLD_SAUCE",
        name="Old Sauce",
        unit="ml",
        quantity_scale=0,
        archived=True,
        item_id=archived_id,
        expected_revision=1,
    )

    burger_id = uuid7()
    assert (
        await rest_env.client.put(
            rest_env.url(f"/menu-items/{burger_id}"),
            headers=rest_env.headers(rest_env.branch_a_mgr, key="rest-menu-burger-1"),
            json={
                "schema_version": 1,
                "expected_revision": 0,
                "location_id": str(rest_env.branch_a),
                "code": "BURGER_01",
                "name": "House Burger",
                "category": "Mains",
                "kitchen_station": "hot",
                "price_minor": 1600,
                "currency": "USD",
            },
        )
    ).status_code == 200

    # Modifier groups: USD toppings + EUR incompatible group
    toppings_id = uuid7()
    res_g = await rest_env.client.put(
        rest_env.url(f"/modifier-groups/{toppings_id}"),
        headers=rest_env.headers(rest_env.branch_a_mgr, key="grp-toppings"),
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "location_id": str(rest_env.branch_a),
            "code": "TOPPINGS",
            "name": "Extra Toppings",
            "min_select": 0,
            "max_select": 3,
            "currency": "USD",
        },
    )
    assert res_g.status_code == 200, res_g.text
    assert res_g.json()["options"] == []

    eur_group_id = uuid7()
    assert (
        await rest_env.client.put(
            rest_env.url(f"/modifier-groups/{eur_group_id}"),
            headers=rest_env.headers(rest_env.branch_a_mgr, key="rest-menu-grp-eur"),
            json={
                "schema_version": 1,
                "expected_revision": 0,
                "location_id": str(rest_env.branch_a),
                "code": "EUR_MODS",
                "name": "Euro Modifiers",
                "min_select": 0,
                "max_select": 1,
                "currency": "EUR",
            },
        )
    ).status_code == 200

    # Modifier option linked to STOCK-01 Cheddar (30.0g -> 300 at scale 1)
    cheese_opt_id = uuid7()
    res_opt = await rest_env.client.put(
        rest_env.url(f"/modifier-groups/{toppings_id}/options/{cheese_opt_id}"),
        headers=rest_env.headers(rest_env.branch_a_mgr, key="opt-cheese"),
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "code": "EXTRA_CHEESE",
            "name": "Extra Cheddar",
            "price_delta_minor": 250,
            "sort_order": 10,
            "stock_item_id": str(cheese_id),
            "stock_quantity": 300,
        },
    )
    assert res_opt.status_code == 200, res_opt.text
    opt_data = res_opt.json()
    assert opt_data["stock_item_code"] == "CHEDDAR"
    assert opt_data["stock_item_unit"] == "g"
    assert opt_data["stock_item_quantity_scale"] == 1
    assert opt_data["stock_quantity"] == 300

    # Archived material rejected on modifier option
    bad_opt = await rest_env.client.put(
        rest_env.url(f"/modifier-groups/{toppings_id}/options/{uuid7()}"),
        headers=rest_env.headers(rest_env.branch_a_mgr, key="rest-menu-opt-arch"),
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "code": "OLD_OPT",
            "name": "Old Sauce",
            "price_delta_minor": 100,
            "stock_item_id": str(archived_id),
            "stock_quantity": 20,
        },
    )
    assert bad_opt.status_code == 409

    # Attach toppings to burger
    attach = await rest_env.client.put(
        rest_env.url(f"/menu-items/{burger_id}/modifier-groups"),
        headers=rest_env.headers(rest_env.branch_a_mgr, key="rest-menu-attach-1"),
        json={"schema_version": 1, "modifier_group_ids": [str(toppings_id)]},
    )
    assert attach.status_code == 200, attach.text
    assert attach.json()["modifier_group_ids"] == [str(toppings_id)]

    # Attaching EUR group to USD menu item fails with 409
    bad_curr = await rest_env.client.put(
        rest_env.url(f"/menu-items/{burger_id}/modifier-groups"),
        headers=rest_env.headers(rest_env.branch_a_mgr, key="attach-eur"),
        json={"schema_version": 1, "modifier_group_ids": [str(eur_group_id)]},
    )
    assert bad_curr.status_code == 409

    # Changing menu item currency while USD modifier group is attached fails with 409
    drift_item = await rest_env.client.put(
        rest_env.url(f"/menu-items/{burger_id}"),
        headers=rest_env.headers(rest_env.branch_a_mgr, key="drift-item"),
        json={
            "schema_version": 1,
            "expected_revision": 1,
            "location_id": str(rest_env.branch_a),
            "code": "BURGER_01",
            "name": "House Burger",
            "category": "Mains",
            "kitchen_station": "hot",
            "price_minor": 1600,
            "currency": "EUR",
        },
    )
    assert drift_item.status_code == 409

    # Changing modifier group currency while USD menu item is attached fails with 409
    drift_grp = await rest_env.client.put(
        rest_env.url(f"/modifier-groups/{toppings_id}"),
        headers=rest_env.headers(rest_env.branch_a_mgr, key="rest-menu-drift-grp"),
        json={
            "schema_version": 1,
            "expected_revision": 1,
            "location_id": str(rest_env.branch_a),
            "code": "TOPPINGS",
            "name": "Extra Toppings",
            "min_select": 0,
            "max_select": 3,
            "currency": "EUR",
        },
    )
    assert drift_grp.status_code == 409

    # Create recipe BOM revision 1 (beef 180g + 1 bun)
    rec1 = await rest_env.client.post(
        rest_env.url(f"/menu-items/{burger_id}/recipes"),
        headers=rest_env.headers(rest_env.branch_a_mgr, key="rest-menu-rec-1"),
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "note": "Standard single patty recipe",
            "lines": [
                {"stock_item_id": str(beef_id), "quantity": 180, "note": "Sear medium-rare"},
                {"stock_item_id": str(bun_id), "quantity": 1},
            ],
        },
    )
    assert rec1.status_code == 200, rec1.text
    r1 = rec1.json()
    assert r1["revision"] == 1
    assert [(line["stock_item_code"], line["quantity"]) for line in r1["lines"]] == [
        ("BEEF_PATTY", 180),
        ("BRIOCHE_BUN", 1),
    ]

    # Idempotent replay on recipe creation returns revision 1
    rec1_replay = await rest_env.client.post(
        rest_env.url(f"/menu-items/{burger_id}/recipes"),
        headers=rest_env.headers(rest_env.branch_a_mgr, key="rest-menu-rec-1"),
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "note": "Standard single patty recipe",
            "lines": [
                {"stock_item_id": str(beef_id), "quantity": 180, "note": "Sear medium-rare"},
                {"stock_item_id": str(bun_id), "quantity": 1},
            ],
        },
    )
    assert rec1_replay.status_code == 200
    assert rec1_replay.json() == r1

    # Archived material rejected in recipe BOM
    rec_arch = await rest_env.client.post(
        rest_env.url(f"/menu-items/{burger_id}/recipes"),
        headers=rest_env.headers(rest_env.branch_a_mgr, key="rest-menu-rec-arch"),
        json={
            "schema_version": 1,
            "expected_revision": 1,
            "lines": [{"stock_item_id": str(archived_id), "quantity": 10}],
        },
    )
    assert rec_arch.status_code == 409

    # Unknown stock_item_id rejected with 422
    rec_missing = await rest_env.client.post(
        rest_env.url(f"/menu-items/{burger_id}/recipes"),
        headers=rest_env.headers(rest_env.branch_a_mgr, key="rec-missing"),
        json={
            "schema_version": 1,
            "expected_revision": 1,
            "lines": [{"stock_item_id": str(uuid7()), "quantity": 10}],
        },
    )
    assert rec_missing.status_code == 422

    # Append recipe revision 2 (200g beef + 1 bun + 20.0g cheddar)
    rec2 = await rest_env.client.post(
        rest_env.url(f"/menu-items/{burger_id}/recipes"),
        headers=rest_env.headers(rest_env.branch_a_mgr, key="rest-menu-rec-2"),
        json={
            "schema_version": 1,
            "expected_revision": 1,
            "note": "Upgraded cheeseburger spec",
            "lines": [
                {"stock_item_id": str(beef_id), "quantity": 200},
                {"stock_item_id": str(bun_id), "quantity": 1},
                {"stock_item_id": str(cheese_id), "quantity": 200},
            ],
        },
    )
    assert rec2.status_code == 200, rec2.text
    assert rec2.json()["revision"] == 2

    # Menu item view reports latest_recipe_revision == 2 and attached modifier group
    burger_view = await rest_env.client.get(
        rest_env.url(f"/menu-items/{burger_id}"),
        headers=rest_env.headers(rest_env.front_desk_a),
    )
    assert burger_view.status_code == 200
    assert burger_view.json()["latest_recipe_revision"] == 2
    assert burger_view.json()["modifier_group_ids"] == [str(toppings_id)]

    # List recipes returns rev 2 then rev 1, and GET rev 1 is still intact
    rec_list = await rest_env.client.get(
        rest_env.url(f"/menu-items/{burger_id}/recipes"),
        headers=rest_env.headers(rest_env.kitchen_a),
    )
    assert rec_list.status_code == 200
    assert [r["revision"] for r in rec_list.json()["items"]] == [2, 1]

    rec_v1_get = await rest_env.client.get(
        rest_env.url(f"/menu-items/{burger_id}/recipes/1"),
        headers=rest_env.headers(rest_env.kitchen_a),
    )
    assert rec_v1_get.status_code == 200
    assert len(rec_v1_get.json()["lines"]) == 2

    # Direct DB immutability checks on revisions and recipes
    with pytest.raises(psycopg.DatabaseError):
        async with tenant_transaction(app_pool, rest_env.tenant) as conn:
            await conn.execute(
                "update gba.restaurant_menu_item_revisions set price_minor = 1 "
                "where tenant_id = %s and menu_item_id = %s and revision = 1",
                (rest_env.tenant, burger_id),
            )

    with pytest.raises(psycopg.DatabaseError):
        async with tenant_transaction(app_pool, rest_env.tenant) as conn:
            await conn.execute(
                "delete from gba.restaurant_recipe_lines "
                "where tenant_id = %s and menu_item_id = %s and revision = 1",
                (rest_env.tenant, burger_id),
            )


async def test_branch_rls_roles_and_delegation_isolation(rest_env: RestaurantEnv) -> None:
    item_a = uuid7()
    res = await rest_env.client.put(
        rest_env.url(f"/menu-items/{item_a}"),
        headers=rest_env.headers(rest_env.branch_a_mgr, key="rls-item-a"),
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "location_id": str(rest_env.branch_a),
            "code": "SOUP_A",
            "name": "Tomato Soup",
            "category": "Starters",
            "kitchen_station": "hot",
            "price_minor": 900,
            "currency": "USD",
        },
    )
    assert res.status_code == 200

    # Front desk and kitchen can read branch A, cannot mutate
    assert (
        await rest_env.client.get(
            rest_env.url(f"/menu-items/{item_a}"),
            headers=rest_env.headers(rest_env.front_desk_a),
        )
    ).status_code == 200
    assert (
        await rest_env.client.put(
            rest_env.url(f"/menu-items/{uuid7()}"),
            headers=rest_env.headers(rest_env.front_desk_a, key="rest-menu-fd-deny"),
            json={
                "schema_version": 1,
                "expected_revision": 0,
                "location_id": str(rest_env.branch_a),
                "code": "DENY_FD",
                "name": "Nope",
                "category": "Starters",
                "kitchen_station": "cold",
                "price_minor": 500,
                "currency": "USD",
            },
        )
    ).status_code == 403

    # Branch B manager cannot see or mutate Branch A menu item
    assert (
        await rest_env.client.get(
            rest_env.url(f"/menu-items/{item_a}"),
            headers=rest_env.headers(rest_env.branch_b_mgr),
        )
    ).status_code == 404
    assert (
        await rest_env.client.put(
            rest_env.url(f"/menu-items/{uuid7()}"),
            headers=rest_env.headers(rest_env.branch_b_mgr, key="rest-menu-b-write-a"),
            json={
                "schema_version": 1,
                "expected_revision": 0,
                "location_id": str(rest_env.branch_a),
                "code": "CROSS_B",
                "name": "Cross Branch",
                "category": "Starters",
                "kitchen_station": "cold",
                "price_minor": 500,
                "currency": "USD",
            },
        )
    ).status_code == 403

    # Company-wide owner sees Branch A item
    assert (
        await rest_env.client.get(
            rest_env.url(f"/menu-items/{item_a}"),
            headers=rest_env.headers(rest_env.owner),
        )
    ).status_code == 200

    # Cross-company delegate is denied (restaurant permissions are not delegable)
    assert (
        await rest_env.client.get(
            rest_env.url("/menu-items"),
            headers=rest_env.headers(rest_env.delegate_b),
        )
    ).status_code == 403
