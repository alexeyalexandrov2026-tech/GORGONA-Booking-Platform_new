"""O1: the construction module, projects and estimates (package O, BUILD-01; FAKE data only).

ADR-0035 and docs/plan/PACKAGE_O1_DESIGN_2026-10-30.md: a project has one currency; estimate
versions are insert-only; a proposal is stamped once on the latest version; totals are derived.
"""

from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.business import modules
from gorgona_booking.business.readiness_registry import Readiness
from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import add_membership
from tests.integration import test_management_api as shared
from tests.integration.booking_support import BookingWorld
from tests.integration.configuration_support import Config
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.seed import FakeUser, seed_other_branch, seed_user
from tests.integration.test_counterparties import card
from tests.integration.test_l8b2_finance_races import race
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
manager_b = shared.manager_b
__all__ = ["client", "idp", "manager_a", "manager_b"]
ENABLED = ["booking_resources", "counterparties", "finance", "finance_documents", "construction"]
CHICAGO = "America/Chicago"


def error(response: httpx.Response) -> tuple[int, str]:
    return response.status_code, response.json()["error"]["code"]


def line(
    description: str = "FAKE drywall",
    *,
    quantity: str = "10",
    cost: int = 1500,
    price: int = 2500,
    kind: str = "material",
    phase: str = "Framing",
    unit: str = "sheet",
) -> dict[str, Any]:
    return {
        "kind": kind,
        "description": description,
        "phase": phase,
        "quantity": quantity,
        "unit": unit,
        "unit_cost_minor": cost,
        "unit_price_minor": price,
    }


@dataclass(frozen=True)
class Construction:
    client: httpx.AsyncClient
    world: BookingWorld
    owner_conn: psycopg.Connection
    idp: FakeIdp
    headers: dict[str, str]
    customer: UUID

    @property
    def tenant(self) -> UUID:
        return self.world.a.tenant_id

    @property
    def base(self) -> str:
        return f"/v1/businesses/{self.tenant}/construction"

    async def send(
        self,
        method: str,
        path: str,
        body: dict[str, Any],
        headers: dict[str, str] | None = None,
        key: str | None = None,
    ) -> httpx.Response:
        return await self.client.request(
            method,
            self.base + path,
            json={"schema_version": 1, **body},
            headers={**(headers or self.headers), "Idempotency-Key": key or str(uuid7())},
        )

    async def get(self, path: str, headers: dict[str, str] | None = None) -> httpx.Response:
        return await self.client.get(self.base + path, headers=headers or self.headers)

    async def project(
        self,
        project_id: UUID,
        revision: int = 0,
        headers: dict[str, str] | None = None,
        **changes: Any,
    ) -> httpx.Response:
        body = {
            "expected_revision": revision,
            "number": f"FAKE-CP-{project_id.hex[-8:]}",
            "name": "FAKE kitchen remodel",
            "customer_id": str(self.customer),
            "location_id": str(self.world.a.location_id),
            "site_address": "FAKE 1 Main St, Springfield",
            "time_zone": CHICAGO,
            "currency": "USD",
            **changes,
        }
        return await self.send("PUT", f"/projects/{project_id}", body, headers)

    async def estimate(
        self,
        project_id: UUID,
        lines: list[dict[str, Any]],
        based_on: int = 0,
        headers: dict[str, str] | None = None,
        key: str | None = None,
    ) -> httpx.Response:
        return await self.send(
            "POST",
            f"/projects/{project_id}/estimates",
            {"based_on": based_on, "note": "FAKE scope", "lines": lines},
            headers,
            key,
        )

    async def propose(self, project_id: UUID, version: int) -> httpx.Response:
        return await self.send("POST", f"/projects/{project_id}/estimates/{version}/proposal", {})

    def member(self, role: str, location: UUID | None) -> dict[str, str]:
        user = seed_user(self.owner_conn, f"construction-{role}-{uuid7()}")
        add_membership(
            self.owner_conn,
            tenant_id=self.tenant,
            user_id=user.user_id,
            role=role,
            location_id=location,
        )
        return self.idp.bearer(user.subject, email=user.email)


