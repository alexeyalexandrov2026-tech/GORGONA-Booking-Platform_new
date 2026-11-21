"""REST-01 Slice 4: split billing conservation, FIN-03 invoicing and coordinated refunds."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid7

import pytest
from psycopg_pool import AsyncConnectionPool

from tests.integration.test_counterparties import card
from tests.integration.test_delegations import client, idp, owner_a, owner_b
from tests.integration.test_restaurant_checks_and_kitchen import _setup_stock_books_and_place
from tests.integration.test_restaurant_floor_and_tables import RestaurantEnv, rest_env

pytestmark = pytest.mark.anyio
__all__ = ["client", "idp", "owner_a", "owner_b", "rest_env"]

DAY = "2026-10-01"


async def _create_customer(env: RestaurantEnv, code: str, name: str) -> UUID:
    cp_id = uuid7()
    res = await env.client.put(
        f"/v1/businesses/{env.tenant}/counterparties/{cp_id}",
        headers=env.headers(env.owner, key=f"rest-s4-cp-{code}-{uuid7()}"),
        json=card(display_name=name, roles=["customer"]),
    )
    assert res.status_code == 200, res.text
    return cp_id


async def _add_item_and_fire(
    env: RestaurantEnv,
    *,
    code: str,
    name: str,
    price_minor: int,
    station: str = "hot",
) -> UUID:
    mid = uuid7()
    res = await env.client.put(
        env.url(f"/menu-items/{mid}"),
        headers=env.headers(env.branch_a_mgr, key=f"rest-s4-mi-{code}"),
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "location_id": str(env.branch_a),
            "code": code,
            "name": name,
            "category": "Mains",
            "kitchen_station": station,
            "price_minor": price_minor,
            "currency": "USD",
        },
    )
    assert res.status_code == 200, res.text
    return mid


async def test_by_items_split_fin03_invoices_credit_note_and_reconciliation(
    rest_env: RestaurantEnv,
    app_pool: AsyncConnectionPool,
) -> None:
    _entity, book_id, _place, accounts = await _setup_stock_books_and_place(
        rest_env, app_pool, location_id=rest_env.branch_a
    )
    # Create accounts receivable (1200) and restaurant revenue (4000) if not in default chart
    ar_id = accounts.get("1200")
    if ar_id is None:
        ar_id = uuid7()
        r = await rest_env.client.put(
            f"/v1/businesses/{rest_env.tenant}/ledger/books/{book_id}/accounts/{ar_id}",
            headers=rest_env.headers(rest_env.owner, key=f"rest-s4-ar-{uuid7()}"),
            json={
                "schema_version": 1,
                "expected_revision": 0,
                "code": "1200",
                "type": "asset",
                "name": "Accounts Receivable",
                "archived": False,
            },
        )
        assert r.status_code == 200, r.text
    rev_id = accounts.get("4000")
    if rev_id is None:
        rev_id = uuid7()
        r = await rest_env.client.put(
            f"/v1/businesses/{rest_env.tenant}/ledger/books/{book_id}/accounts/{rev_id}",
            headers=rest_env.headers(rest_env.owner, key=f"rest-s4-rev-{uuid7()}"),
            json={
                "schema_version": 1,
                "expected_revision": 0,
                "code": "4000",
                "type": "income",
                "name": "Restaurant Revenue",
                "archived": False,
            },
        )
        assert r.status_code == 200, r.text

    guest_1 = await _create_customer(rest_env, "G1", "Guest One")
    guest_2 = await _create_customer(rest_env, "G2", "Guest Two")

    steak = await _add_item_and_fire(rest_env, code="STEAK_S4", name="Ribeye", price_minor=3200)
    wine = await _add_item_and_fire(
        rest_env, code="WINE_S4", name="Pinot Noir", price_minor=1400, station="bar"
    )

    # Open check and add 2 lines: 3200 + 1400 = 4600
    chk = (
        await rest_env.client.post(
            rest_env.url("/checks"),
            headers=rest_env.headers(rest_env.front_desk_a, key="rest-s4-chk-1"),
            json={
                "schema_version": 1,
                "location_id": str(rest_env.branch_a),
                "service_mode": "dine_in",
                "currency": "USD",
            },
        )
    ).json()
    check_id = chk["check_id"]

    l1_res = await rest_env.client.post(
        rest_env.url(f"/checks/{check_id}/lines"),
        headers=rest_env.headers(rest_env.front_desk_a, key="rest-s4-l1"),
        json={"schema_version": 1, "menu_item_id": str(steak), "quantity": 1},
    )
    assert l1_res.status_code == 200
    line_1 = l1_res.json()["lines"][0]["line_id"]

    l2_res = await rest_env.client.post(
        rest_env.url(f"/checks/{check_id}/lines"),
        headers=rest_env.headers(rest_env.front_desk_a, key="rest-s4-l2"),
        json={"schema_version": 1, "menu_item_id": str(wine), "quantity": 1},
    )
    assert l2_res.status_code == 200
    line_2 = l2_res.json()["lines"][1]["line_id"]
    assert l2_res.json()["subtotal_minor"] == 4600

    # Splitting while draft lines remain is rejected with 409
    premature = await rest_env.client.post(
        rest_env.url(f"/checks/{check_id}/split"),
        headers=rest_env.headers(rest_env.front_desk_a, key="rest-s4-sp-draft"),
        json={
            "schema_version": 1,
            "split_mode": "by_items",
            "shares": [
                {"label": "Seat 1", "line_ids": [line_1]},
                {"label": "Seat 2", "line_ids": [line_2]},
            ],
        },
    )
    assert premature.status_code == 409

    # Fire all draft lines
    assert (
        await rest_env.client.post(
            rest_env.url(f"/checks/{check_id}/fire"),
            headers=rest_env.headers(rest_env.front_desk_a, key="rest-s4-fire-1"),
            json={"schema_version": 1},
        )
    ).status_code == 200

    # Incomplete by_items split (omitting line_2) rejected with 409
    incomplete = await rest_env.client.post(
        rest_env.url(f"/checks/{check_id}/split"),
        headers=rest_env.headers(rest_env.front_desk_a, key="rest-s4-sp-inc"),
        json={
            "schema_version": 1,
            "split_mode": "by_items",
            "shares": [{"label": "Seat 1 only", "line_ids": [line_1]}],
        },
    )
    assert incomplete.status_code == 409

    # Valid by_items split: Seat 1 = 3200 (line_1), Seat 2 = 1400 (line_2) -> sum 4600
    split_res = await rest_env.client.post(
        rest_env.url(f"/checks/{check_id}/split"),
        headers=rest_env.headers(rest_env.front_desk_a, key="rest-s4-sp-ok"),
        json={
            "schema_version": 1,
            "split_mode": "by_items",
            "shares": [
                {"label": "Seat 1", "counterparty_id": str(guest_1), "line_ids": [line_1]},
                {"label": "Seat 2", "counterparty_id": str(guest_2), "line_ids": [line_2]},
            ],
        },
    )
    assert split_res.status_code == 200, split_res.text
    sp = split_res.json()
    assert sp["total_minor"] == 4600
    assert [(s["share_no"], s["amount_minor"]) for s in sp["shares"]] == [(1, 3200), (2, 1400)]

    # Adding another line after split is blocked by guard_restaurant_check_line (409)
    post_split_line = await rest_env.client.post(
        rest_env.url(f"/checks/{check_id}/lines"),
        headers=rest_env.headers(rest_env.front_desk_a, key="rest-s4-post-line"),
        json={"schema_version": 1, "menu_item_id": str(wine), "quantity": 1},
    )
    assert post_split_line.status_code == 409

    # Branch manager cannot bill into FIN-03 (company-wide required -> 403)
    assert (
        await rest_env.client.post(
            rest_env.url(f"/checks/{check_id}/shares/1/bill"),
            headers=rest_env.headers(rest_env.branch_a_mgr, key="rest-s4-bill-deny"),
            json={
                "schema_version": 1,
                "book_id": str(book_id),
                "counterparty_id": str(guest_1),
                "receivable_account_id": str(ar_id),
                "revenue_account_id": str(rev_id),
                "invoice_date": DAY,
                "due_date": DAY,
                "title": "Dinner Seat 1",
                "number": "REST-INV-001",
            },
        )
    ).status_code == 403

    # Company-wide owner bills Share 1 (3200) and Share 2 (1400) into FIN-03
    bill_1 = await rest_env.client.post(
        rest_env.url(f"/checks/{check_id}/shares/1/bill"),
        headers=rest_env.headers(rest_env.owner, key="rest-s4-bill-1"),
        json={
            "schema_version": 1,
            "book_id": str(book_id),
            "counterparty_id": str(guest_1),
            "receivable_account_id": str(ar_id),
            "revenue_account_id": str(rev_id),
            "invoice_date": DAY,
            "due_date": DAY,
            "title": "Dinner Seat 1",
            "number": "REST-INV-001",
        },
    )
    assert bill_1.status_code == 200, bill_1.text
    inv_1 = bill_1.json()["invoice_document_id"]

    bill_2 = await rest_env.client.post(
        rest_env.url(f"/checks/{check_id}/shares/2/bill"),
        headers=rest_env.headers(rest_env.owner, key="rest-s4-bill-2"),
        json={
            "schema_version": 1,
            "book_id": str(book_id),
            "counterparty_id": str(guest_2),
            "receivable_account_id": str(ar_id),
            "revenue_account_id": str(rev_id),
            "invoice_date": DAY,
            "due_date": DAY,
            "title": "Dinner Seat 2",
            "number": "REST-INV-002",
        },
    )
    assert bill_2.status_code == 200, bill_2.text
    inv_2 = bill_2.json()["invoice_document_id"]

    # Issue both FIN-03 invoices
    for idx, inv_id in ((1, inv_1), (2, inv_2)):
        iss = await rest_env.client.post(
            f"/v1/businesses/{rest_env.tenant}/financial-documents/books/{book_id}"
            f"/invoices/{inv_id}/issue",
            headers=rest_env.headers(rest_env.owner, key=f"rest-s4-issue-{idx}"),
            json={
                "schema_version": 1,
                "expected_revision": 1,
                "entry_date": DAY,
                "attestation": "confirmed_account_treatment",
            },
        )
        assert iss.status_code == 200, iss.text

    # Record a FIN-03 credit-note refund of 1000 against Share 1 (returned steak line)
    ref_1 = await rest_env.client.post(
        rest_env.url(f"/checks/{check_id}/refunds"),
        headers=rest_env.headers(rest_env.owner, key="rest-s4-ref-1"),
        json={
            "schema_version": 1,
            "share_no": 1,
            "amount_minor": 1000,
            "method": "credit",
            "reason": "Steak overcooked adjustment",
            "returned_line_id": line_1,
            "credit_date": DAY,
            "number": "REST-CR-001",
        },
    )
    assert ref_1.status_code == 200, ref_1.text
    cred_1 = ref_1.json()["credit_document_id"]
    assert cred_1 is not None

    # Issue the FIN-03 credit note
    iss_cr = await rest_env.client.post(
        f"/v1/businesses/{rest_env.tenant}/financial-documents/books/{book_id}"
        f"/credits/{cred_1}/issue",
        headers=rest_env.headers(rest_env.owner, key="rest-s4-issue-cr1"),
        json={
            "schema_version": 1,
            "expected_revision": 1,
            "entry_date": DAY,
            "attestation": "confirmed_account_treatment",
        },
    )
    assert iss_cr.status_code == 200, iss_cr.text

    # Record an external refund of 400 on Share 2
    ref_2 = await rest_env.client.post(
        rest_env.url(f"/checks/{check_id}/refunds"),
        headers=rest_env.headers(rest_env.owner, key="rest-s4-ref-2"),
        json={
            "schema_version": 1,
            "share_no": 2,
            "amount_minor": 400,
            "method": "external",
            "reason": "Corkage waived",
            "reference": "POS-REF-400",
            "refunded_at": (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
        },
    )
    assert ref_2.status_code == 200, ref_2.text

    # Trying to refund more than remaining Share 2 ceiling (1400 - 400 = 1000) fails with 409
    over = await rest_env.client.post(
        rest_env.url(f"/checks/{check_id}/refunds"),
        headers=rest_env.headers(rest_env.owner, key="rest-s4-ref-over"),
        json={
            "schema_version": 1,
            "share_no": 2,
            "amount_minor": 1001,
            "method": "external",
            "reason": "Over-refund attempt",
            "reference": "POS-REF-OVER",
            "refunded_at": (datetime.now(UTC) - timedelta(minutes=4)).isoformat(),
        },
    )
    assert over.status_code == 409
    assert over.json()["error"]["code"] == "RESTAURANT_REFUND_EXCEEDS_BILLED"

    # Reconciliation derives live FIN-03 balances + totals cleanly
    rec = await rest_env.client.get(
        rest_env.url(f"/checks/{check_id}/reconciliation"),
        headers=rest_env.headers(rest_env.owner),
    )
    assert rec.status_code == 200, rec.text
    data = rec.json()
    assert data["totals"] == {
        "check_subtotal_minor": 4600,
        "split_total_minor": 4600,
        "billed_total_minor": 4600,
        "invoiced_issued_minor": 4600,
        "paid_minor": 0,
        "credited_minor": 1000,
        "open_minor": 3600,
        "refunded_external_minor": 400,
        "refund_owed_minor": 0,
        "balanced": True,
    }
    assert [s["invoice_state"] for s in data["shares"]] == ["issued", "issued"]
    assert [r["state"] for r in data["refunds"]] == ["issued", "recorded"]


async def test_by_amounts_split_conservation_and_branch_rls(rest_env: RestaurantEnv) -> None:
    pizza = await _add_item_and_fire(rest_env, code="PIZZA_S4", name="Margherita", price_minor=1000)
    chk = (
        await rest_env.client.post(
            rest_env.url("/checks"),
            headers=rest_env.headers(rest_env.front_desk_a, key="rest-s4-amt-chk"),
            json={
                "schema_version": 1,
                "location_id": str(rest_env.branch_a),
                "service_mode": "takeout",
                "currency": "USD",
            },
        )
    ).json()
    cid = chk["check_id"]
    assert (
        await rest_env.client.post(
            rest_env.url(f"/checks/{cid}/lines"),
            headers=rest_env.headers(rest_env.front_desk_a, key="rest-s4-amt-l1"),
            json={"schema_version": 1, "menu_item_id": str(pizza), "quantity": 1},
        )
    ).status_code == 200
    assert (
        await rest_env.client.post(
            rest_env.url(f"/checks/{cid}/fire"),
            headers=rest_env.headers(rest_env.front_desk_a, key="rest-s4-amt-fire"),
            json={"schema_version": 1},
        )
    ).status_code == 200

    # Unbalanced 3-way split (333 + 333 + 333 = 999 != 1000) is rejected with 409!
    bad = await rest_env.client.post(
        rest_env.url(f"/checks/{cid}/split"),
        headers=rest_env.headers(rest_env.front_desk_a, key="rest-s4-amt-bad"),
        json={
            "schema_version": 1,
            "split_mode": "by_amounts",
            "shares": [
                {"label": "P1", "amount_minor": 333},
                {"label": "P2", "amount_minor": 333},
                {"label": "P3", "amount_minor": 333},
            ],
        },
    )
    assert bad.status_code == 409

    # Exact 3-way split (334 + 333 + 333 = 1000) succeeds
    ok = await rest_env.client.post(
        rest_env.url(f"/checks/{cid}/split"),
        headers=rest_env.headers(rest_env.front_desk_a, key="rest-s4-amt-ok"),
        json={
            "schema_version": 1,
            "split_mode": "by_amounts",
            "shares": [
                {"label": "P1", "amount_minor": 334},
                {"label": "P2", "amount_minor": 333},
                {"label": "P3", "amount_minor": 333},
            ],
        },
    )
    assert ok.status_code == 200, ok.text
    assert sum(s["amount_minor"] for s in ok.json()["shares"]) == 1000

    # Branch B cannot view Branch A split (404); branch mgr denied FIN-03 reconciliation
    assert (
        await rest_env.client.get(
            rest_env.url(f"/checks/{cid}/split"),
            headers=rest_env.headers(rest_env.branch_b_mgr),
        )
    ).status_code == 404
    assert (
        await rest_env.client.get(
            rest_env.url(f"/checks/{cid}/reconciliation"),
            headers=rest_env.headers(rest_env.branch_a_mgr),
        )
    ).status_code == 403
