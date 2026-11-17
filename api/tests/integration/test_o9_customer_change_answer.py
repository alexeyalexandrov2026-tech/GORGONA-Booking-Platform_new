"""A construction customer can read and answer a specific change through its own grant."""

from uuid import uuid7

import psycopg
import pytest
from psycopg.errors import CheckViolation

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.seed import FakeUser, seed_other_branch
from tests.integration.test_delegations import Parties, owner_a, owner_b, parties
from tests.integration.test_l8b2_finance_races import race
from tests.integration.test_o1_construction_estimates import accepted, client, idp, manager_a
from tests.integration.test_o2_construction_contract import LOCK, add, change, decide, signed
from tests.integration.test_o5_construction_billing import Billing, billing

__all__ = ["accepted", "billing", "client", "idp", "manager_a", "owner_a", "owner_b", "parties"]
pytestmark = pytest.mark.anyio


async def test_customer_change_answer_uses_exact_grant_and_records_its_proof(
    billing: Billing,
    parties: Parties,
    owner_a: FakeUser,
    owner_b: FakeUser,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
) -> None:
    c = billing.c
    project = await signed(c)
    path = f"/projects/{project}/change-orders"
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
    for _ in range(2):
        assert (await change(c, project, [add()], days=2)).status_code == 200
    headers = parties.headers(owner_b)
    away, _ = seed_other_branch(owner_conn, c.world.a)
    wrong_branch_grant = await parties.active_grant(
        owner_a,
        owner_b,
        [owner_b],
        permissions=["construction.customer_answer"],
        location_id=str(away),
    )
    wrong_branch = f"{path}/1/customer-answer/{wrong_branch_grant}"
    assert (await c.get(wrong_branch, headers)).status_code == 404
    assert (
        await c.send(
            "POST",
            wrong_branch,
            {"decision": "approved", "expected_customer_generation": 1},
            headers,
        )
    ).status_code == 404
    revoked_branch = await parties.act(owner_a, billing.tenant, wrong_branch_grant, "revoke", 2)
    assert revoked_branch.status_code == 200, revoked_branch.text
    grant = await parties.active_grant(
        owner_a,
        owner_b,
        [owner_b],
        permissions=["construction.customer_answer"],
        location_id=str(c.world.a.location_id),
    )
    granted = f"{path}/1/customer-answer/{grant}"
    get = await c.get(granted, headers)
    assert get.status_code == 200, get.text
    assert get.json()["state"] == "proposed"
    assert get.json()["price_minor"] == 25000
    assert "cost" not in get.text
    assert "material_id" not in get.text
    assert (await c.get(granted)).status_code == 403
    assert (await c.get(f"{path}/1/customer-answer/{uuid7()}", headers)).status_code == 403
    assert (await c.get(f"{path}/1", headers)).status_code == 403
    unlinked = await signed(c)
    assert (await change(c, unlinked, [add()])).status_code == 200
    assert (
        await c.get(f"/projects/{unlinked}/change-orders/1/customer-answer/{grant}", headers)
    ).status_code == 404

    answer = {"decision": "approved", "expected_customer_generation": 1}
    assert (
        await c.send("POST", f"{path}/1/decision", {"decision": "approved", "source": "platform"})
    ).status_code == 422
    stale = await c.send("POST", granted, {**answer, "expected_customer_generation": 2}, headers)
    assert stale.status_code == 409, stale.text
    assert (
        await c.send("POST", granted, {**answer, "decision": "withdrawn"}, headers)
    ).status_code == 422
    key = str(uuid7())
    saved = await c.send("POST", granted, answer, headers, key)
    assert saved.status_code == 200, saved.text
    assert saved.json()["state"] == "approved"
    assert "cost" not in saved.text
    assert (await c.send("POST", granted, answer, headers, key)).json() == saved.json()
    async with tenant_transaction(app_pool, billing.tenant) as conn:
        with pytest.raises(CheckViolation) as error:
            async with conn.transaction():
                await conn.execute(
                    "insert into gba.construction_change_order_decisions (tenant_id, project_id, "
                    "number, decision, source, decided_by, customer_company_id, customer_grant_id) "
                    "values (%s, %s, 2, 'approved', 'platform', %s, %s, %s)",
                    (billing.tenant, project, owner_b.user_id, c.world.b.tenant_id, grant),
                )
        assert error.value.diag.constraint_name == "construction_change_decision_customer_scope"
    rejected = await c.send(
        "POST",
        f"{path}/2/customer-answer/{grant}",
        {**answer, "decision": "rejected", "note": "FAKE out of scope"},
        headers,
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["state"] == "rejected"
    async with tenant_transaction(app_pool, billing.tenant) as conn:
        rows = await (
            await conn.execute(
                "select decision, source, customer_company_id, customer_grant_id, decided_by, "
                "note from gba.construction_change_order_decisions where project_id=%s "
                "order by number",
                (project,),
            )
        ).fetchall()
        proof = ("platform", c.world.b.tenant_id, grant, owner_b.user_id)
        assert rows == [
            ("approved", *proof, None),
            ("rejected", *proof, "FAKE out of scope"),
        ]
    contract = await c.get(f"/projects/{project}/contract")
    assert contract.json()["approved_price_minor"] == 25000
    assert contract.json()["approved_days"] == 2
    revoked = await parties.act(owner_a, billing.tenant, grant, "revoke", 2)
    assert revoked.status_code == 200, revoked.text
    assert (await c.get(granted, headers)).status_code == 403
    assert (await c.send("POST", granted, answer, headers, key)).status_code == 403


async def test_delegated_approval_racing_staff_withdrawal_records_one_outcome(
    billing: Billing,
    parties: Parties,
    owner_a: FakeUser,
    owner_b: FakeUser,
    app_pool: RuntimePool,
    test_database: ProvisionedDatabase,
) -> None:
    c = billing.c
    project = await signed(c)
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
    proposed = await change(c, project, [add()])
    assert proposed.status_code == 200, proposed.text
    grant = await parties.active_grant(
        owner_a,
        owner_b,
        [owner_b],
        permissions=["construction.customer_answer"],
        location_id=str(c.world.a.location_id),
    )
    answers = await race(
        app_pool,
        test_database,
        billing.tenant,
        LOCK,
        project,
        [
            c.send(
                "POST",
                f"/projects/{project}/change-orders/1/customer-answer/{grant}",
                {"decision": "approved", "expected_customer_generation": 1},
                parties.headers(owner_b),
            ),
            decide(c, project, 1, "withdrawn"),
        ],
    )
    assert sorted(answer.status_code for answer in answers) == [200, 409], [
        answer.text for answer in answers
    ]
    (winner,) = [answer.json()["state"] for answer in answers if answer.status_code == 200]
    async with tenant_transaction(app_pool, billing.tenant) as conn:
        rows = await (
            await conn.execute(
                "select decision, source, customer_company_id, customer_grant_id "
                "from gba.construction_change_order_decisions where project_id=%s",
                (project,),
            )
        ).fetchall()
        expected = (
            ("approved", "platform", c.world.b.tenant_id, grant)
            if winner == "approved"
            else ("withdrawn", None, None, None)
        )
        assert rows == [expected]
