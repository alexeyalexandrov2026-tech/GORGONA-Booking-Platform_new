"""A customer's acceptance binds a live grant and the reviewed scope of work."""

from uuid import uuid7

import pytest
from psycopg.errors import CheckViolation

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from tests.integration.seed import FakeUser
from tests.integration.test_delegations import Parties, owner_a, owner_b, parties
from tests.integration.test_o1_construction_estimates import accepted, client, idp, manager_a
from tests.integration.test_o4a_construction_execution import TWO_LINES, ago, measure, signed_at
from tests.integration.test_o4b_construction_quality import move, raise_item
from tests.integration.test_o5_construction_billing import Billing, billing, pay
from tests.integration.test_o6a_construction_acceptance import later

__all__ = ["accepted", "billing", "client", "idp", "manager_a", "owner_a", "owner_b", "parties"]
pytestmark = pytest.mark.anyio


async def test_customer_acceptance_checks_review_and_live_grant_before_write_and_replay(
    billing: Billing, parties: Parties, owner_a: FakeUser, owner_b: FakeUser, app_pool: RuntimePool
) -> None:
    c = billing.c
    project = await signed_at(c, TWO_LINES)
    linked = await c.send(
        "PUT",
        f"/projects/{project}/customer-company",
        {
            "expected_revision": 0,
            "expected_customer_generation": 1,
            "company_id": str(c.world.b.tenant_id),
        },
    )
    assert linked.status_code == 200, linked.text
    grant = await parties.active_grant(
        owner_a,
        owner_b,
        [owner_b],
        permissions=["construction.customer_answer"],
        location_id=str(c.world.a.location_id),
    )
    path = f"/projects/{project}/customer-acceptance/{grant}"
    headers = parties.headers(owner_b)
    first = await c.get(path, headers)
    assert first.status_code == 200, first.text
    assert "cost" not in first.text
    assert "material_id" not in first.text
    assert (await c.get(path)).status_code == 403
    assert (
        await c.get(f"/projects/{project}/customer-acceptance/{uuid7()}", headers)
    ).status_code == 403
    phase = {
        "scope": "phase",
        "phase": "Framing",
        "accepted_on": ago(1),
        "signatory": "FAKE customer delegate",
        "expected_customer_generation": 1,
        "expected_review_hash": first.json()["review_hash"],
    }
    unfinished = await c.send("POST", path, phase, headers)
    assert unfinished.status_code == 409, unfinished.text
    assert unfinished.json()["error"]["code"] == "CONSTRUCTION_NOT_COMPLETED"
    for position, quantity in ((1, "10"), (2, "3.3333")):
        assert (await measure(c, project, position, quantity, ago(2))).status_code == 200
    stale = await c.send("POST", path, phase, headers)
    assert stale.status_code == 409, stale.text
    assert stale.json()["error"]["code"] == "CONSTRUCTION_REVISION_CONFLICT"
    reviewed = (await c.get(path, headers)).json()
    final = {
        **phase,
        "scope": "final",
        "phase": None,
        "warranty_ends_on": later(365),
        "expected_review_hash": reviewed["review_hash"],
    }
    raised = await raise_item(c, project, phase=None)
    assert raised.status_code == 200, raised.text
    blocked_review = (await c.get(path, headers)).json()
    assert blocked_review["open_items"] == 1
    assert blocked_review["review_hash"] != reviewed["review_hash"]
    old_review = await c.send("POST", path, final, headers)
    assert old_review.status_code == 409, old_review.text
    assert old_review.json()["error"]["code"] == "CONSTRUCTION_REVISION_CONFLICT"
    final["expected_review_hash"] = blocked_review["review_hash"]
    blocked = await c.send("POST", path, final, headers)
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["error"]["code"] == "CONSTRUCTION_OPEN_ITEMS"
    assert (await move(c, project, 1, 0, "fixed")).status_code == 200
    assert (await move(c, project, 1, 1, "closed")).status_code == 200
    final["expected_review_hash"] = (await c.get(path, headers)).json()["review_hash"]
    unbilled = await c.send("POST", path, final, headers)
    assert unbilled.status_code == 409, unbilled.text
    assert unbilled.json()["error"]["code"] == "CONSTRUCTION_NOT_FULLY_BILLED"
    paid = await pay(billing, project, ago(1))
    assert paid.status_code == 200, paid.text
    reviewed = (await c.get(path, headers)).json()
    phase["expected_review_hash"] = reviewed["review_hash"]
    async with tenant_transaction(app_pool, billing.tenant) as conn:
        with pytest.raises(CheckViolation) as proof_error:
            async with conn.transaction():
                await conn.execute(
                    "insert into gba.construction_acceptances (tenant_id, project_id, number, "
                    "scope, phase, accepted_on, signatory, source, recorded_by, "
                    "customer_company_id, customer_grant_id, customer_review_hash) "
                    "values (%s, %s, 1, 'phase', 'Framing', %s, 'FAKE forged', 'platform', "
                    "%s, %s, %s, %s)",
                    (
                        billing.tenant,
                        project,
                        ago(1),
                        owner_b.user_id,
                        c.world.b.tenant_id,
                        grant,
                        reviewed["review_hash"],
                    ),
                )
        assert proof_error.value.diag.constraint_name == "construction_acceptance_customer_scope"
    wrong_generation = await c.send(
        "POST", path, {**phase, "expected_customer_generation": 2}, headers
    )
    assert wrong_generation.status_code == 409, wrong_generation.text
    key = str(uuid7())
    saved = await c.send("POST", path, phase, headers, key)
    assert saved.status_code == 200, saved.text
    assert saved.json()["source"] == "platform"
    assert saved.json()["review_hash"] == reviewed["review_hash"]
    assert (await c.send("POST", path, phase, headers, key)).json() == saved.json()
    conflicting = await c.send("POST", path, {**phase, "note": "FAKE changed note"}, headers, key)
    assert conflicting.status_code == 422, conflicting.text
    assert conflicting.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    reviewed = (await c.get(path, headers)).json()
    final["expected_review_hash"] = reviewed["review_hash"]
    final_key = str(uuid7())
    completed = await c.send("POST", path, final, headers, final_key)
    assert completed.status_code == 200, completed.text
    assert completed.json()["warranty_ends_on"] == later(365)
    async with tenant_transaction(app_pool, billing.tenant) as conn:
        rows = await (
            await conn.execute(
                "select scope, customer_company_id, customer_grant_id, recorded_by, "
                "customer_review_hash from gba.construction_acceptances where project_id=%s "
                "order by number",
                (project,),
            )
        ).fetchall()
        proof = (c.world.b.tenant_id, grant, owner_b.user_id)
        assert rows == [
            ("phase", *proof, phase["expected_review_hash"]),
            ("final", *proof, final["expected_review_hash"]),
        ]
        releases = await (
            await conn.execute(
                "select count(*) from gba.construction_retainage_releases where project_id=%s",
                (project,),
            )
        ).fetchone()
        assert releases == (0,)
    revoked = await parties.act(owner_a, billing.tenant, grant, "revoke", 2)
    assert revoked.status_code == 200, revoked.text
    assert (await c.get(path, headers)).status_code == 403
    assert (await c.send("POST", path, final, headers, final_key)).status_code == 403
