"""Stage 1 completion: a small business, a network of independent companies and a
hybrid company run through every stage 1 module without duplication or leakage
(master plan §13, stage 1). Real API, real publication and PostgreSQL; FAKE data.
"""

import json
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid7
from zoneinfo import ZoneInfo

import httpx
import psycopg
import pytest
from psycopg import sql

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import add_membership
from tests.integration import test_management_api as shared
from tests.integration.booking_support import BookingWorld, at
from tests.integration.customer_support import customer_day
from tests.integration.seed import FakeUser, seed_other_branch, seed_user
from tests.integration.test_agreements import Agreements
from tests.integration.test_delegations import Parties
from tests.integration.test_documents import ALL_MODULES, Documents
from tests.integration.test_groups import Groups
from tests.integration.test_resource_reservations import Reservations
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a

EMAIL, PHONE = "fake.counterparty@example.test", "+15550101234"
# Company-wide stage 1 records; none may be visible outside their company or branch.
COMPANY_TABLES = (
    "counterparties",
    "counterparty_versions",
    "counterparty_booking_links",
    "document_files",
    "documents",
    "document_versions",
    "document_counterparty_links",
    "agreements",
    "agreement_versions",
)


class Company:
    """One business seen through one member, across the stage 1 modules."""

    def __init__(
        self, client: httpx.AsyncClient, business: UUID, user: FakeUser, idp: FakeIdp
    ) -> None:
        self.docs = Documents(client, business, user, idp)
        self.contracts = Agreements(client, business, user, idp)
        self.staff = Reservations(client, business, user, idp)
        self.client, self.business, self.user = client, business, user

    async def enable(self, industries: list[int]) -> None:
        await self.docs.config.profile(self.user, self.business, 0, industries)
        await self.docs.config.publish(self.user, self.business, 0, ALL_MODULES)

    async def booking(
        self, location: UUID, resource: UUID, variant: UUID, hour: int
    ) -> dict[str, Any]:
        starts = datetime.fromisoformat(f"{customer_day()}T{hour:02d}:00:00").replace(
            tzinfo=ZoneInfo("America/New_York")
        )
        response = await self.client.post(
            f"/v1/salons/{self.business}/bookings",
            headers=self.docs.auth,
            json={
                "location_id": str(location),
                "resource_id": str(resource),
                "variant_id": str(variant),
                "starts_at": starts.isoformat(),
                "customer_name": "FAKE Stage Guest",
                "customer_email": EMAIL,
                "customer_phone": PHONE,
            },
        )
        assert response.status_code == 201, response.text
        result: dict[str, Any] = response.json()
        return result

    async def everything(self, world: BookingWorld) -> dict[str, str]:
        """One record per module, all about the same counterparty."""
        partner = await self.docs.counterparty()
        booking = await self.booking(
            world.a.location_id, world.artist_a1, world.catalog_a.base_variant_id, 11
        )
        linked = await self.client.post(
            f"{self.docs.base}/counterparties/{partner}/booking-links",
            json={"action": "link", "booking_ids": [booking["booking_id"]]},
            headers=self.docs.headers(),
        )
        assert linked.status_code == 200, linked.text
        file_id = await self.docs.stored()
        document = str((await self.docs.create(file_id=file_id))["document_id"])
        assert (
            await self.docs.link(document, {"action": "link", "counterparty_id": partner})
        ).status_code == 200
        contract = await self.contracts.drafted(partner)
        assert (await self.contracts.agree(contract, 1)).status_code == 200
        reservation = uuid7()
        reserved = await self.staff.put(
            reservation,
            self.staff.body(world.a.location_id, [world.artist_a2], at(9), at(10)),
        )
        assert reserved.status_code == 200, reserved.text
        return {
            "partner": partner,
            "booking": str(booking["booking_id"]),
            "booking_starts": str(booking["starts_at"]),
            "document": document,
            "contract": contract,
            "reservation": str(reservation),
        }