@pytest.fixture
def accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only fixtures stand in for the package O acceptance; the registry stays implemented."""
    current = modules.MODULES_BY_ID["construction"]
    monkeypatch.setitem(
        modules.MODULES_BY_ID,
        "construction",
        current.model_copy(
            update={"enableable": True, "readiness": Readiness.TECHNICALLY_VERIFIED}
        ),
    )


@pytest.fixture
async def construction(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager_a: FakeUser,
    idp: FakeIdp,
    owner_conn: psycopg.Connection,
    accepted: None,
) -> Construction:
    config = Config(client, idp)
    await config.profile(manager_a, world.a.tenant_id, 0, [19])
    await config.publish(manager_a, world.a.tenant_id, 0, ENABLED)
    headers = idp.bearer(manager_a.subject, email=manager_a.email)
    customer = uuid7()
    saved = await client.put(
        f"/v1/businesses/{world.a.tenant_id}/counterparties/{customer}",
        json=card(display_name="FAKE Homeowner", roles=["customer"]),
        headers={**headers, "Idempotency-Key": str(uuid7())},
    )
    assert saved.status_code == 200, saved.text
    return Construction(client, world, owner_conn, idp, headers, customer)


# O1-01 ------------------------------------------------------------------------------


async def test_the_module_is_registered_but_cannot_be_enabled(
    client: httpx.AsyncClient, world: BookingWorld, manager_a: FakeUser, idp: FakeIdp
) -> None:
    headers = idp.bearer(manager_a.subject, email=manager_a.email)
    catalog = await client.get(
        f"/v1/businesses/{world.a.tenant_id}/module-catalog", headers=headers
    )
    assert catalog.status_code == 200, catalog.text
    (entry,) = [m for m in catalog.json()["modules"] if m["id"] == "construction"]
    assert (entry["readiness"], entry["enableable"]) == ("implemented", False)
    assert entry["depends_on"] == ["counterparties", "finance_documents"]
    base = f"/v1/businesses/{world.a.tenant_id}/construction"
    refused = await client.put(
        f"{base}/projects/{uuid7()}",
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "number": "FAKE-CP-NOT-READY",
            "name": "FAKE",
            "customer_id": str(uuid7()),
            "location_id": str(world.a.location_id),
            "site_address": "FAKE",
            "time_zone": CHICAGO,
            "currency": "USD",
        },
        headers={**headers, "Idempotency-Key": str(uuid7())},
    )
    assert error(refused) == (409, "MODULE_NOT_READY"), refused.text
    read = await client.get(f"{base}/projects", headers=headers)
    assert (read.status_code, read.json()["items"]) == (200, []), read.text


# O1-02 ------------------------------------------------------------------------------


async def test_a_project_is_replaced_with_its_revision(construction: Construction) -> None:
    project = uuid7()
    saved = await construction.project(project)
    assert saved.status_code == 200, saved.text
    view = saved.json()
    assert (view["project_id"], view["revision"], view["latest_version"]) == (str(project), 1, 0)
    assert (view["time_zone"], view["currency"]) == (CHICAGO, "USD")
    changed = await construction.project(project, revision=1, name="FAKE kitchen and bath")
    assert changed.status_code == 200, changed.text
    assert (changed.json()["revision"], changed.json()["name"]) == (2, "FAKE kitchen and bath")
    stale = await construction.project(project, revision=1)
    assert error(stale) == (409, "CONSTRUCTION_REVISION_CONFLICT")
    taken = await construction.project(uuid7(), number=view["number"])
    assert error(taken) == (409, "CONSTRUCTION_NUMBER_TAKEN")
    stranger = await construction.project(uuid7(), customer_id=str(uuid7()))
    assert error(stranger) == (422, "INVALID_REFERENCE")
    nowhere = await construction.project(uuid7(), time_zone="Mars/Olympus_Mons")
    assert error(nowhere) == (422, "CONSTRUCTION_TIME_ZONE_UNKNOWN")
    listed = await construction.get("/projects")
    assert [item["project_id"] for item in listed.json()["items"]] == [str(project)]


# O1-03 ------------------------------------------------------------------------------


async def test_estimate_versions_are_insert_only_with_derived_totals(
    construction: Construction,
) -> None:
    project = uuid7()
    assert (await construction.project(project)).status_code == 200
    first = await construction.estimate(
        project,
        [
            line(quantity="2.3333", cost=333, price=1001),
            line("FAKE carpenter", kind="labor", quantity="0.5", cost=1, price=1, unit="hour"),
        ],
    )
    assert first.status_code == 200, first.text
    one = first.json()
    assert (one["version"], one["based_on"], one["currency"], one["proposed_at"]) == (
        1,
        0,
        "USD",
        None,
    )
    # 2.3333 x 333 = 776.9889 -> 777; 2.3333 x 1001 = 2335.6333 -> 2336; 0.5 x 1 -> 1 (half up).
    assert [(item["cost_minor"], item["price_minor"]) for item in one["lines"]] == [
        (777, 2336),
        (1, 1),
    ]
    assert (one["cost_total_minor"], one["price_total_minor"]) == (778, 2337)
    assert one["lines"][0]["quantity"] == "2.3333"
    second = await construction.estimate(project, [line(quantity="12")], based_on=1)
    assert second.status_code == 200, second.text
    assert (second.json()["version"], second.json()["price_total_minor"]) == (2, 30000)
    stale = await construction.estimate(project, [line()], based_on=1)
    assert error(stale) == (409, "CONSTRUCTION_ESTIMATE_STALE")
    again = await construction.get(f"/projects/{project}/estimates/1")
    assert again.status_code == 200, again.text
    assert again.json() == one
    listed = await construction.get(f"/projects/{project}/estimates")
    assert [(i["version"], i["price_total_minor"]) for i in listed.json()["items"]] == [
        (1, 2337),
        (2, 30000),
    ]
    head = await construction.get(f"/projects/{project}")
    assert head.json()["latest_version"] == 2
    # The same key and body answer the stored result; another body is refused.
    key = str(uuid7())
    made = await construction.estimate(project, [line()], based_on=2, key=key)
    assert made.status_code == 200, made.text
    repeat = await construction.estimate(project, [line()], based_on=2, key=key)
    assert (repeat.status_code, repeat.json()["version"]) == (200, 3)
    reused = await construction.estimate(project, [line(quantity="3")], based_on=2, key=key)
    assert error(reused) == (422, "IDEMPOTENCY_KEY_REUSED")


# O1-04 ------------------------------------------------------------------------------


async def test_a_proposal_is_stamped_once_and_never_changes(
    construction: Construction, app_pool: RuntimePool
) -> None:
    project = uuid7()
    assert (await construction.project(project)).status_code == 200
    assert (await construction.estimate(project, [line()])).status_code == 200
    assert (
        await construction.estimate(project, [line(quantity="11")], based_on=1)
    ).status_code == 200
    older = await construction.propose(project, 1)
    assert error(older) == (409, "CONSTRUCTION_ESTIMATE_STALE")
    proposed = await construction.propose(project, 2)
    assert proposed.status_code == 200, proposed.text
    stamp = proposed.json()["proposed_at"]
    assert stamp is not None
    repeat = await construction.propose(project, 2)
    assert (repeat.status_code, repeat.json()["proposed_at"]) == (200, stamp)
    revised = await construction.estimate(project, [line(quantity="9")], based_on=2)
    assert revised.status_code == 200, revised.text
    kept = await construction.get(f"/projects/{project}/estimates/2")
    assert (kept.json()["proposed_at"], kept.json()["price_total_minor"]) == (stamp, 27500)
    tenant = construction.tenant
    for statement in (
        "update gba.construction_estimate_lines set quantity = 1",
        "delete from gba.construction_estimate_lines",
        "delete from gba.construction_estimate_versions",
        "update gba.construction_estimate_versions set note = 'FAKE'",
        "delete from gba.construction_projects",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with tenant_transaction(app_pool, tenant) as conn:
                await conn.execute(statement)
    with pytest.raises(psycopg.errors.CheckViolation):
        async with tenant_transaction(app_pool, tenant) as conn:
            await conn.execute(
                "update gba.construction_estimate_versions set proposed_at = now() "
                "where project_id = %s and version = 2",
                (project,),
            )


# O1-05 ------------------------------------------------------------------------------


async def test_the_currency_is_fixed_once_an_estimate_exists(construction: Construction) -> None:
    project = uuid7()
    assert (await construction.project(project)).status_code == 200
    euros = await construction.project(project, revision=1, currency="EUR")
    assert euros.status_code == 200, euros.text
    assert (await construction.estimate(project, [line()])).status_code == 200
    dollars = await construction.project(project, revision=2, currency="USD")
    assert error(dollars) == (409, "CONSTRUCTION_CURRENCY_FIXED")
    renamed = await construction.project(project, revision=2, currency="EUR", name="FAKE attic")
    assert renamed.status_code == 200, renamed.text


# O1-06 ------------------------------------------------------------------------------


async def _counts(pool: RuntimePool, tenant: UUID) -> tuple[int, ...]:
    async with tenant_transaction(pool, tenant) as conn:
        row = await (
            await conn.execute(
                "select (select count(*) from gba.construction_projects), "
                "(select count(*) from gba.construction_estimate_versions), "
                "(select count(*) from gba.construction_estimate_lines)"
            )
        ).fetchone()
    assert row is not None
    return tuple(int(n) for n in row)


async def test_without_the_module_writes_are_refused_and_scope_holds(
    construction: Construction,
    app_pool: RuntimePool,
    idp: FakeIdp,
    manager_a: FakeUser,
    manager_b: FakeUser,
) -> None:
    world = construction.world
    home = world.a.location_id
    away, _ = seed_other_branch(construction.owner_conn, world.a)
    here, there = uuid7(), uuid7()
    assert (await construction.project(here)).status_code == 200
    assert (await construction.project(there, location_id=str(away))).status_code == 200
    assert (await construction.estimate(here, [line()])).status_code == 200
    # A branch manager sees and changes only its branch's projects.
    branch = construction.member("manager", home)
    seen = await construction.get("/projects", headers=branch)
    assert [item["project_id"] for item in seen.json()["items"]] == [str(here)]
    hidden = await construction.get(f"/projects/{there}", headers=branch)
    assert error(hidden) == (404, "NOT_FOUND"), hidden.text
    outside = await construction.project(uuid7(), headers=branch, location_id=str(away))
    assert error(outside) == (422, "INVALID_REFERENCE"), outside.text
    # Another company sees nothing.
    other = idp.bearer(manager_b.subject, email=manager_b.email)
    foreign = await construction.get("/projects", headers=other)
    assert foreign.status_code in (403, 404), foreign.text
    assert await _counts(app_pool, world.b.tenant_id) == (0, 0, 0)
    # Turned off: writes are refused and write nothing; reads continue.
    tenant = construction.tenant
    before = await _counts(app_pool, tenant)
    assert before == (2, 1, 1)
    await Config(construction.client, idp).publish(
        manager_a, tenant, 1, ["booking_resources", "counterparties"]
    )
    off_project = await construction.project(uuid7())
    assert error(off_project) == (409, "MODULE_DISABLED"), off_project.text
    off_estimate = await construction.estimate(here, [line()], based_on=1)
    assert error(off_estimate) == (409, "MODULE_DISABLED"), off_estimate.text
    assert await _counts(app_pool, tenant) == before
    read = await construction.get(f"/projects/{here}/estimates")
    assert (read.status_code, len(read.json()["items"])) == (200, 1), read.text


# O1-07 ------------------------------------------------------------------------------


async def test_two_racing_saves_on_one_base_leave_one_version(
    construction: Construction, app_pool: RuntimePool, test_database: ProvisionedDatabase
) -> None:
    project = uuid7()
    assert (await construction.project(project)).status_code == 200
    answers = await race(
        app_pool,
        test_database,
        construction.tenant,
        "select 1 from gba.construction_projects where id = %s for update",
        project,
        [
            construction.estimate(project, [line(quantity="1")]),
            construction.estimate(project, [line(quantity="2")]),
        ],
    )
    assert sorted(a.status_code for a in answers) == [200, 409], [a.text for a in answers]
    (refused,) = [a for a in answers if a.status_code == 409]
    assert error(refused) == (409, "CONSTRUCTION_ESTIMATE_STALE")
    assert await _counts(app_pool, construction.tenant) == (1, 1, 1)
