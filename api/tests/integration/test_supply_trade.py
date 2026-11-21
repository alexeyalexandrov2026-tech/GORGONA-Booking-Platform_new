"""Integration tests for SUPPLY-01 Slice 3 (0140): channel & contract price lists,
retail/wholesale & 3PL fulfillment orders, owner-isolated lot/serial shipments
(STOCK-01 COGS write_off + FIN-03 receivable invoice), and customer returns
(STOCK-01 return + FIN-03 credit note draft).
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


async def test_trade_and_3pl_orders_preserve_owner_isolation_lots_movements_and_cost(
    sup_env: SupplyEnv,
) -> None:
    h = sup_env.headers(sup_env.owner)
    biz = f"/v1/businesses/{sup_env.tenant}"

    accts = {
        a["code"]: a["account_id"]
        for a in (
            await sup_env.client.get(
                f"{biz}/ledger/books/{sup_env.book_id}/accounts?limit=100", headers=h
            )
        ).json()["items"]
    }
    ar_acct_id = accts["1200"]
    rev_acct_id = accts["4000"]

    # 1. Register company owner, 3PL bailor owner, bins, lots, and inbound receipts
    co_owner_id, bailor_id, bin_co_id, bin_3pl_id, co_lot_id, bailor_lot_id = (
        uuid7(),
        uuid7(),
        uuid7(),
        uuid7(),
        uuid7(),
        uuid7(),
    )
    assert (
        await sup_env.client.put(
            sup_env.url(f"/owners/{co_owner_id}"),
            headers=sup_env.headers(sup_env.owner, key=f"trd-own-co-{uuid7()}"),
            json={
                "schema_version": 1,
                "expected_revision": 0,
                "location_id": str(sup_env.home),
                "code": "TRD_CO",
                "display_name": "Company Trade Owner",
                "owner_kind": "company_entity",
                "legal_entity_id": str(sup_env.entity_id),
            },
        )
    ).status_code == 200
    assert (
        await sup_env.client.put(
            sup_env.url(f"/owners/{bailor_id}"),
            headers=sup_env.headers(sup_env.owner, key=f"trd-own-3pl-{uuid7()}"),
            json={
                "schema_version": 1,
                "expected_revision": 0,
                "location_id": str(sup_env.home),
                "code": "TRD_3PL",
                "display_name": "3PL Bailor Alpha",
                "owner_kind": "counterparty_3pl",
                "counterparty_id": str(sup_env.bailor_a_cp_id),
            },
        )
    ).status_code == 200

    for bid, zc, bc, ded in (
        (bin_co_id, "ZONE_TRD", "BIN_TRD_CO", co_owner_id),
        (bin_3pl_id, "ZONE_3PL", "BIN_TRD_3PL", bailor_id),
    ):
        assert (
            await sup_env.client.put(
                sup_env.url(f"/bins/{bid}"),
                headers=sup_env.headers(sup_env.owner, key=f"trd-bin-{bid}"),
                json={
                    "schema_version": 1,
                    "expected_revision": 0,
                    "location_id": str(sup_env.home),
                    "place_id": str(sup_env.place_main_id),
                    "zone_code": zc,
                    "bin_code": bc,
                    "bin_kind": "storage",
                    "dedicated_owner_id": str(ded),
                },
            )
        ).status_code == 200

    for lid, oid, lcode, cost in (
        (co_lot_id, co_owner_id, "LOT-TRD-CO-01", 5000),
        (bailor_lot_id, bailor_id, "LOT-TRD-3PL-01", 0),
    ):
        assert (
            await sup_env.client.put(
                sup_env.url(f"/lots/{lid}"),
                headers=sup_env.headers(sup_env.owner, key=f"trd-lot-{lid}"),
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

    # Inbound 10 company units @ $50.00 ($500.00 total) with 4 serials + 6 unserialized in lot,
    # wait: inbound serial_codes requires len(serial_codes) == quantity when provided, so let's
    # receive 4 serialized units + 6 additional units in two inbound movements!
    assert (
        await sup_env.client.post(
            sup_env.url("/movements/inbound"),
            headers=sup_env.headers(sup_env.owner, key=f"trd-in-co1-{uuid7()}"),
            json={
                "schema_version": 1,
                "location_id": str(sup_env.home),
                "bin_id": str(bin_co_id),
                "goods_owner_id": str(co_owner_id),
                "item_id": str(sup_env.item_id),
                "lot_id": str(co_lot_id),
                "quantity": 4,
                "serial_codes": ["SN-TRD-01", "SN-TRD-02", "SN-TRD-03", "SN-TRD-04"],
                "auto_stock_receipt_date": "2026-10-01",
                "auto_stock_receipt_reason": "purchase",
                "auto_stock_receipt_amount": "200.00",
            },
        )
    ).status_code == 200
    assert (
        await sup_env.client.post(
            sup_env.url("/movements/inbound"),
            headers=sup_env.headers(sup_env.owner, key=f"trd-in-co2-{uuid7()}"),
            json={
                "schema_version": 1,
                "location_id": str(sup_env.home),
                "bin_id": str(bin_co_id),
                "goods_owner_id": str(co_owner_id),
                "item_id": str(sup_env.item_id),
                "lot_id": str(co_lot_id),
                "quantity": 6,
                "auto_stock_receipt_date": "2026-10-01",
                "auto_stock_receipt_reason": "purchase",
                "auto_stock_receipt_amount": "300.00",
            },
        )
    ).status_code == 200
    assert (
        await sup_env.client.post(
            sup_env.url("/movements/inbound"),
            headers=sup_env.headers(sup_env.owner, key=f"trd-in-3pl-{uuid7()}"),
            json={
                "schema_version": 1,
                "location_id": str(sup_env.home),
                "bin_id": str(bin_3pl_id),
                "goods_owner_id": str(bailor_id),
                "item_id": str(sup_env.item_id),
                "lot_id": str(bailor_lot_id),
                "quantity": 3,
            },
        )
    ).status_code == 200

    # 2. Create tiered wholesale price list (1+ @ $90.00, 5+ @ $80.00)
    pl_id = uuid7()
    r_pl = await sup_env.client.put(
        sup_env.url(f"/price-lists/{pl_id}"),
        headers=sup_env.headers(sup_env.owner, key=f"trd-pl-{uuid7()}"),
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "location_id": str(sup_env.home),
            "code": "PL_WHOLESALE_2026",
            "title": "Wholesale Tiered Price List 2026",
            "channel": "wholesale",
            "currency": "USD",
            "items": [
                {
                    "item_id": str(sup_env.item_id),
                    "min_quantity": 1,
                    "unit_price_minor": 9000,
                },
                {
                    "item_id": str(sup_env.item_id),
                    "min_quantity": 5,
                    "unit_price_minor": 8000,
                },
            ],
        },
    )
    assert r_pl.status_code == 200, r_pl.text

    # 3. Negative proof: wholesale_sale order cannot be created for a 3PL bailor owner
    bad_ord = await sup_env.client.put(
        sup_env.url(f"/orders/{uuid7()}"),
        headers=sup_env.headers(sup_env.owner, key=f"trd-ord-bad-{uuid7()}"),
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "location_id": str(sup_env.home),
            "code": "ORD_BAD_OWNER",
            "order_kind": "wholesale_sale",
            "goods_owner_id": str(bailor_id),
            "customer_counterparty_id": str(sup_env.bailor_b_cp_id),
            "price_list_id": str(pl_id),
            "currency": "USD",
            "book_id": str(sup_env.book_id),
            "control_account_id": ar_acct_id,
            "revenue_account_id": rev_acct_id,
            "lines": [{"item_id": str(sup_env.item_id), "ordered_quantity": 5}],
        },
    )
    assert bad_ord.status_code == 409
    assert bad_ord.json()["error"]["code"] == "SUPPLY_OWNER_MISMATCH"

    # 4. Create company wholesale order (6 units -> resolves 5+ tier @ $80.00 = 48000 minor)
    co_order_id = uuid7()
    r_ord = await sup_env.client.put(
        sup_env.url(f"/orders/{co_order_id}"),
        headers=sup_env.headers(sup_env.owner, key=f"trd-ord-co-{uuid7()}"),
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "location_id": str(sup_env.home),
            "code": "ORD_WHOLESALE_01",
            "order_kind": "wholesale_sale",
            "goods_owner_id": str(co_owner_id),
            "customer_counterparty_id": str(sup_env.bailor_b_cp_id),
            "price_list_id": str(pl_id),
            "currency": "USD",
            "book_id": str(sup_env.book_id),
            "control_account_id": ar_acct_id,
            "revenue_account_id": rev_acct_id,
            "lines": [{"item_id": str(sup_env.item_id), "ordered_quantity": 6}],
        },
    )
    assert r_ord.status_code == 200, r_ord.text
    co_order = r_ord.json()
    assert co_order["total_ordered_minor"] == 48000
    co_line_id = co_order["lines"][0]["order_line_id"]
    assert co_order["lines"][0]["unit_price_minor"] == 8000

    # 5. Negative proof: cannot ship company order using 3PL bailor's lot or dedicated bin
    bad_ship = await sup_env.client.post(
        sup_env.url(f"/orders/{co_order_id}/shipments"),
        headers=sup_env.headers(sup_env.owner, key=f"trd-shp-bad-{uuid7()}"),
        json={
            "schema_version": 1,
            "order_line_id": co_line_id,
            "bin_id": str(bin_3pl_id),
            "lot_id": str(bailor_lot_id),
            "quantity": 2,
            "document_date": "2026-10-05",
        },
    )
    assert bad_ship.status_code == 409
    assert bad_ship.json()["error"]["code"] == "SUPPLY_OWNER_MISMATCH"

    # 6. Ship 4 serialized units on company wholesale order:
    # posts STOCK-01 COGS write_off ($200.00 = 20000) + FIN-03 receivable invoice ($320.00 = 32000)
    r_ship = await sup_env.client.post(
        sup_env.url(f"/orders/{co_order_id}/shipments"),
        headers=sup_env.headers(sup_env.owner, key=f"trd-shp-co-{uuid7()}"),
        json={
            "schema_version": 1,
            "order_line_id": co_line_id,
            "bin_id": str(bin_co_id),
            "lot_id": str(co_lot_id),
            "quantity": 4,
            "serial_codes": ["SN-TRD-01", "SN-TRD-02", "SN-TRD-03", "SN-TRD-04"],
            "document_date": "2026-10-05",
            "invoice_number": "INV-TRD-001",
        },
    )
    assert r_ship.status_code == 200, r_ship.text
    shipment = r_ship.json()
    assert shipment["revenue_minor"] == 32000
    assert shipment["cogs_minor"] == 20000
    assert shipment["stock_document_id"] is not None
    assert shipment["invoice_document_id"] is not None
    assert shipment["obligation_id"] is not None

    # Verify STOCK-01 valuation balance dropped from 10 ($500.00) to 6 ($300.00)
    stk_after_ship = {
        c["item_id"]: (c["quantity"], c["value"])
        for c in (await sup_env.client.get(f"{biz}/inventory/costs", headers=h)).json()["items"]
    }
    assert stk_after_ship[str(sup_env.item_id)] == ("6", "300.00")

    # Verify FIN-03 invoice is issued for $320.00
    inv_res = await sup_env.client.get(
        f"{biz}/financial-documents/books/{sup_env.book_id}/invoices/{shipment['invoice_document_id']}",
        headers=h,
    )
    assert inv_res.status_code == 200, inv_res.text
    assert inv_res.json()["state"] == "issued"
    assert inv_res.json()["total"] == "320.00"

    # 7. Customer returns 1 serialized unit (SN-TRD-04)
    # -> restores lot balance (6 -> 7), serial state ('in_stock'), STOCK-01 return ($50.00 COGS),
    # and saves FIN-03 credit note draft ($80.00)
    r_ret = await sup_env.client.post(
        sup_env.url(f"/orders/{co_order_id}/returns"),
        headers=sup_env.headers(sup_env.owner, key=f"trd-ret-co-{uuid7()}"),
        json={
            "schema_version": 1,
            "shipment_id": shipment["shipment_id"],
            "bin_id": str(bin_co_id),
            "quantity": 1,
            "serial_codes": ["SN-TRD-04"],
            "document_date": "2026-10-06",
            "reason": "Customer over-ordered 1 unit",
            "credit_note_number": "CN-TRD-001",
        },
    )
    assert r_ret.status_code == 200, r_ret.text
    ret_view = r_ret.json()
    assert ret_view["refund_minor"] == 8000
    assert ret_view["cogs_restored_minor"] == 5000
    assert ret_view["stock_return_document_id"] is not None
    assert ret_view["credit_note_document_id"] is not None

    # Verify STOCK-01 valuation balance restored to 7 ($350.00)
    stk_after_ret = {
        c["item_id"]: (c["quantity"], c["value"])
        for c in (await sup_env.client.get(f"{biz}/inventory/costs", headers=h)).json()["items"]
    }
    assert stk_after_ret[str(sup_env.item_id)] == ("7", "350.00")

    # Verify serial SN-TRD-04 is back in_stock in bin_co_id while SN-TRD-01..03 remain shipped
    serials = {
        s["serial_code"]: s
        for s in (
            await sup_env.client.get(
                sup_env.url(f"/serials?goods_owner_id={co_owner_id}"), headers=h
            )
        ).json()["items"]
    }
    assert serials["SN-TRD-04"]["state"] == "in_stock"
    assert serials["SN-TRD-04"]["bin_id"] == str(bin_co_id)
    assert serials["SN-TRD-01"]["state"] == "shipped"

    # 8. 3PL fulfillment order + shipment + return stay isolated from company STOCK-01 balance
    tpl_order_id = uuid7()
    r_tpl = await sup_env.client.put(
        sup_env.url(f"/orders/{tpl_order_id}"),
        headers=sup_env.headers(sup_env.owner, key=f"trd-ord-3pl-{uuid7()}"),
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "location_id": str(sup_env.home),
            "code": "ORD_3PL_01",
            "order_kind": "3pl_fulfillment",
            "goods_owner_id": str(bailor_id),
            "customer_counterparty_id": str(sup_env.bailor_b_cp_id),
            "currency": "USD",
            "lines": [
                {
                    "item_id": str(sup_env.item_id),
                    "ordered_quantity": 2,
                    "unit_price_minor": 0,
                }
            ],
        },
    )
    assert r_tpl.status_code == 200, r_tpl.text
    tpl_line_id = r_tpl.json()["lines"][0]["order_line_id"]

    # Negative proof: cannot ship 3PL order using company lot
    bad_tpl_ship = await sup_env.client.post(
        sup_env.url(f"/orders/{tpl_order_id}/shipments"),
        headers=sup_env.headers(sup_env.owner, key=f"trd-shp-3pl-bad-{uuid7()}"),
        json={
            "schema_version": 1,
            "order_line_id": tpl_line_id,
            "bin_id": str(bin_co_id),
            "lot_id": str(co_lot_id),
            "quantity": 1,
            "document_date": "2026-10-07",
        },
    )
    assert bad_tpl_ship.status_code == 409
    assert bad_tpl_ship.json()["error"]["code"] == "SUPPLY_OWNER_MISMATCH"

    # Valid 3PL shipment & return
    r_tpl_ship = await sup_env.client.post(
        sup_env.url(f"/orders/{tpl_order_id}/shipments"),
        headers=sup_env.headers(sup_env.owner, key=f"trd-shp-3pl-{uuid7()}"),
        json={
            "schema_version": 1,
            "order_line_id": tpl_line_id,
            "bin_id": str(bin_3pl_id),
            "lot_id": str(bailor_lot_id),
            "quantity": 2,
            "document_date": "2026-10-07",
        },
    )
    assert r_tpl_ship.status_code == 200, r_tpl_ship.text
    tpl_shp = r_tpl_ship.json()
    assert tpl_shp["stock_document_id"] is None

    r_tpl_ret = await sup_env.client.post(
        sup_env.url(f"/orders/{tpl_order_id}/returns"),
        headers=sup_env.headers(sup_env.owner, key=f"trd-ret-3pl-{uuid7()}"),
        json={
            "schema_version": 1,
            "shipment_id": tpl_shp["shipment_id"],
            "bin_id": str(bin_3pl_id),
            "quantity": 1,
            "document_date": "2026-10-08",
            "reason": "3PL customer return to bailor stock",
        },
    )
    assert r_tpl_ret.status_code == 200, r_tpl_ret.text

    # Branch B isolation check
    hb = sup_env.headers(sup_env.branch_b_mgr)
    assert (
        await sup_env.client.get(sup_env.url(f"/orders/{co_order_id}"), headers=hb)
    ).status_code == 404