async def _rows(pool: RuntimePool, business: UUID, table: str) -> int:
    async with tenant_transaction(pool, business) as conn:
        query = sql.SQL("select count(*) from {}").format(sql.Identifier("gba", table))
        row = await (await conn.execute(query)).fetchone()
    assert row is not None
    return int(row[0])


async def test_small_business_keeps_one_record_across_every_module(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager_a: FakeUser,
    idp: FakeIdp,
    app_pool: RuntimePool,
) -> None:
    company = Company(client, world.a.tenant_id, manager_a, idp)
    await company.enable([1])
    made = await company.everything(world)
    partner = made["partner"]
    # One card is customer and supplier at once; every module refers to it.
    listed = (await company.docs.get("/counterparties")).json()["items"]
    assert [(c["counterparty_id"], c["roles"]) for c in listed] == [
        (partner, ["customer", "supplier"])
    ]
    for suffix, key in (("bookings", "booking"), ("documents", "document")):
        items = (await company.docs.get(f"/counterparties/{partner}/{suffix}")).json()["items"]
        assert [r[key][f"{key}_id"] for r in items] == [made[key]], suffix
    contracts = (await company.docs.get(f"/counterparties/{partner}/agreements")).json()
    assert [r["agreement_id"] for r in contracts["items"]] == [made["contract"]]
    # A check by the customer's e-mail finds the existing card instead of a new one.
    probe = await client.post(
        f"{company.docs.base}/counterparties/match-check",
        json={"emails": [EMAIL.upper()]},
        headers=company.docs.auth,
    )
    assert [r["counterparty_id"] for r in probe.json()["items"]] == [partner]
    # Bookings and reservations share one occupancy table: no double use of a resource.
    starts = datetime.fromisoformat(made["booking_starts"])
    clash = await company.staff.put(
        uuid7(),
        company.staff.body(
            world.a.location_id, [world.artist_a1], starts, starts + timedelta(minutes=15)
        ),
    )
    assert clash.status_code == 409, clash.text
    async with tenant_transaction(app_pool, company.business) as conn:
        kinds = await (
            await conn.execute(
                "select source_kind, count(*) from gba.resource_allocations "
                "where state in ('held', 'confirmed') group by source_kind order by 1"
            )
        ).fetchall()
        audits = await (await conn.execute("select details from gba.audit_events")).fetchall()
        receipts = await (
            await conn.execute(
                "select response_body from gba.idempotency_keys where operation like 'business.%%'"
            )
        ).fetchall()
    assert kinds == [("booking", 1), ("reservation", 1)]
    for text in (json.dumps([r[0] for r in audits]), json.dumps([r[0] for r in receipts])):
        assert EMAIL not in text.lower()
        assert "FAKE Supply" not in text
        assert "FAKE Agreement" not in text
    for table in ("counterparties", "documents", "agreements"):
        assert await _rows(app_pool, company.business, table) == 1


async def test_network_of_independent_companies_shares_no_records(
    client: httpx.AsyncClient,
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    idp: FakeIdp,
    app_pool: RuntimePool,
) -> None:
    owners = [seed_user(owner_conn, f"FAKE-network-owner-{uuid7()}") for _ in range(2)]
    for salon, user in zip((world.a, world.b), owners, strict=True):
        add_membership(owner_conn, tenant_id=salon.tenant_id, user_id=user.user_id, role="owner")
    a = Company(client, world.a.tenant_id, owners[0], idp)
    b = Company(client, world.b.tenant_id, owners[1], idp)
    for company in (a, b):
        await company.enable([1])
    made = await a.everything(world)
    own = await b.docs.counterparty(display_name="FAKE Network Partner B")
    # A group and a delegation connect the companies without moving ownership.
    groups, group = Groups(client, idp), uuid7()
    assert (await groups.create(owners[0], a.business, group)).status_code == 200
    assert (await groups.invite(owners[0], a.business, group, b.business)).status_code == 200
    assert (await groups.decide(owners[1], b.business, group, "accept", 1)).status_code == 200
    await Parties(client, idp, world).active_grant(owners[0], owners[1], [owners[1]])
    seen_by_b = Company(client, a.business, owners[1], idp)
    for path in (
        "/counterparties",
        f"/counterparties/{made['partner']}",
        f"/counterparties/{made['partner']}/documents",
        f"/counterparties/{made['partner']}/agreements",
        "/documents",
        f"/documents/{made['document']}",
        f"/documents/{made['document']}/versions/1/file",
        f"/agreements/{made['contract']}",
        f"/resource-reservations/{made['reservation']}",
    ):
        assert (await seen_by_b.docs.get(path)).status_code == 403, path
    listed = (await b.docs.get("/counterparties")).json()["items"]
    assert [c["counterparty_id"] for c in listed] == [own]
    assert (await b.docs.get("/documents")).json()["items"] == []
    expected = {"counterparties": 1, "counterparty_versions": 1}
    for table in (*COMPANY_TABLES, "resource_reservations"):
        assert await _rows(app_pool, b.business, table) == expected.get(table, 0), table
    async with tenant_transaction(app_pool, b.business) as conn:
        foreign = await (
            await conn.execute(
                "select count(*) from gba.resource_allocations where resource_id = %s",
                (world.artist_a1,),
            )
        ).fetchone()
    assert foreign == (0,)


