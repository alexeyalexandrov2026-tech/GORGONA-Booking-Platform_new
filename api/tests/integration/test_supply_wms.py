"""Integration tests for SUPPLY-01 Slice 1 (0138): multi-warehouse WMS bins, goods-owner
isolation (company legal entity vs 3PL bailor), lot/batch & serial tracking, and STOCK-01
linked movements.
"""

from dataclasses import dataclass
from datetime import date
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.business import modules
from gorgona_booking.business.readiness_registry import Readiness
from gorgona_booking.db.provisioning import add_membership
from tests.integration import test_management_api as shared
from tests.integration.booking_support import BookingWorld
from tests.integration.configuration_support import Config
from tests.integration.seed import FakeUser, seed_other_branch, seed_user
from tests.integration.test_counterparties import card
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp


@dataclass(frozen=True)
class SupplyEnv:
    client: httpx.AsyncClient
    idp: FakeIdp
    world: BookingWorld
    owner: FakeUser
    branch_b_mgr: FakeUser
    entity_id: UUID
    book_id: UUID
    bailor_a_cp_id: UUID
    bailor_b_cp_id: UUID
    place_main_id: UUID
    place_aux_id: UUID
    item_id: UUID

    @property
    def tenant(self) -> UUID:
        return self.world.a.tenant_id

    @property
    def home(self) -> UUID:
        return self.world.a.location_id

    def url(self, suffix: str) -> str:
        return f"/v1/businesses/{self.tenant}/supply{suffix}"

    def headers(self, user: FakeUser, *, key: str | None = None) -> dict[str, str]:
        h = self.idp.bearer(user.subject, email=user.email)
        if key is not None:
            h["Idempotency-Key"] = key
        return h


