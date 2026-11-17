"""A construction project's current customer can be bound to a company for O-09."""

from uuid import uuid7

import pytest
from psycopg.errors import InsufficientPrivilege

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from tests.integration.test_o1_construction_estimates import accepted, client, error, idp, manager_a
from tests.integration.test_o3b_construction_costs import _party
from tests.integration.test_o5_construction_billing import Billing, billing

__all__ = ["accepted", "billing", "client", "idp", "manager_a"]
pytestmark = pytest.mark.anyio


async def test_customer_company_is_versioned_and_stops_matching_after_customer_change(
    billing: Billing,
) -> None:
    c = billing.c
    project = uuid7()
    assert (await c.project(project)).status_code == 200
    path = f"/projects/{project}/customer-company"
    foreign = str(c.world.b.tenant_id)
    initial = await c.get(path)
    assert initial.status_code == 200, initial.text
    assert initial.json() == {
        "schema_version": 1,
        "project_id": str(project),
        "customer_id": str(c.customer),
        "customer_generation": 1,
        "revision": 0,
        "company_id": None,
        "versions": [],
    }
    key = str(uuid7())
    first = {"expected_revision": 0, "expected_customer_generation": 1, "company_id": foreign}
    saved = await c.send("PUT", path, first, key=key)
    assert saved.status_code == 200, saved.text
    assert (saved.json()["revision"], saved.json()["company_id"]) == (1, foreign)
    assert (await c.send("PUT", path, first, key=key)).json() == saved.json()
    stale = await c.send("PUT", path, {**first, "company_id": None})
    assert error(stale) == (409, "CONSTRUCTION_REVISION_CONFLICT"), stale.text
    rename = await c.project(project, revision=1, name="FAKE new project name")
    assert rename.status_code == 200, rename.text
    unchanged = (await c.get(path)).json()
    assert (unchanged["customer_generation"], unchanged["company_id"]) == (1, foreign)

    replacement = await _party(c, "FAKE New construction customer", ["customer"])
    updated = await c.project(project, revision=2, customer_id=str(replacement))
    assert updated.status_code == 200, updated.text
    current = (await c.get(path)).json()
    assert (current["customer_id"], current["revision"], current["company_id"]) == (
        str(replacement),
        1,
        None,
    )
    assert current["versions"][0]["company_id"] == foreign
    assert current["customer_generation"] == 2
    old_customer = await c.send("PUT", path, {**first, "expected_revision": 1})
    assert error(old_customer) == (409, "CONSTRUCTION_REVISION_CONFLICT"), old_customer.text
    assert (await c.project(project, revision=3, customer_id=str(c.customer))).status_code == 200
    returned = (await c.get(path)).json()
    assert (returned["customer_generation"], returned["company_id"]) == (3, None)
    assert (await c.project(project, revision=4, customer_id=str(replacement))).status_code == 200
    rebound = await c.send(
        "PUT", path, {**first, "expected_revision": 1, "expected_customer_generation": 4}
    )
    assert rebound.status_code == 200, rebound.text
    assert rebound.json()["company_id"] == foreign
    revoked = await c.send(
        "PUT", path, {"expected_revision": 2, "expected_customer_generation": 4, "company_id": None}
    )
    assert revoked.status_code == 200, revoked.text
    view = revoked.json()
    assert view["company_id"] is None
    assert [row["revision"] for row in view["versions"]] == [1, 2, 3]
    assert [row["customer_id"] for row in view["versions"]] == [
        str(c.customer),
        str(replacement),
        str(replacement),
    ]


async def test_only_company_wide_construction_approvers_can_manage_the_link(
    billing: Billing,
) -> None:
    c = billing.c
    project = uuid7()
    assert (await c.project(project)).status_code == 200
    path = f"/projects/{project}/customer-company"
    body = {
        "expected_revision": 0,
        "expected_customer_generation": 1,
        "company_id": str(c.world.b.tenant_id),
    }
    for role, location in (("manager", c.world.a.location_id), ("front_desk", None)):
        headers = c.member(role, location)
        assert (await c.get(path, headers)).status_code == 403
        assert (await c.send("PUT", path, body, headers)).status_code == 403
    same_company = await c.send("PUT", path, {**body, "company_id": str(billing.tenant)})
    assert same_company.status_code == 422, same_company.text
    unknown = await c.send("PUT", path, {**body, "company_id": str(uuid7())})
    assert unknown.status_code == 422, unknown.text
    assert (await c.get(path)).json()["versions"] == []


async def test_database_isolates_customer_links_and_preserves_their_history(
    billing: Billing,
    app_pool: RuntimePool,
) -> None:
    c = billing.c
    project = uuid7()
    assert (await c.project(project)).status_code == 200
    path = f"/projects/{project}/customer-company"
    linked = await c.send(
        "PUT",
        path,
        {
            "expected_revision": 0,
            "expected_customer_generation": 1,
            "company_id": str(c.world.b.tenant_id),
        },
    )
    assert linked.status_code == 200, linked.text
    async with tenant_transaction(app_pool, billing.tenant) as conn:
        for query in (
            "update gba.construction_customer_companies set company_id=null where project_id=%s",
            "delete from gba.construction_customer_companies where project_id=%s",
            "update gba.construction_projects set customer_generation=2 where id=%s",
        ):
            with pytest.raises(InsufficientPrivilege):
                async with conn.transaction():
                    await conn.execute(query, (project,))
    async with tenant_transaction(app_pool, c.world.b.tenant_id) as conn:
        rows = await (
            await conn.execute(
                "select revision from gba.construction_customer_companies where project_id=%s",
                (project,),
            )
        ).fetchall()
        assert rows == []
    view = (await c.get(path)).json()
    assert view["company_id"] == str(c.world.b.tenant_id)
    assert view["customer_generation"] == 1