async def test_hybrid_company_keeps_one_list_and_branch_limits(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager_a: FakeUser,
    owner_conn: psycopg.Connection,
    idp: FakeIdp,
    app_pool: RuntimePool,
) -> None:
    company = Company(client, world.a.tenant_id, manager_a, idp)
    await company.enable([1, 6, 24])
    made = await company.everything(world)
    supplier = await company.docs.counterparty(
        display_name="FAKE Hybrid Supplier",
        roles=["supplier", "contractor"],
        email=None,
        phone=None,
    )
    # Several business profiles, one company: one counterparty list.
    listed = (await company.docs.get("/counterparties")).json()["items"]
    assert {c["counterparty_id"] for c in listed} == {made["partner"], supplier}
    other_location, other_resource = seed_other_branch(owner_conn, world.a)
    branch = seed_user(owner_conn, f"FAKE-hybrid-branch-{uuid7()}")
    add_membership(
        owner_conn,
        tenant_id=world.a.tenant_id,
        user_id=branch.user_id,
        role="manager",
        location_id=other_location,
    )
    at_branch = Company(client, world.a.tenant_id, branch, idp)
    # A branch manager reserves only in the own branch and never sees company records.
    reserved = await at_branch.staff.put(
        uuid7(), at_branch.staff.body(other_location, [other_resource], at(9), at(10))
    )
    assert reserved.status_code == 200, reserved.text
    elsewhere = at_branch.staff.body(world.a.location_id, [world.artist_a1], at(12), at(13))
    assert (await at_branch.staff.put(uuid7(), elsewhere)).status_code == 403
    hidden = await at_branch.docs.get(f"/resource-reservations/{made['reservation']}")
    assert hidden.status_code == 404
    for path in (
        "/counterparties",
        "/documents",
        f"/agreements/{made['contract']}",
        f"/counterparties/{made['partner']}/agreements",
    ):
        assert (await at_branch.docs.get(path)).status_code == 403, path
    async with tenant_transaction(app_pool, company.business) as conn:
        await conn.execute(
            "select pg_catalog.set_config('gba.location_id', %s, true)", (str(other_location),)
        )
        for table in COMPANY_TABLES:
            query = sql.SQL("select count(*) from {}").format(sql.Identifier("gba", table))
            assert await (await conn.execute(query)).fetchone() == (0,), table
        rows = await (
            await conn.execute(
                "select source_kind, resource_id from gba.resource_allocations "
                "where state in ('held', 'confirmed')"
            )
        ).fetchall()
    assert rows == [("reservation", other_resource)]
    async with tenant_transaction(app_pool, company.business) as conn:
        everywhere = await (
            await conn.execute(
                "select source_kind, count(*) from gba.resource_allocations "
                "where state in ('held', 'confirmed') group by 1 order by 1"
            )
        ).fetchall()
    assert everywhere == [("booking", 1), ("reservation", 2)]
