"""PROPERTY-01 acceptance: who may reach each Property route (synthetic data only).

docs/plan/PACKAGE_PROPERTY01_ACCESS_DESIGN_2026-11-15.md. Every authenticated Property route is
called with real tokens and valid bodies by another company's manager, by company members
without the property permissions, by platform support, by branch-scoped managers and by a
company-wide manager who is suspended, reactivated and finally revoked. Refused commands write
nothing, a revoked member cannot replay an earlier command key, and the records the member made
keep their author.
"""

from dataclasses import dataclass
from uuid import UUID, uuid7

import httpx
import pytest

from gorgona_booking.api.app import create_app
from gorgona_booking.config import Settings
from gorgona_booking.db.pool import RuntimePool
from gorgona_booking.db.provisioning import (
    add_membership,
    grant_platform_admin,
    owner_tenant_transaction,
)
from tests.integration import test_property_leases as lease_tests
from tests.integration.seed import FakeUser, seed_other_branch, seed_user
from tests.integration.test_agreements import Agreements
from tests.integration.test_property_catalog import Catalog
from tests.integration.test_property_listings import listing
from tests.integration.test_property_move_in import lease_with_evidence, record_move_in

pytestmark = pytest.mark.anyio
agreements = lease_tests.agreements
catalog = lease_tests.catalog
client = lease_tests.client
enabled = lease_tests.enabled
idp = lease_tests.idp
manager_a = lease_tests.manager_a
manager_b = lease_tests.manager_b
__all__ = ["agreements", "catalog", "client", "enabled", "idp", "manager_a", "manager_b"]

READ, MANAGE, DELEGATE = "property.read", "property.manage", "property.contractor_work"
TABLES = (
    "property_objects",
    "property_revisions",
    "property_parties",
    "property_listings",
    "property_listing_revisions",
    "property_showings",
    "property_showing_cancellations",
    "property_leases",
    "property_lease_term_events",
    "property_move_ins",
    "property_move_in_photos",
    "property_maintenance_requests",
    "property_maintenance_events",
    "property_maintenance_obligations",
    "property_maintenance_contractor_links",
    "property_maintenance_contractor_updates",
)


@dataclass(frozen=True)
class Route:
    method: str
    template: str
    path: str
    body: dict[str, object] | None
    permission: str

    @property
    def name(self) -> str:
        return f"{self.method} {self.template}"


@dataclass(frozen=True)
class Estate:
    object_id: UUID
    showing_id: UUID
    lease_id: UUID
    prospect: str
    move_in: dict[str, object]
    maintenance_id: UUID


async def estate(c: Catalog, a: Agreements) -> Estate:
    """A unit with a listing, a showing and a lease with its move-in, all in the home branch."""
    lease_id, _, move_in = await lease_with_evidence(c, a)
    found = await c.client.get(f"{lease_tests.leases(c)}/{lease_id}", headers=c.headers)
    assert found.is_success, found.text
    object_id = UUID(found.json()["object_id"])
    saved = await c.client.put(
        f"/v1/businesses/{c.tenant}/property/listings/{object_id}",
        json=listing(),
        headers={**c.headers, "Idempotency-Key": str(uuid7())},
    )
    assert saved.is_success, saved.text
    prospect, showing_id = await c.counterparty(), uuid7()
    booked = await c.client.put(
        f"/v1/businesses/{c.tenant}/property/showings/{showing_id}",
        json=showing(object_id, prospect, "2031-07-10T14:00:00Z"),
        headers={**c.headers, "Idempotency-Key": str(uuid7())},
    )
    assert booked.is_success, booked.text
    recorded = await record_move_in(c, lease_id, move_in)
    assert recorded.is_success, recorded.text
    maintenance_id = uuid7()
    maint = await c.client.put(
        f"/v1/businesses/{c.tenant}/property/maintenance/{maintenance_id}",
        json={
            "schema_version": 1,
            "object_id": str(object_id),
            "lease_id": str(lease_id),
            "category": "plumbing",
            "priority": "routine",
            "title": "FAKE faucet drip",
            "description": "FAKE washer replacement needed",
        },
        headers={**c.headers, "Idempotency-Key": str(uuid7())},
    )
    assert maint.is_success, maint.text
    return Estate(object_id, showing_id, lease_id, prospect, move_in, maintenance_id)


def showing(object_id: UUID, prospect: str, starts_at: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "object_id": str(object_id),
        "prospect_id": prospect,
        "host_resource_id": None,
        "starts_at": starts_at,
        "ends_at": starts_at.replace("T14:", "T15:"),
    }


