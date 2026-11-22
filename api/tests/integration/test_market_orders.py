"""Integration tests for MARKET-01 Slice 2 (0142): multi-seller basket split into isolated
single-seller orders & FIN-03 receivable invoices, negative proof against cross-seller book
commingling, customer refund FIN-03 credit notes, and zero-commission operator commercial fees.
"""

from uuid import uuid7

import pytest

from tests.integration.test_market_storefronts import (
    MarketEnv,
    client,
    enable_storefronts_for_test,
    idp,
    mkt_env,
)

pytestmark = pytest.mark.anyio
__all__ = ["client", "enable_storefronts_for_test", "idp", "mkt_env"]


async def test_multi_seller_basket_splits_into_single_seller_orders_and_invoices(
    mkt_env: MarketEnv,
) -> None:
    h = mkt_env.headers(mkt_env.owner)
    biz = f"/v1/businesses/{mkt_env.tenant}"

    accts_a = {
        a["code"]: a["account_id"]
        for a in (
            await mkt_env.client.get(
                f"{biz}/ledger/books/{mkt_env.book_a_id}/accounts?limit=100", headers=h
            )
        ).json()["items"]
    }
    accts_b = {
        a["code"]: a["account_id"]
        for a in (
            await mkt_env.client.get(
                f"{biz}/ledger/books/{mkt_env.book_b_id}/accounts?limit=100", headers=h
            )
        ).json()["items"]
    }

    # 1. Create two independent seller storefronts (Seller A + Seller B)
    sf_a_id, sf_b_id, lst_a_id, lst_b_id, mp_id = uuid7(), uuid7(), uuid7(), uuid7(), uuid7()
    for sfid, eid, slug, name in (
        (sf_a_id, mkt_env.entity_a_id, "seller-alpha-shop", "Seller Alpha Shop"),
        (sf_b_id, mkt_env.entity_b_id, "seller-beta-shop", "Seller Beta Shop"),
    ):
        assert (
            await mkt_env.client.put(
                mkt_env.url(f"/storefronts/{sfid}"),
                headers=mkt_env.headers(mkt_env.owner, key=f"mo-sf-{sfid}"),
                json={
                    "schema_version": 1,
                    "expected_revision": 0,
                    "location_id": str(mkt_env.home),
                    "legal_entity_id": str(eid),
                    "slug": slug,
                    "display_name": name,
                    "currency": "USD",
                    "published_fields": ["title", "price", "currency", "availability"],
                    "is_published": True,
                },
            )
        ).status_code == 200

    for lid, sfid, sku, title, price in (
        (lst_a_id, sf_a_id, "ALPHA-01", "Alpha Motor", 20000),
        (lst_b_id, sf_b_id, "BETA-01", "Beta Sensor", 15000),
    ):
        assert (
            await mkt_env.client.put(
                mkt_env.url(f"/listings/{lid}"),
                headers=mkt_env.headers(mkt_env.owner, key=f"mo-lst-{lid}"),
                json={
                    "schema_version": 1,
                    "expected_revision": 0,
                    "location_id": str(mkt_env.home),
                    "storefront_id": str(sfid),
                    "sku": sku,
                    "title": title,
                    "category": "equipment",
                    "currency": "USD",
                    "price_minor": price,
                    "available_quantity": 10,
                    "published_fields": ["title", "price", "currency", "availability"],
                    "moderation_status": "published",
                },
            )
        ).status_code == 200

    assert (
        await mkt_env.client.put(
            mkt_env.url(f"/marketplaces/{mp_id}"),
            headers=mkt_env.headers(mkt_env.owner, key=f"mo-mp-{uuid7()}"),
            json={
                "schema_version": 1,
                "expected_revision": 0,
                "location_id": str(mkt_env.home),
                "slug": "industrial-hub",
                "title": "Industrial Hub Marketplace",
                "operator_fee_bps": 300,
            },
        )
    ).status_code == 200

    # 2. Negative proof: cannot commingle Seller B's storefront into Seller A's ledger book!
    bad_checkout = await mkt_env.client.post(
        mkt_env.url("/baskets/checkout"),
        headers=mkt_env.headers(mkt_env.owner, key=f"mo-bad-{uuid7()}"),
        json={
            "schema_version": 1,
            "location_id": str(mkt_env.home),
            "customer_counterparty_id": str(mkt_env.customer_cp_id),
            "marketplace_id": str(mp_id),
            "currency": "USD",
            "order_date": "2026-10-10",
            "items": [
                {"listing_id": str(lst_a_id), "quantity": 1},
                {"listing_id": str(lst_b_id), "quantity": 1},
            ],
            "seller_configs": [
                {
                    "storefront_id": str(sf_a_id),
                    "book_id": str(mkt_env.book_a_id),
                    "control_account_id": accts_a["1200"],
                    "revenue_account_id": accts_a["4000"],
                },
                {
                    "storefront_id": str(sf_b_id),
                    "book_id": str(mkt_env.book_a_id),  # WRONG: Seller A's book!
                    "control_account_id": accts_a["1200"],
                    "revenue_account_id": accts_a["4000"],
                },
            ],
        },
    )
    assert bad_checkout.status_code == 422

    # 3. Valid multi-seller checkout splits into 2 independent single-seller orders & invoices
    ok_res = await mkt_env.client.post(
        mkt_env.url("/baskets/checkout"),
        headers=mkt_env.headers(mkt_env.owner, key=f"mo-ok-{uuid7()}"),
        json={
            "schema_version": 1,
            "location_id": str(mkt_env.home),
            "customer_counterparty_id": str(mkt_env.customer_cp_id),
            "marketplace_id": str(mp_id),
            "currency": "USD",
            "order_date": "2026-10-10",
            "items": [
                {"listing_id": str(lst_a_id), "quantity": 2},  # $400.00 -> Seller A
                {"listing_id": str(lst_b_id), "quantity": 1},  # $150.00 -> Seller B
            ],
            "seller_configs": [
                {
                    "storefront_id": str(sf_a_id),
                    "book_id": str(mkt_env.book_a_id),
                    "control_account_id": accts_a["1200"],
                    "revenue_account_id": accts_a["4000"],
                    "seller_counterparty_id": str(mkt_env.seller_cp_id),
                },
                {
                    "storefront_id": str(sf_b_id),
                    "book_id": str(mkt_env.book_b_id),
                    "control_account_id": accts_b["1200"],
                    "revenue_account_id": accts_b["4000"],
                    "seller_counterparty_id": str(mkt_env.seller_cp_id),
                },
            ],
        },
    )
    assert ok_res.status_code == 200, ok_res.text
    basket = ok_res.json()
    assert basket["split_order_count"] == 2
    assert len(basket["orders"]) == 2

    by_sf = {o["storefront_id"]: o for o in basket["orders"]}
    ord_a = by_sf[str(sf_a_id)]
    ord_b = by_sf[str(sf_b_id)]
    assert ord_a["legal_entity_id"] == str(mkt_env.entity_a_id)
    assert ord_a["book_id"] == str(mkt_env.book_a_id)
    assert ord_a["total_minor"] == 40000
    assert ord_b["legal_entity_id"] == str(mkt_env.entity_b_id)
    assert ord_b["book_id"] == str(mkt_env.book_b_id)
    assert ord_b["total_minor"] == 15000
    assert ord_a["invoice_document_id"] != ord_b["invoice_document_id"]

    # Verify Seller A's FIN-03 invoice is issued for exact $400.00 (no commingled funds!)
    inv_url = (
        f"{biz}/financial-documents/books/{mkt_env.book_a_id}"
        f"/invoices/{ord_a['invoice_document_id']}"
    )
    inv_a = await mkt_env.client.get(inv_url, headers=h)
    assert inv_a.status_code == 200
    assert inv_a.json()["state"] == "issued"
    assert inv_a.json()["total"] == "400.00"

    # Verify separate operator commercial fees recorded with gorgona_commission_minor = 0
    fees = (
        await mkt_env.client.get(mkt_env.url(f"/operator-fees?marketplace_id={mp_id}"), headers=h)
    ).json()["items"]
    assert len(fees) == 2
    assert all(f["gorgona_commission_minor"] == 0 for f in fees)
    assert sorted(f["operator_fee_minor"] for f in fees) == [450, 1200]

    # 4. Partial refund on Seller A's order creates Seller A's FIN-03 credit note draft ($100.00)
    ref_res = await mkt_env.client.post(
        mkt_env.url(f"/orders/{ord_a['order_id']}/refund"),
        headers=mkt_env.headers(mkt_env.owner, key=f"mo-ref-{uuid7()}"),
        json={
            "schema_version": 1,
            "refund_minor": 10000,
            "refund_date": "2026-10-12",
            "reason": "Partial customer refund on Alpha Motor",
        },
    )
    assert ref_res.status_code == 200, ref_res.text
    ref_ord = ref_res.json()
    assert ref_ord["status"] == "partially_refunded"
    assert ref_ord["refunded_minor"] == 10000
    assert ref_ord["credit_note_document_id"] is not None

    # Branch B isolation check
    hb = mkt_env.headers(mkt_env.branch_b_mgr)
    assert (
        await mkt_env.client.get(mkt_env.url(f"/orders/{ord_a['order_id']}"), headers=hb)
    ).status_code == 404
