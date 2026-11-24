"""Integration tests for SUPPLY-01 Slice 2 (0139): Manufacturing BOMs, work orders,
component lot issues (STOCK-01 write_off), unused material returns (STOCK-01 return),
quality control, and finished-goods lot output (STOCK-01 receipt) with cost conservation.
"""

from uuid import uuid7

import pytest

from tests.integration.test_supply_wms import (
    SupplyEnv,
    client,
    enable_supply_for_test,
    idp,
    sup_env,
)

pytestmark = pytest.mark.anyio
__all__ = ["client", "enable_supply_for_test", "idp", "sup_env"]


async def test_manufacturing_work_order_preserves_lots_movements_and_cost(
    sup_env: SupplyEnv,
) -> None:
    h = sup_env.headers(sup_env.owner)
    biz = f"/v1/businesses/{sup_env.tenant}"

    # 1. Create finished-goods stock item (ASSY_VALVE)
    fg_item_id = uuid7()
    assert (
        await sup_env.client.put(
            f"{biz}/inventory/items/{fg_item_id}",
            headers=sup_env.headers(sup_env.owner, key=f"mfg-fg-it-{uuid7()}"),
            json={
                "schema_version": 1,
                "expected_revision": 0,
                "code": "ASSY_VALVE",
                "name": "Assembled Industrial Valve",
                "unit": "pcs",
                "quantity_scale": 0,
                "archived": False,
            },
        )
    ).status_code == 200

    # 2. Register company owner + 3PL bailor owner + warehouse bins
    co_owner_id, bailor_id, bin_comp_id, bin_fg_id, bin_3pl_id = (
        uuid7(),
        uuid7(),
        uuid7(),
        uuid7(),
        uuid7(),
    )
    assert (
        await sup_env.client.put(
            sup_env.url(f"/owners/{co_owner_id}"),
            headers=sup_env.headers(sup_env.owner, key=f"mfg-own-co-{uuid7()}"),
            json={
                "schema_version": 1,
                "expected_revision": 0,
                "location_id": str(sup_env.home),
                "code": "MFG_CO",
                "display_name": "Company Manufacturing Owner",
                "owner_kind": "company_entity",
                "legal_entity_id": str(sup_env.entity_id),
            },
        )
    ).status_code == 200
    assert (
        await sup_env.client.put(
            sup_env.url(f"/owners/{bailor_id}"),
            headers=sup_env.headers(sup_env.owner, key=f"mfg-own-3pl-{uuid7()}"),
            json={
                "schema_version": 1,
                "expected_revision": 0,
                "location_id": str(sup_env.home),
                "code": "MFG_3PL",
                "display_name": "3PL Bailor Alpha",
                "owner_kind": "counterparty_3pl",
                "counterparty_id": str(sup_env.bailor_a_cp_id),
            },
        )
    ).status_code == 200

    for bid, zc, bc, bkind, ded in (
        (bin_comp_id, "ZONE_M", "BIN_COMP_01", "storage", co_owner_id),
        (bin_fg_id, "ZONE_FG", "BIN_FG_01", "production", co_owner_id),
        (bin_3pl_id, "ZONE_3PL", "BIN_3PL_01", "storage", bailor_id),
    ):
        assert (
            await sup_env.client.put(
                sup_env.url(f"/bins/{bid}"),
                headers=sup_env.headers(sup_env.owner, key=f"mfg-bin-{bid}"),
                json={
                    "schema_version": 1,
                    "expected_revision": 0,
                    "location_id": str(sup_env.home),
                    "place_id": str(sup_env.place_main_id),
                    "zone_code": zc,
                    "bin_code": bc,
                    "bin_kind": bkind,
                    "dedicated_owner_id": str(ded),
                },
            )
        ).status_code == 200

    # 3. Receive 10 component units @ $50.00 each ($500.00 total) for company, and 5 units for
    # 3PL bailor
    comp_lot_id, bailor_lot_id = uuid7(), uuid7()
    for lid, oid, lcode, cost in (
        (comp_lot_id, co_owner_id, "LOT-COMP-01", 5000),
        (bailor_lot_id, bailor_id, "LOT-3PL-COMP", 0),
    ):
        assert (
            await sup_env.client.put(
                sup_env.url(f"/lots/{lid}"),
                headers=sup_env.headers(sup_env.owner, key=f"mfg-lot-{lid}"),
                json={
                    "schema_version": 1,
                    "expected_revision": 0,
                    "location_id": str(sup_env.home),
                    "goods_owner_id": str(oid),
                    "item_id": str(sup_env.item_id),
                    "lot_code": lcode,
                    "unit_cost_minor": cost,
                },
            )
        ).status_code == 200

    assert (
        await sup_env.client.post(
            sup_env.url("/movements/inbound"),
            headers=sup_env.headers(sup_env.owner, key=f"mfg-in-co-{uuid7()}"),
            json={
                "schema_version": 1,
                "location_id": str(sup_env.home),
                "bin_id": str(bin_comp_id),
                "goods_owner_id": str(co_owner_id),
                "item_id": str(sup_env.item_id),
                "lot_id": str(comp_lot_id),
                "quantity": 10,
                "auto_stock_receipt_date": "2026-10-01",
                "auto_stock_receipt_reason": "purchase",
                "auto_stock_receipt_amount": "500.00",
            },
        )
    ).status_code == 200
    assert (
        await sup_env.client.post(
            sup_env.url("/movements/inbound"),
            headers=sup_env.headers(sup_env.owner, key=f"mfg-in-3pl-{uuid7()}"),
            json={
                "schema_version": 1,
                "location_id": str(sup_env.home),
                "bin_id": str(bin_3pl_id),
                "goods_owner_id": str(bailor_id),
                "item_id": str(sup_env.item_id),
                "lot_id": str(bailor_lot_id),
                "quantity": 5,
            },
        )
    ).status_code == 200

    # 4. Create BOM for ASSY_VALVE (standard labor = $40.00 / 4000, overhead = $10.00 / 1000)
    bom_id = uuid7()
    bom_res = await sup_env.client.put(
        sup_env.url(f"/boms/{bom_id}"),
        headers=sup_env.headers(sup_env.owner, key=f"mfg-bom-{uuid7()}"),
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "location_id": str(sup_env.home),
            "code": "BOM_ASSY_01",
            "title": "Industrial Valve Assembly Spec",
            "output_item_id": str(fg_item_id),
            "batch_output_quantity": 5,
            "standard_labor_minor": 4000,
            "standard_overhead_minor": 1000,
            "components": [
                {
                    "component_item_id": str(sup_env.item_id),
                    "quantity_per_batch": 5,
                    "scrap_bps": 0,
                }
            ],
        },
    )
    assert bom_res.status_code == 200, bom_res.text

    # 5. 3PL bailor cannot own a manufacturing work order (409 SUPPLY_OWNER_MISMATCH)
    bad_wo = await sup_env.client.put(
        sup_env.url(f"/work-orders/{uuid7()}"),
        headers=sup_env.headers(sup_env.owner, key=f"mfg-wo-bad-{uuid7()}"),
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "location_id": str(sup_env.home),
            "code": "WO_BAD_3PL",
            "goods_owner_id": str(bailor_id),
            "bom_id": str(bom_id),
            "place_id": str(sup_env.place_main_id),
            "planned_quantity": 5,
        },
    )
    assert bad_wo.status_code == 409
    assert bad_wo.json()["error"]["code"] == "SUPPLY_OWNER_MISMATCH"

    # 6. Create company Work Order for 5 finished units
    wo_id = uuid7()
    wo_res = await sup_env.client.put(
        sup_env.url(f"/work-orders/{wo_id}"),
        headers=sup_env.headers(sup_env.owner, key=f"mfg-wo-{uuid7()}"),
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "location_id": str(sup_env.home),
            "code": "WO_2026_001",
            "goods_owner_id": str(co_owner_id),
            "bom_id": str(bom_id),
            "place_id": str(sup_env.place_main_id),
            "planned_quantity": 5,
        },
    )
    assert wo_res.status_code == 200, wo_res.text

    # 7. Work order CANNOT consume 3PL bailor's component lot («Товар другого собственника
    # недоступен»)
    steal_iss = await sup_env.client.post(
        sup_env.url(f"/work-orders/{wo_id}/issues"),
        headers=sup_env.headers(sup_env.owner, key=f"mfg-iss-steal-{uuid7()}"),
        json={
            "schema_version": 1,
            "bin_id": str(bin_3pl_id),
            "component_item_id": str(sup_env.item_id),
            "lot_id": str(bailor_lot_id),
            "quantity": 5,
            "document_date": "2026-10-02",
        },
    )
    assert steal_iss.status_code == 409
    assert steal_iss.json()["error"]["code"] == "SUPPLY_OWNER_MISMATCH"

    # 8. Issue 6 company component units ($300.00 = 30000 minor) -> posts real STOCK-01 write_off
    iss_res = await sup_env.client.post(
        sup_env.url(f"/work-orders/{wo_id}/issues"),
        headers=sup_env.headers(sup_env.owner, key=f"mfg-iss-ok-{uuid7()}"),
        json={
            "schema_version": 1,
            "bin_id": str(bin_comp_id),
            "component_item_id": str(sup_env.item_id),
            "lot_id": str(comp_lot_id),
            "quantity": 6,
            "document_date": "2026-10-02",
        },
    )
    assert iss_res.status_code == 200, iss_res.text
    iss_data = iss_res.json()
    assert iss_data["cost_minor"] == 30_000
    issue_id = iss_data["issue_id"]

    # 9. Return 1 unused component unit ($50.00 = 5000 minor) -> posts real STOCK-01 return
    # ('unused')
    # and restores comp_lot_id balance from 4 -> 5!
    ret_res = await sup_env.client.post(
        sup_env.url(f"/work-orders/{wo_id}/returns"),
        headers=sup_env.headers(sup_env.owner, key=f"mfg-ret-ok-{uuid7()}"),
        json={
            "schema_version": 1,
            "issue_id": issue_id,
            "bin_id": str(bin_comp_id),
            "quantity": 1,
            "document_date": "2026-10-02",
        },
    )
    assert ret_res.status_code == 200, ret_res.text
    assert ret_res.json()["cost_returned_minor"] == 5_000

    # 10. Record QC pass for 5 finished units and complete finished-goods output:
    # Net material cost = $300 - $50 = $250 (25000) + Labor $40 (4000) + Overhead $10 (1000) =
    # $300.00 (30000 minor, $60/unit)
    qc_res = await sup_env.client.post(
        sup_env.url(f"/work-orders/{wo_id}/qc"),
        headers=sup_env.headers(sup_env.owner, key=f"mfg-qc-{uuid7()}"),
        json={
            "schema_version": 1,
            "passed_quantity": 5,
            "scrap_quantity": 0,
            "notes": "ISO 9001 pressure test passed",
        },
    )
    assert qc_res.status_code == 200, qc_res.text

    out_res = await sup_env.client.post(
        sup_env.url(f"/work-orders/{wo_id}/output"),
        headers=sup_env.headers(sup_env.owner, key=f"mfg-out-{uuid7()}"),
        json={
            "schema_version": 1,
            "bin_id": str(bin_fg_id),
            "output_lot_code": "LOT-FG-2026-01",
            "manufactured_on": "2026-10-03",
            "expires_on": "2028-10-03",
        },
    )
    assert out_res.status_code == 200, out_res.text
    out_data = out_res.json()
    assert out_data["quantity"] == 5
    assert out_data["material_cost_minor"] == 25_000
    assert out_data["labor_cost_minor"] == 4_000
    assert out_data["overhead_cost_minor"] == 1_000
    assert out_data["total_cost_minor"] == 30_000
    assert out_data["unit_cost_minor"] == 6_000

    # Verify both WMS lot balances AND STOCK-01 moving-average costs!
    lot_bals = (await sup_env.client.get(sup_env.url("/lot-balances"), headers=h)).json()["items"]
    by_lot = {b["lot_id"]: b["quantity"] for b in lot_bals}
    assert by_lot[str(comp_lot_id)] == 5  # 10 received - 6 issued + 1 returned = 5
    assert by_lot[out_data["output_lot_id"]] == 5  # 5 finished units produced
    assert by_lot[str(bailor_lot_id)] == 5  # 3PL bailor lot completely untouched

    stk_costs = (await sup_env.client.get(f"{biz}/inventory/costs", headers=h)).json()["items"]
    cost_by_item = {c["item_id"]: (c["quantity"], c["value"]) for c in stk_costs}
    assert cost_by_item[str(sup_env.item_id)] == ("5", "250.00")
    assert cost_by_item[str(fg_item_id)] == ("5", "300.00")