def routes(c: Catalog, e: Estate) -> list[Route]:
    """All nineteen authenticated Property routes, each with a valid body."""
    known = {
        "object_id": e.object_id,
        "showing_id": e.showing_id,
        "lease_id": e.lease_id,
        "request_id": e.maintenance_id,
        "grant_id": uuid7(),
    }

    def route(
        method: str,
        template: str,
        body: dict[str, object] | None,
        permission: str,
        **fresh: UUID,
    ) -> Route:
        path = f"/v1/businesses/{c.tenant}/property" + template.format(**{**known, **fresh})
        return Route(method, template, path, body, permission)

    parcel = {
        "schema_version": 1,
        "expected_revision": 0,
        "location_id": str(c.world.a.location_id),
        "kind": "parcel",
        "name": "FAKE refused parcel",
    }
    later = showing(e.object_id, e.prospect, "2031-08-10T14:00:00Z")
    lease = {
        "schema_version": 1,
        "object_id": str(e.object_id),
        "agreement_id": str(uuid7()),
        "agreement_revision": 2,
    }
    release = {
        "schema_version": 1,
        "action": "release",
        "agreement_revision": 3,
        "expected_revision": 1,
    }
    return [
        route("GET", "/objects", None, READ),
        route("GET", "/objects/{object_id}", None, READ),
        route("GET", "/objects/{object_id}/history", None, MANAGE),
        route("PUT", "/objects/{object_id}", parcel, MANAGE, object_id=uuid7()),
        route("GET", "/listings", None, READ),
        route("GET", "/listings/{object_id}", None, READ),
        route("GET", "/listings/{object_id}/history", None, MANAGE),
        route("PUT", "/listings/{object_id}", listing(expected_revision=1), MANAGE),
        route("GET", "/showings", None, READ),
        route("GET", "/showings/{showing_id}", None, READ),
        route("PUT", "/showings/{showing_id}", later, MANAGE, showing_id=uuid7()),
        route("POST", "/showings/{showing_id}/cancel", {"schema_version": 1}, MANAGE),
        route("GET", "/leases", None, MANAGE),
        route("GET", "/leases/{lease_id}", None, MANAGE),
        route("PUT", "/leases/{lease_id}", lease, MANAGE, lease_id=uuid7()),
        route("GET", "/leases/{lease_id}/terms", None, MANAGE),
        route("POST", "/leases/{lease_id}/terms", release, MANAGE),
        route("GET", "/leases/{lease_id}/move-in", None, MANAGE),
        route("PUT", "/leases/{lease_id}/move-in", e.move_in, MANAGE),
        route("GET", "/maintenance", None, READ),
        route("GET", "/maintenance/{request_id}", None, READ),
        route(
            "PUT",
            "/maintenance/{request_id}",
            {
                "schema_version": 1,
                "object_id": str(e.object_id),
                "lease_id": None,
                "category": "general",
                "priority": "routine",
                "title": "FAKE refused request",
                "description": "FAKE refused body",
            },
            MANAGE,
            request_id=uuid7(),
        ),
        route("GET", "/maintenance/{request_id}/events", None, MANAGE),
        route(
            "POST",
            "/maintenance/{request_id}/events",
            {
                "schema_version": 1,
                "action": "cancel",
                "expected_revision": 1,
            },
            MANAGE,
        ),
        route("GET", "/maintenance/{request_id}/obligations", None, MANAGE),
        route(
            "POST",
            "/maintenance/{request_id}/obligations",
            {
                "schema_version": 1,
                "book_id": str(uuid7()),
                "invoice_document_id": str(uuid7()),
            },
            MANAGE,
        ),
        route("GET", "/maintenance/{request_id}/contractor-company", None, MANAGE),
        route(
            "PUT",
            "/maintenance/{request_id}/contractor-company",
            {"schema_version": 1, "expected_revision": 0, "company_id": None},
            MANAGE,
        ),
        route("GET", "/maintenance/{request_id}/contractor-updates", None, MANAGE),
        route("GET", "/maintenance/{request_id}/contractor-work/{grant_id}", None, DELEGATE),
        route(
            "POST",
            "/maintenance/{request_id}/contractor-work/{grant_id}/updates",
            {"schema_version": 1, "kind": "acknowledged", "note": "FAKE refused"},
            DELEGATE,
        ),
    ]


async def call(
    c: Catalog, route: Route, headers: dict[str, str], key: str | None = None
) -> httpx.Response:
    return await c.client.request(
        route.method,
        route.path,
        json=route.body,
        headers={**headers, "Idempotency-Key": key or str(uuid7())},
    )


def counts(c: Catalog) -> dict[str, int]:
    with owner_tenant_transaction(c.owner_conn, c.tenant):
        found: dict[str, int] = {}
        for table in TABLES:
            row = c.owner_conn.execute(
                f"select count(*) from gba.{table} where tenant_id = %s",
                (c.tenant,),
            ).fetchone()
            assert row is not None
            found[table] = int(row[0])
        return found


async def refused_everywhere(
    c: Catalog, items: list[Route], headers: dict[str, str], status: int = 403
) -> None:
    before = counts(c)
    outcome = {item.name: (await call(c, item, headers)).status_code for item in items}
    assert outcome == {item.name: status for item in items}
    assert counts(c) == before


def member(c: Catalog, role: str, location: UUID | None = None) -> tuple[FakeUser, UUID]:
    user = seed_user(c.owner_conn, f"property-access-{role}-{uuid7()}")
    membership = add_membership(
        c.owner_conn, tenant_id=c.tenant, user_id=user.user_id, role=role, location_id=location
    )
    return user, membership