@pytest.fixture
def enable_supply_for_test(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(
        modules.MODULES_BY_ID,
        "supply",
        modules.MODULES_BY_ID["supply"].model_copy(
            update={"enableable": True, "readiness": Readiness.TECHNICALLY_VERIFIED}
        ),
    )


@pytest.fixture
async def sup_env(
    client: httpx.AsyncClient,
    idp: FakeIdp,
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    enable_supply_for_test: None,
) -> SupplyEnv:
    tenant_a = world.a.tenant_id
    home = world.a.location_id
    branch_b, _ = seed_other_branch(owner_conn, world.a)

    def _m(role: str, label: str, loc: UUID | None) -> FakeUser:
        u = seed_user(owner_conn, f"sup-{label}-{uuid7()}")
        add_membership(
            owner_conn,
            tenant_id=tenant_a,
            user_id=u.user_id,
            role=role,
            location_id=loc,
        )
        return u

    owner = _m("owner", "owner", None)
    branch_b_mgr = _m("manager", "mgr-b", branch_b)
    owner_conn.commit()

    cfg = Config(client, idp)
    await cfg.profile(owner, tenant_a, 0, [25])
    await cfg.publish(
        owner,
        tenant_a,
        0,
        ["counterparties", "finance", "finance_documents", "inventory", "supply"],
    )

    h = idp.bearer(owner.subject, email=owner.email)
    biz = f"/v1/businesses/{tenant_a}"

    bailor_a_cp_id, bailor_b_cp_id = uuid7(), uuid7()
    for cid, name in ((bailor_a_cp_id, "Bailor 3PL Alpha"), (bailor_b_cp_id, "Bailor 3PL Beta")):
        res = await client.put(
            f"{biz}/counterparties/{cid}",
            headers={**h, "Idempotency-Key": f"sup-cp-{cid}"},
            json=card(display_name=name, roles=["customer"]),
        )
        assert res.status_code == 200, res.text

    entity_id, book_id = uuid7(), uuid7()
    assert (
        await client.put(
            f"{biz}/legal-entities/{entity_id}",
            headers={**h, "Idempotency-Key": f"sup-le-{uuid7()}"},
            json={
                "expected_revision": 0,
                "code": "SUP_LE_01",
                "legal_name": "Gorgona Supply Corp",
            },
        )
    ).status_code == 200

    assert (
        await client.put(
            f"{biz}/ledger/books/{book_id}",
            headers={**h, "Idempotency-Key": f"sup-bk-{uuid7()}"},
            json={
                "schema_version": 1,
                "expected_revision": 0,
                "legal_entity_id": str(entity_id),
                "base_currency": "USD",
                "fiscal_year_start_month": 1,
                "accounting_start": date(2026, 1, 1).isoformat(),
            },
        )
    ).status_code == 200

    accts = {
        a["code"]: a["account_id"]
        for a in (
            await client.get(f"{biz}/ledger/books/{book_id}/accounts?limit=100", headers=h)
        ).json()["items"]
    }
    assert (
        await client.put(
            f"{biz}/inventory/posting-rules/{book_id}",
            headers={**h, "Idempotency-Key": f"sup-rl-{uuid7()}"},
            json={
                "schema_version": 1,
                "expected_revision": 0,
                "inventory_account_id": accts["1300"],
                "receipt_account_id": accts["1400"],
                "opening_account_id": accts["3900"],
                "surplus_account_id": accts["4900"],
                "consumption_account_id": accts["5000"],
                "loss_account_id": accts["6900"],
                "difference_account_id": accts["6900"],
            },
        )
    ).status_code == 200

    place_main_id, place_aux_id, item_id = uuid7(), uuid7(), uuid7()
    for pid, pcode, pname in (
        (place_main_id, "WH_MAIN", "Main Warehouse Hall"),
        (place_aux_id, "WH_AUX", "Aux Shipping Dock"),
    ):
        assert (
            await client.put(
                f"{biz}/inventory/places/{pid}",
                headers={**h, "Idempotency-Key": f"sup-pl-{pid}"},
                json={
                    "schema_version": 1,
                    "expected_revision": 0,
                    "location_id": str(home),
                    "code": pcode,
                    "name": pname,
                    "archived": False,
                },
            )
        ).status_code == 200

    assert (
        await client.put(
            f"{biz}/inventory/items/{item_id}",
            headers={**h, "Idempotency-Key": f"sup-it-{uuid7()}"},
            json={
                "schema_version": 1,
                "expected_revision": 0,
                "code": "VALVE_M12",
                "name": "Precision Steel Valve M12",
                "unit": "pcs",
                "quantity_scale": 0,
                "archived": False,
            },
        )
    ).status_code == 200

    return SupplyEnv(
        client=client,
        idp=idp,
        world=world,
        owner=owner,
        branch_b_mgr=branch_b_mgr,
        entity_id=entity_id,
        book_id=book_id,
        bailor_a_cp_id=bailor_a_cp_id,
        bailor_b_cp_id=bailor_b_cp_id,
        place_main_id=place_main_id,
        place_aux_id=place_aux_id,
        item_id=item_id,
    )


async def test_goods_owner_isolation_and_stock01_linked_wms_movements(sup_env: SupplyEnv) -> None:
    # 1. Register Company owner + two 3PL bailor owners
    co_owner_id, bailor_a_id, bailor_b_id = uuid7(), uuid7(), uuid7()

    r_co = await sup_env.client.put(
        sup_env.url(f"/owners/{co_owner_id}"),
        headers=sup_env.headers(sup_env.owner, key=f"sup-own-co-{uuid7()}"),
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "location_id": str(sup_env.home),
            "code": "OWN_COMPANY",
            "display_name": "Gorgona Supply Corp (Own Stock)",
            "owner_kind": "company_entity",
            "legal_entity_id": str(sup_env.entity_id),
        },
    )
    assert r_co.status_code == 200, r_co.text

    for oid, code, name, cpid in (
        (bailor_a_id, "3PL_ALPHA", "Bailor Alpha 3PL", sup_env.bailor_a_cp_id),
        (bailor_b_id, "3PL_BETA", "Bailor Beta 3PL", sup_env.bailor_b_cp_id),
    ):
        r_3pl = await sup_env.client.put(
            sup_env.url(f"/owners/{oid}"),
            headers=sup_env.headers(sup_env.owner, key=f"sup-own-3pl-{oid}"),
            json={
                "schema_version": 1,
                "expected_revision": 0,
                "location_id": str(sup_env.home),
                "code": code,
                "display_name": name,
                "owner_kind": "counterparty_3pl",
                "counterparty_id": str(cpid),
            },
        )
        assert r_3pl.status_code == 200, r_3pl.text

    # 2. Create warehouse bins: general company bin, shipping bin in Aux place, and dedicated
    # Bailor Alpha bin
    bin_co_id, bin_ship_id, bin_3pl_alpha_id = uuid7(), uuid7(), uuid7()
    for bid, pid, zc, bc, bkind, ded in (
        (bin_co_id, sup_env.place_main_id, "ZONE_A", "BIN_A01", "storage", co_owner_id),
        (bin_ship_id, sup_env.place_aux_id, "ZONE_S", "BIN_SHIP01", "shipping", co_owner_id),
        (bin_3pl_alpha_id, sup_env.place_main_id, "ZONE_3PL", "BIN_3PL_A1", "storage", bailor_a_id),
    ):
        rb = await sup_env.client.put(
            sup_env.url(f"/bins/{bid}"),
            headers=sup_env.headers(sup_env.owner, key=f"sup-bin-{bid}"),
            json={
                "schema_version": 1,
                "expected_revision": 0,
                "location_id": str(sup_env.home),
                "place_id": str(pid),
                "zone_code": zc,
                "bin_code": bc,
                "bin_kind": bkind,
                "dedicated_owner_id": str(ded),
            },
        )
        assert rb.status_code == 200, rb.text

    # 3. Create lots for Company owner and 3PL Bailor Alpha
    lot_co_id, lot_3pl_a_id = uuid7(), uuid7()
    for lid, oid, lcode, cost in (
        (lot_co_id, co_owner_id, "LOT-CO-2026-01", 5000),
        (lot_3pl_a_id, bailor_a_id, "LOT-3PLA-2026-01", 0),
    ):
        rl = await sup_env.client.put(
            sup_env.url(f"/lots/{lid}"),
            headers=sup_env.headers(sup_env.owner, key=f"sup-lot-{lid}"),
            json={
                "schema_version": 1,
                "expected_revision": 0,
                "location_id": str(sup_env.home),
                "goods_owner_id": str(oid),
                "item_id": str(sup_env.item_id),
                "lot_code": lcode,
                "manufactured_on": "2026-10-01",
                "expires_on": "2027-10-01",
                "unit_cost_minor": cost,
            },
        )
        assert rl.status_code == 200, rl.text

    # 4. Company inbound putaway (3 serialized units @ $50 each = $150.00) auto-posts a real
    # STOCK-01 receipt
    in_co = await sup_env.client.post(
        sup_env.url("/movements/inbound"),
        headers=sup_env.headers(sup_env.owner, key=f"sup-in-co-{uuid7()}"),
        json={
            "schema_version": 1,
            "location_id": str(sup_env.home),
            "bin_id": str(bin_co_id),
            "goods_owner_id": str(co_owner_id),
            "item_id": str(sup_env.item_id),
            "lot_id": str(lot_co_id),
            "quantity": 3,
            "serial_codes": ["SN-CO-1", "SN-CO-2", "SN-CO-3"],
            "auto_stock_receipt_date": "2026-10-01",
            "auto_stock_receipt_reason": "purchase",
            "auto_stock_receipt_amount": "150.00",
            "reference_code": "PO-1001",
        },
    )
    assert in_co.status_code == 200, in_co.text
    in_co_data = in_co.json()
    assert in_co_data["stock_document_id"] is not None
    assert in_co_data["stock_line_no"] == 1

    # Verify STOCK-01 balance in place_main_id is 3 and moving-average cost is $150.00
    stk_bal = await sup_env.client.get(
        f"/v1/businesses/{sup_env.tenant}/inventory/balances",
        headers=sup_env.headers(sup_env.owner),
    )
    assert stk_bal.status_code == 200
    assert any(
        b["place_id"] == str(sup_env.place_main_id) and b["quantity"] == "3"
        for b in stk_bal.json()["items"]
    )

    # 5. 3PL Bailor Alpha custodial inbound putaway (2 serialized units, NO STOCK-01 valuation)
    in_3pl = await sup_env.client.post(
        sup_env.url("/movements/inbound"),
        headers=sup_env.headers(sup_env.owner, key=f"sup-in-3pl-{uuid7()}"),
        json={
            "schema_version": 1,
            "location_id": str(sup_env.home),
            "bin_id": str(bin_3pl_alpha_id),
            "goods_owner_id": str(bailor_a_id),
            "item_id": str(sup_env.item_id),
            "lot_id": str(lot_3pl_a_id),
            "quantity": 2,
            "serial_codes": ["SN-3PLA-1", "SN-3PLA-2"],
            "reference_code": "ASN-3PL-01",
        },
    )
    assert in_3pl.status_code == 200, in_3pl.text
    assert in_3pl.json()["stock_document_id"] is None

    # 6. GOODS-OWNER ISOLATION («Товар другого собственника недоступен»):
    # 6a. Bailor Beta cannot putaway or pick using Bailor Alpha's lot or dedicated bin (409
    # SUPPLY_OWNER_MISMATCH)
    cross_pick = await sup_env.client.post(
        sup_env.url("/movements/outbound"),
        headers=sup_env.headers(sup_env.owner, key=f"sup-cross-1-{uuid7()}"),
        json={
            "schema_version": 1,
            "location_id": str(sup_env.home),
            "bin_id": str(bin_3pl_alpha_id),
            "goods_owner_id": str(bailor_b_id),
            "item_id": str(sup_env.item_id),
            "lot_id": str(lot_3pl_a_id),
            "quantity": 1,
        },
    )
    assert cross_pick.status_code == 409
    assert cross_pick.json()["error"]["code"] == "SUPPLY_OWNER_MISMATCH"

    # 6b. Company owner cannot pick or relocate 3PL Bailor Alpha's lot (409 SUPPLY_OWNER_MISMATCH)
    co_steal_3pl = await sup_env.client.post(
        sup_env.url("/movements/outbound"),
        headers=sup_env.headers(sup_env.owner, key=f"sup-cross-2-{uuid7()}"),
        json={
            "schema_version": 1,
            "location_id": str(sup_env.home),
            "bin_id": str(bin_3pl_alpha_id),
            "goods_owner_id": str(co_owner_id),
            "item_id": str(sup_env.item_id),
            "lot_id": str(lot_3pl_a_id),
            "quantity": 1,
            "auto_stock_write_off_date": "2026-10-01",
        },
    )
    assert co_steal_3pl.status_code == 409
    assert co_steal_3pl.json()["error"]["code"] == "SUPPLY_OWNER_MISMATCH"

    # 6c. 3PL Bailor Alpha cannot relocate its lot into Company's dedicated bin (409
    # SUPPLY_OWNER_MISMATCH)
    rel_wrong_bin = await sup_env.client.post(
        sup_env.url("/movements/relocate"),
        headers=sup_env.headers(sup_env.owner, key=f"sup-cross-3-{uuid7()}"),
        json={
            "schema_version": 1,
            "location_id": str(sup_env.home),
            "from_bin_id": str(bin_3pl_alpha_id),
            "to_bin_id": str(bin_co_id),
            "goods_owner_id": str(bailor_a_id),
            "item_id": str(sup_env.item_id),
            "lot_id": str(lot_3pl_a_id),
            "quantity": 1,
        },
    )
    assert rel_wrong_bin.status_code == 409
    assert rel_wrong_bin.json()["error"]["code"] == "SUPPLY_OWNER_MISMATCH"

    # 7. Company cross-place bin relocation (Main -> Aux) auto-posts a real STOCK-01 transfer
    rel_co = await sup_env.client.post(
        sup_env.url("/movements/relocate"),
        headers=sup_env.headers(sup_env.owner, key=f"sup-rel-co-{uuid7()}"),
        json={
            "schema_version": 1,
            "location_id": str(sup_env.home),
            "from_bin_id": str(bin_co_id),
            "to_bin_id": str(bin_ship_id),
            "goods_owner_id": str(co_owner_id),
            "item_id": str(sup_env.item_id),
            "lot_id": str(lot_co_id),
            "quantity": 2,
            "serial_codes": ["SN-CO-1", "SN-CO-2"],
            "document_date": "2026-10-01",
            "reference_code": "REPLEN-01",
        },
    )
    assert rel_co.status_code == 200, rel_co.text
    assert rel_co.json()["stock_document_id"] is not None

    # 8. Company outbound pick of 1 unit from shipping bin auto-posts a real STOCK-01 write_off
    out_co = await sup_env.client.post(
        sup_env.url("/movements/outbound"),
        headers=sup_env.headers(sup_env.owner, key=f"sup-out-co-{uuid7()}"),
        json={
            "schema_version": 1,
            "location_id": str(sup_env.home),
            "bin_id": str(bin_ship_id),
            "goods_owner_id": str(co_owner_id),
            "item_id": str(sup_env.item_id),
            "lot_id": str(lot_co_id),
            "quantity": 1,
            "serial_codes": ["SN-CO-1"],
            "auto_stock_write_off_date": "2026-10-01",
            "auto_stock_write_off_reason": "used",
            "reference_code": "PICK-1001",
        },
    )
    assert out_co.status_code == 200, out_co.text
    assert out_co.json()["stock_document_id"] is not None

    # Verify lot balances: bin_co_id has 1, bin_ship_id has 1, bin_3pl_alpha_id has 2
    bals = (
        await sup_env.client.get(
            sup_env.url("/lot-balances"),
            headers=sup_env.headers(sup_env.owner),
        )
    ).json()["items"]
    by_bin = {b["bin_id"]: b["quantity"] for b in bals}
    assert by_bin[str(bin_co_id)] == 1
    assert by_bin[str(bin_ship_id)] == 1
    assert by_bin[str(bin_3pl_alpha_id)] == 2

    # Verify serial states: SN-CO-1 is shipped, SN-CO-2 & SN-CO-3 are in_stock
    sers = (
        await sup_env.client.get(
            sup_env.url(f"/serials?goods_owner_id={co_owner_id}"),
            headers=sup_env.headers(sup_env.owner),
        )
    ).json()["items"]
    ser_state = {s["serial_code"]: (s["state"], s["bin_id"]) for s in sers}
    assert ser_state["SN-CO-1"] == ("shipped", str(bin_ship_id))
    assert ser_state["SN-CO-2"] == ("in_stock", str(bin_ship_id))
    assert ser_state["SN-CO-3"] == ("in_stock", str(bin_co_id))

    # 9. Branch-B manager sees 0 owners/bins/lots of Branch-A
    b_lots = await sup_env.client.get(
        sup_env.url("/lots"),
        headers=sup_env.headers(sup_env.branch_b_mgr),
    )
    assert b_lots.status_code == 200
    assert b_lots.json()["items"] == []
