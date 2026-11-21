"""Integration tests for MARKET-01 Slice 1 (0141): business storefronts, strict public field
projection (unpublished fields & internal costs never exposed), moderation, and client-operated
marketplaces with revocable seller connections and zero GORGONA commission.
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
class MarketEnv:
    client: httpx.AsyncClient
    idp: FakeIdp
    world: BookingWorld
    owner: FakeUser
    branch_b_mgr: FakeUser
    entity_a_id: UUID
    entity_b_id: UUID
    book_a_id: UUID
    book_b_id: UUID
    customer_cp_id: UUID
    seller_cp_id: UUID

    @property
    def tenant(self) -> UUID:
        return self.world.a.tenant_id

    @property
    def home(self) -> UUID:
        return self.world.a.location_id

    def url(self, suffix: str) -> str:
        return f"/v1/businesses/{self.tenant}/market{suffix}"

    def headers(self, user: FakeUser, *, key: str | None = None) -> dict[str, str]:
        h = self.idp.bearer(user.subject, email=user.email)
        if key is not None:
            h["Idempotency-Key"] = key
        return h


@pytest.fixture
def enable_storefronts_for_test(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(
        modules.MODULES_BY_ID,
        "storefronts",
        modules.MODULES_BY_ID["storefronts"].model_copy(
            update={"enableable": True, "readiness": Readiness.TECHNICALLY_VERIFIED}
        ),
    )


@pytest.fixture
async def mkt_env(
    client: httpx.AsyncClient,
    idp: FakeIdp,
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    enable_storefronts_for_test: None,
) -> MarketEnv:
    tenant_a = world.a.tenant_id
    branch_b, _ = seed_other_branch(owner_conn, world.a)

    def _m(role: str, label: str, loc: UUID | None) -> FakeUser:
        u = seed_user(owner_conn, f"mkt-{label}-{uuid7()}")
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
        ["counterparties", "finance", "finance_documents", "storefronts"],
    )

    h = idp.bearer(owner.subject, email=owner.email)
    biz = f"/v1/businesses/{tenant_a}"

    customer_cp_id, seller_cp_id = uuid7(), uuid7()
    for cid, name in (
        (customer_cp_id, "Marketplace Buyer Corp"),
        (seller_cp_id, "Independent Seller Studio"),
    ):
        assert (
            await client.put(
                f"{biz}/counterparties/{cid}",
                headers={**h, "Idempotency-Key": f"mkt-cp-{cid}"},
                json=card(display_name=name, roles=["customer", "supplier"]),
            )
        ).status_code == 200

    entity_a_id, entity_b_id, book_a_id, book_b_id = uuid7(), uuid7(), uuid7(), uuid7()
    for eid, bid, code, lname in (
        (entity_a_id, book_a_id, "MKT_SELLER_A", "Seller Alpha LLC"),
        (entity_b_id, book_b_id, "MKT_SELLER_B", "Seller Beta LLC"),
    ):
        assert (
            await client.put(
                f"{biz}/legal-entities/{eid}",
                headers={**h, "Idempotency-Key": f"mkt-le-{eid}"},
                json={"expected_revision": 0, "code": code, "legal_name": lname},
            )
        ).status_code == 200
        assert (
            await client.put(
                f"{biz}/ledger/books/{bid}",
                headers={**h, "Idempotency-Key": f"mkt-bk-{bid}"},
                json={
                    "schema_version": 1,
                    "expected_revision": 0,
                    "legal_entity_id": str(eid),
                    "base_currency": "USD",
                    "fiscal_year_start_month": 1,
                    "accounting_start": date(2026, 1, 1).isoformat(),
                },
            )
        ).status_code == 200

    return MarketEnv(
        client=client,
        idp=idp,
        world=world,
        owner=owner,
        branch_b_mgr=branch_b_mgr,
        entity_a_id=entity_a_id,
        entity_b_id=entity_b_id,
        book_a_id=book_a_id,
        book_b_id=book_b_id,
        customer_cp_id=customer_cp_id,
        seller_cp_id=seller_cp_id,
    )


async def test_storefront_strict_public_field_projection_and_marketplace_connections(
    mkt_env: MarketEnv,
) -> None:
    h = mkt_env.headers(mkt_env.owner)
    sf_id = uuid7()
    r_sf = await mkt_env.client.put(
        mkt_env.url(f"/storefronts/{sf_id}"),
        headers=mkt_env.headers(mkt_env.owner, key=f"mkt-sf-{uuid7()}"),
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "location_id": str(mkt_env.home),
            "legal_entity_id": str(mkt_env.entity_a_id),
            "slug": "alpha-industrial",
            "display_name": "Alpha Industrial Storefront",
            "description": "Internal storefront summary not selected for projection",
            "location_city": "Chicago",
            "currency": "USD",
            "published_fields": ["title", "price", "currency", "availability", "location_city"],
            "is_published": True,
        },
    )
    assert r_sf.status_code == 200, r_sf.text

    # Create 2 listings: one published (with secret internal cost/notes + unselected sku),
    # one draft (must NOT appear in public catalog!)
    pub_lst_id, draft_lst_id = uuid7(), uuid7()
    assert (
        await mkt_env.client.put(
            mkt_env.url(f"/listings/{pub_lst_id}"),
            headers=mkt_env.headers(mkt_env.owner, key=f"mkt-lst-1-{uuid7()}"),
            json={
                "schema_version": 1,
                "expected_revision": 0,
                "location_id": str(mkt_env.home),
                "storefront_id": str(sf_id),
                "sku": "SECRET-SKU-01",
                "title": "Industrial Hydraulic Pump",
                "description": "Unselected description text",
                "category": "hydraulics",
                "brand": "AlphaBrand",
                "currency": "USD",
                "price_minor": 45000,
                "available_quantity": 8,
                "internal_cost_minor": 19000,
                "internal_notes": "PRIVATE SUPPLIER COST $190",
                "published_fields": ["title", "price", "currency", "sku", "description"],
                "moderation_status": "published",
            },
        )
    ).status_code == 200
    assert (
        await mkt_env.client.put(
            mkt_env.url(f"/listings/{draft_lst_id}"),
            headers=mkt_env.headers(mkt_env.owner, key=f"mkt-lst-2-{uuid7()}"),
            json={
                "schema_version": 1,
                "expected_revision": 0,
                "location_id": str(mkt_env.home),
                "storefront_id": str(sf_id),
                "sku": "DRAFT-SKU-02",
                "title": "Unpublished Prototype",
                "category": "hydraulics",
                "currency": "USD",
                "price_minor": 99000,
                "available_quantity": 1,
                "published_fields": ["title", "price", "currency"],
                "moderation_status": "draft",
            },
        )
    ).status_code == 200

    # Strict public projection: only published listing & intersection of allowed fields
    cat_res = await mkt_env.client.get(
        mkt_env.url(f"/storefronts/{sf_id}/public-catalog"), headers=h
    )
    assert cat_res.status_code == 200, cat_res.text
    cat = cat_res.json()
    assert len(cat["items"]) == 1
    item = cat["items"][0]
    assert item["listing_id"] == str(pub_lst_id)
    assert item["published_fields"] == ["title", "price", "currency"]
    assert item["fields"] == {
        "title": "Industrial Hydraulic Pump",
        "price": 45000,
        "currency": "USD",
    }
    raw_text = cat_res.text
    assert "PRIVATE SUPPLIER COST" not in raw_text
    assert "SECRET-SKU-01" not in raw_text
    assert "Unpublished Prototype" not in raw_text
    assert "19000" not in raw_text

    # Client-operated marketplace with gorgona_commission_bps = 0 and revocable seller connection
    mp_id, conn_id = uuid7(), uuid7()
    r_mp = await mkt_env.client.put(
        mkt_env.url(f"/marketplaces/{mp_id}"),
        headers=mkt_env.headers(mkt_env.owner, key=f"mkt-mp-{uuid7()}"),
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "location_id": str(mkt_env.home),
            "slug": "midwest-b2b-exchange",
            "title": "Midwest Industrial B2B Marketplace",
            "operator_fee_bps": 250,
        },
    )
    assert r_mp.status_code == 200, r_mp.text
    assert r_mp.json()["gorgona_commission_bps"] == 0

    r_conn = await mkt_env.client.put(
        mkt_env.url(f"/marketplaces/{mp_id}/sellers/{conn_id}"),
        headers=mkt_env.headers(mkt_env.owner, key=f"mkt-conn-{uuid7()}"),
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "location_id": str(mkt_env.home),
            "seller_counterparty_id": str(mkt_env.seller_cp_id),
            "seller_storefront_slug": "independent-seller-studio",
            "granted_scopes": ["publish", "reports_read"],
            "status": "active",
        },
    )
    assert r_conn.status_code == 200, r_conn.text

    # Revoke connection and verify reactivation is rejected
    r_rev = await mkt_env.client.put(
        mkt_env.url(f"/marketplaces/{mp_id}/sellers/{conn_id}"),
        headers=mkt_env.headers(mkt_env.owner, key=f"mkt-conn-rev-{uuid7()}"),
        json={
            "schema_version": 1,
            "expected_revision": 1,
            "location_id": str(mkt_env.home),
            "seller_counterparty_id": str(mkt_env.seller_cp_id),
            "seller_storefront_slug": "independent-seller-studio",
            "granted_scopes": ["publish"],
            "status": "revoked",
        },
    )
    assert r_rev.status_code == 200, r_rev.text
    assert r_rev.json()["revoked_at"] is not None

    r_reactivate = await mkt_env.client.put(
        mkt_env.url(f"/marketplaces/{mp_id}/sellers/{conn_id}"),
        headers=mkt_env.headers(mkt_env.owner, key=f"mkt-conn-re-{uuid7()}"),
        json={
            "schema_version": 1,
            "expected_revision": 2,
            "location_id": str(mkt_env.home),
            "seller_counterparty_id": str(mkt_env.seller_cp_id),
            "seller_storefront_slug": "independent-seller-studio",
            "granted_scopes": ["publish"],
            "status": "active",
        },
    )
    assert r_reactivate.status_code == 409
    assert r_reactivate.json()["error"]["code"] == "MARKET_STATE_INVALID"

    # Branch B isolation check
    hb = mkt_env.headers(mkt_env.branch_b_mgr)
    assert (
        await mkt_env.client.get(mkt_env.url(f"/storefronts/{sf_id}"), headers=hb)
    ).status_code == 404