def bearer(c: Catalog, user: FakeUser) -> dict[str, str]:
    return c.idp.bearer(user.subject, email=user.email)


async def test_matrix_covers_every_property_route(
    enabled: Catalog, agreements: Agreements, app_pool: RuntimePool
) -> None:
    e = await estate(enabled, agreements)
    app = create_app(
        Settings(environment="test"), pool=app_pool, token_verifier=enabled.idp.verifier()
    )
    prefix = "/v1/businesses/{business_id}/property/"
    declared = sorted(
        f"{method.upper()} {path}"
        for path, operations in app.openapi()["paths"].items()
        if path.startswith(prefix)
        for method in operations
    )
    covered = [
        f"{item.method} /v1/businesses/{{business_id}}/property{item.template}"
        for item in routes(enabled, e)
    ]
    assert sorted(covered) == declared
    assert len(declared) == 31


async def test_other_company_lesser_roles_and_support_are_refused_and_write_nothing(
    enabled: Catalog, agreements: Agreements, manager_b: FakeUser
) -> None:
    e = await estate(enabled, agreements)
    items = routes(enabled, e)
    await refused_everywhere(enabled, items, bearer(enabled, manager_b))
    for role in ("artist", "front_desk"):
        user, _ = member(enabled, role)
        await refused_everywhere(enabled, items, bearer(enabled, user))
    # Platform support is not a company role and holds no Property permission.
    support = seed_user(enabled.owner_conn, f"property-access-support-{uuid7()}")
    grant_platform_admin(enabled.owner_conn, user_id=support.user_id, granted_by="property-test")
    await refused_everywhere(enabled, items, bearer(enabled, support))
    # The company's own manager reads all of it.
    for item in items:
        if item.method == "GET":
            response = await call(enabled, item, enabled.headers)
            expected = 403 if item.permission == DELEGATE else 200
            assert response.status_code == expected, (item.name, response.text)


async def test_branch_managers_read_their_branch_and_manage_nothing(
    enabled: Catalog, agreements: Agreements
) -> None:
    e = await estate(enabled, agreements)
    items = routes(enabled, e)
    home, _ = member(enabled, "manager", enabled.world.a.location_id)
    other_branch, _ = seed_other_branch(enabled.owner_conn, enabled.world.a)
    away, _ = member(enabled, "manager", other_branch)
    reads = [item for item in items if item.permission == READ]
    manages = [item for item in items if item.permission != READ]
    assert (len(reads), len(manages)) == (8, 23)
    for item in reads:
        response = await call(enabled, item, bearer(enabled, home))
        assert response.status_code == 200, (item.name, response.text)
    await refused_everywhere(enabled, manages, bearer(enabled, home))
    await refused_everywhere(enabled, manages, bearer(enabled, away))
    seen: dict[str, int] = {}
    for item in reads:
        response = await call(enabled, item, bearer(enabled, away))
        seen[item.name] = response.status_code
        if response.status_code == 200:
            assert response.json()["items"] == [], item.name
    assert sorted(seen.values()) == [200, 200, 200, 200, 404, 404, 404, 404], seen


async def test_suspended_and_revoked_members_lose_every_route_and_their_replays(
    enabled: Catalog, agreements: Agreements
) -> None:
    e = await estate(enabled, agreements)
    items = routes(enabled, e)
    boss, _ = member(enabled, "owner")
    worker, membership = member(enabled, "manager")
    headers = bearer(enabled, worker)
    revision = next(
        item for item in items if item.name.startswith("PUT") and "/listings/" in item.path
    )
    first = await call(enabled, revision, headers, key="access-listing-revision")
    assert first.status_code == 200, first.text

    async def status(action: str) -> httpx.Response:
        return await enabled.client.post(
            f"/v1/salons/{enabled.tenant}/members/{membership}/{action}",
            headers=bearer(enabled, boss),
        )

    assert (await status("suspend")).status_code == 200
    await refused_everywhere(enabled, items, headers)
    replay = await call(enabled, revision, headers, key="access-listing-revision")
    assert replay.status_code == 403, replay.text

    assert (await status("reactivate")).status_code == 200
    replay = await call(enabled, revision, headers, key="access-listing-revision")
    assert (replay.status_code, replay.json()) == (200, first.json())
    for item in items:
        if item.method == "GET":
            response = await call(enabled, item, headers)
            expected = 403 if item.permission == DELEGATE else 200
            assert response.status_code == expected, (item.name, response.text)

    assert (await status("revoke")).status_code == 200
    await refused_everywhere(enabled, items, headers)
    replay = await call(enabled, revision, headers, key="access-listing-revision")
    assert replay.status_code == 403, replay.text
    assert (await status("reactivate")).status_code == 409

    history = await enabled.client.get(
        f"/v1/businesses/{enabled.tenant}/property/listings/{e.object_id}/history",
        headers=enabled.headers,
    )
    assert history.is_success, history.text
    authors = [item["recorded_by"] for item in history.json()["items"]]
    assert str(worker.user_id) in authors, history.json()
