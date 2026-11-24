"""A named customer delegate may accept only its own project's latest proposal."""

from uuid import uuid7

import pytest

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from tests.integration.seed import FakeUser
from tests.integration.test_delegations import Parties, owner_a, owner_b, parties
from tests.integration.test_o1_construction_estimates import accepted, client, idp, line, manager_a
from tests.integration.test_o5_construction_billing import Billing, billing

__all__ = ["accepted", "billing", "client", "idp", "manager_a", "owner_a", "owner_b", "parties"]
pytestmark = pytest.mark.anyio


async def test_customer_answers_only_through_its_live_grant(
    billing: Billing, parties: Parties, owner_a: FakeUser, owner_b: FakeUser, app_pool: RuntimePool
) -> None:
    c = billing.c
    project, other = uuid7(), uuid7()
    for project_id in (project, other):
        assert (await c.project(project_id)).status_code == 200
        assert (await c.estimate(project_id, [line()])).status_code == 200
        assert (await c.propose(project_id, 1)).status_code == 200

    link = await c.send(
        "PUT",
        f"/projects/{project}/customer-company",
        {
            "expected_revision": 0,
            "expected_customer_generation": 1,
            "company_id": str(c.world.b.tenant_id),
        },
    )
    assert link.status_code == 200, link.text
    grant = await parties.active_grant(
        owner_a,
        owner_b,
        [owner_b],
        permissions=["construction.customer_answer"],
        location_id=str(c.world.a.location_id),
    )
    path = f"/projects/{project}/customer-proposal/{grant}"
    headers = parties.headers(owner_b)
    proposal = await c.get(path, headers)
    assert proposal.status_code == 200, proposal.text
    assert proposal.json()["price_total_minor"] == 25000
    assert "cost" not in proposal.text
    assert (await c.get(path)).status_code == 403
    assert (
        await c.get(f"/projects/{project}/customer-proposal/{uuid7()}", headers)
    ).status_code == 403
    assert (await c.get(f"/projects/{other}/customer-proposal/{grant}", headers)).status_code == 404
    assert (await c.get(f"/projects/{project}/contract", headers)).status_code == 403
    key = str(uuid7())
    answer = {"version": 1, "expected_customer_generation": 1, "signatory": "FAKE customer"}
    stale = await c.send("POST", path, {**answer, "expected_customer_generation": 2}, headers)
    assert stale.status_code == 409, stale.text
    saved = await c.send("POST", path, answer, headers, key)
    assert saved.status_code == 200, saved.text
    assert saved.json()["accepted"] is True
    assert "cost" not in saved.text
    assert (await c.send("POST", path, answer, headers, key)).json() == saved.json()
    contract = await c.get(f"/projects/{project}/contract")
    assert contract.json()["source"] == "platform"
    async with tenant_transaction(app_pool, c.world.a.tenant_id) as conn:
        proof = await (
            await conn.execute(
                "select customer_company_id, customer_grant_id, recorded_by "
                "from gba.construction_contracts where project_id=%s",
                (project,),
            )
        ).fetchone()
        assert proof == (c.world.b.tenant_id, grant, owner_b.user_id)
    revoked = await parties.act(owner_a, c.world.a.tenant_id, grant, "revoke", 2)
    assert revoked.status_code == 200, revoked.text
    assert (await c.send("POST", path, answer, headers, key)).status_code == 403
