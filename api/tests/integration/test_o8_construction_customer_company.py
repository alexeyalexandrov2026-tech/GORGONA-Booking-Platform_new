"""A construction project's current customer can be bound to a company for O-09."""

from uuid import uuid7

import pytest

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
        "revision": 0,
        "company_id": None,
        "versions": [],
    }
    key = str(uuid7())
    first = {"expected_revision": 0, "company_id": foreign}
    saved = await c.send("PUT", path, first, key=key)
    assert saved.status_code == 200, saved.text
    assert (saved.json()["revision"], saved.json()["company_id"]) == (1, foreign)
    assert (await c.send("PUT", path, first, key=key)).json() == saved.json()
    stale = await c.send("PUT", path, {"expected_revision": 0, "company_id": None})
    assert error(stale) == (409, "CONSTRUCTION_REVISION_CONFLICT"), stale.text

    replacement = await _party(c, "FAKE New construction customer", ["customer"])
    updated = await c.project(project, revision=1, customer_id=str(replacement))
    assert updated.status_code == 200, updated.text
    current = (await c.get(path)).json()
    assert (current["customer_id"], current["revision"], current["company_id"]) == (
        str(replacement),
        1,
        None,
    )
    assert current["versions"][0]["company_id"] == foreign
    rebound = await c.send("PUT", path, {"expected_revision": 1, "company_id": foreign})
    assert rebound.status_code == 200, rebound.text
    assert rebound.json()["company_id"] == foreign
    revoked = await c.send("PUT", path, {"expected_revision": 2, "company_id": None})
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
    body = {"expected_revision": 0, "company_id": str(c.world.b.tenant_id)}
    for role, location in (("manager", c.world.a.location_id), ("front_desk", None)):
        headers = c.member(role, location)
        assert (await c.get(path, headers)).status_code == 403
        assert (await c.send("PUT", path, body, headers)).status_code == 403
    same_company = await c.send("PUT", path, {**body, "company_id": str(billing.tenant)})
    assert same_company.status_code == 422, same_company.text
    unknown = await c.send("PUT", path, {**body, "company_id": str(uuid7())})
    assert unknown.status_code == 422, unknown.text
    assert (await c.get(path)).json()["versions"] == []
