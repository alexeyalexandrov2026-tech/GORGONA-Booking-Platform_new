"""PROPERTY-01 5a: maintenance requests, approvals and separate FIN-03 obligations (FAKE data).

docs/plan/PACKAGE_PROPERTY01_MAINTENANCE_DESIGN_2026-11-20.md.
"""

import asyncio
from typing import Any
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from tests.integration import test_property_leases as lease_tests
from tests.integration.configuration_support import Config
from tests.integration.seed import FakeUser, seed_other_branch, seed_user
from tests.integration.test_agreements import Agreements
from tests.integration.test_inventory import Inventory
from tests.integration.test_property_catalog import Catalog
from tests.integration.test_property_move_in import lease_with_evidence
from tests.integration.test_stock import entity_with_book
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
agreements = lease_tests.agreements
catalog = lease_tests.catalog
client = lease_tests.client
enabled = lease_tests.enabled
idp = lease_tests.idp
manager_a = lease_tests.manager_a
manager_b = lease_tests.manager_b
__all__ = ["agreements", "catalog", "client", "enabled", "idp", "manager_a", "manager_b"]


async def make_parcel(c: Catalog, name: str) -> UUID:
    oid = uuid7()
    res = await c.put(oid, c.body("parcel", name=name))
    assert res.is_success, res.text
    return oid


def root(c: Catalog) -> str:
    return f"/v1/businesses/{c.tenant}/property/maintenance"


def request_body(object_id: UUID, **changes: Any) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "object_id": str(object_id),
        "lease_id": None,
        "category": "plumbing",
        "priority": "urgent",
        "title": "FAKE Leaking sink valve",
        "description": "FAKE Cold water shutoff valve under kitchen sink drips steadily.",
        **changes,
    }


async def create_request(
    c: Catalog,
    object_id: UUID,
    *,
    request_id: UUID | None = None,
    headers: dict[str, str] | None = None,
    key: str | None = None,
    **changes: Any,
) -> tuple[UUID, httpx.Response]:
    rid = request_id or uuid7()
    res = await c.client.put(
        f"{root(c)}/{rid}",
        json=request_body(object_id, **changes),
        headers={**(headers or c.headers), "Idempotency-Key": key or str(uuid7())},
    )
    return rid, res


async def post_event(
    c: Catalog,
    request_id: UUID,
    body: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
    key: str | None = None,
) -> httpx.Response:
    return await c.client.post(
        f"{root(c)}/{request_id}/events",
        json={"schema_version": 1, **body},
        headers={**(headers or c.headers), "Idempotency-Key": key or str(uuid7())},
    )


async def link_obligation(
    c: Catalog,
    request_id: UUID,
    book_id: UUID,
    invoice_document_id: UUID,
    *,
    note: str | None = "FAKE Valve replacement invoice",
    headers: dict[str, str] | None = None,
    key: str | None = None,
) -> httpx.Response:
    return await c.client.post(
        f"{root(c)}/{request_id}/obligations",
        json={
            "schema_version": 1,
            "book_id": str(book_id),
            "invoice_document_id": str(invoice_document_id),
            "note": note,
        },
        headers={**(headers or c.headers), "Idempotency-Key": key or str(uuid7())},
    )


async def make_book(
    c: Catalog, app_pool: RuntimePool, idp: FakeIdp, user: FakeUser
) -> tuple[UUID, dict[str, UUID]]:
    cfg = Config(c.client, idp)
    cur = await cfg.get(user, c.tenant)
    assert cur.status_code == 200, cur.text
    body = cur.json()
    mods = list(body["published"]["module_ids"])
    changed = False
    for mod in ("finance", "finance_documents"):
        if mod not in mods:
            mods.append(mod)
            changed = True
    if changed:
        await cfg.publish(user, c.tenant, body["published"]["version"], mods)
    inv = Inventory(c.client, c.world, idp, c.owner_conn, user, c.headers)
    _, book_id, chart = await entity_with_book(inv, app_pool, "FAKE")
    return book_id, chart


async def create_invoice(
    c: Catalog,
    book_id: UUID,
    chart: dict[str, UUID],
    counterparty_id: str,
    amount_str: str,
    *,
    direction: str = "payable",
    currency: str = "USD",
    issue: bool = True,
) -> UUID:
    doc_id = uuid7()
    control = chart["2000"] if direction == "payable" else chart["1200"]
    counter = chart["6100"] if direction == "payable" else chart["4100"]
    draft = await c.client.put(
        f"/v1/businesses/{c.tenant}/financial-documents/books/{book_id}/invoices/{doc_id}",
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "direction": direction,
            "counterparty_id": counterparty_id,
            "counterparty_revision": 1,
            "currency": currency,
            "invoice_date": "2026-06-01",
            "due_date": "2026-06-15",
            "control_account_id": str(control),
            "title": "FAKE Maintenance work invoice",
            "number": f"FAKE-PM-{doc_id.hex[-8:]}",
            "lines": [
                {
                    "line_id": str(uuid7()),
                    "counter_account_id": str(counter),
                    "description": "FAKE Repair labor and parts",
                    "amount": amount_str,
                }
            ],
        },
        headers={**c.headers, "Idempotency-Key": str(uuid7())},
    )
    assert draft.status_code == 200, draft.text
    if issue:
        issued = await c.client.post(
            f"/v1/businesses/{c.tenant}/financial-documents/books/{book_id}/invoices/{doc_id}/issue",
            json={
                "schema_version": 1,
                "expected_revision": 1,
                "entry_date": "2026-06-01",
                "attestation": "confirmed_account_treatment",
            },
            headers={**c.headers, "Idempotency-Key": str(uuid7())},
        )
        assert issued.status_code == 200, issued.text
    return doc_id


async def test_maintenance_lifecycle_and_separate_fin03_obligations(
    enabled: Catalog,
    agreements: Agreements,
    app_pool: RuntimePool,
    idp: FakeIdp,
    manager_a: FakeUser,
) -> None:
    lease_id, _, _ = await lease_with_evidence(enabled, agreements)
    lease_res = await enabled.client.get(
        f"{lease_tests.leases(enabled)}/{lease_id}", headers=enabled.headers
    )
    assert lease_res.is_success, lease_res.text
    unit_id = UUID(lease_res.json()["object_id"])

    contractor = await enabled.counterparty()
    other_contractor = await enabled.counterparty()
    book_id, chart = await make_book(enabled, app_pool, idp, manager_a)

    # 1. Create open maintenance request tied to unit and lease
    rid, created = await create_request(enabled, unit_id, lease_id=str(lease_id), key="pm-create-1")
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["request_id"] == str(rid)
    assert body["object_id"] == str(unit_id)
    assert body["lease_id"] == str(lease_id)
    assert body["state"] == "open"
    assert body["revision"] == 1
    assert body["approved_limit_minor"] is None
    assert body["currency"] is None
    assert body["contractor_id"] is None

    # Replay same idempotency key returns identical view; different body is 409
    replay = await enabled.client.put(
        f"{root(enabled)}/{rid}",
        json=request_body(unit_id, lease_id=str(lease_id)),
        headers={**enabled.headers, "Idempotency-Key": "pm-create-1"},
    )
    assert replay.status_code == 200
    assert replay.json() == body
    reused = await enabled.client.put(
        f"{root(enabled)}/{rid}",
        json=request_body(unit_id, lease_id=str(lease_id), title="FAKE Different title"),
        headers={**enabled.headers, "Idempotency-Key": "pm-create-1"},
    )
    assert reused.status_code == 422
    assert reused.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"

    # Cannot assign, complete or link obligation before approval
    bad_assign = await post_event(
        enabled, rid, {"action": "assign", "expected_revision": 1, "contractor_id": contractor}
    )
    assert bad_assign.status_code == 409
    bad_complete = await post_event(enabled, rid, {"action": "complete", "expected_revision": 1})
    assert bad_complete.status_code == 409

    # 2. Approve with 500.00 USD limit
    approved = await post_event(
        enabled,
        rid,
        {
            "action": "approve",
            "expected_revision": 1,
            "approved_limit_minor": 50000,
            "currency": "USD",
            "note": "FAKE Approved up to 500 USD",
        },
        key="pm-approve-1",
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["state"] == "approved"
    assert approved.json()["revision"] == 2
    assert approved.json()["approved_limit_minor"] == 50000
    assert approved.json()["currency"] == "USD"

    # Cannot complete or link obligation before assigning a contractor
    inv_early = await create_invoice(enabled, book_id, chart, contractor, "100.00")
    assert (await link_obligation(enabled, rid, book_id, inv_early)).status_code == 409
    assert (
        await post_event(enabled, rid, {"action": "complete", "expected_revision": 2})
    ).status_code == 409

    # 3. Assign contractor (and verify reassignment BEFORE obligations is allowed)
    assigned_tmp = await post_event(
        enabled,
        rid,
        {"action": "assign", "expected_revision": 2, "contractor_id": other_contractor},
    )
    assert assigned_tmp.status_code == 200, assigned_tmp.text
    assert assigned_tmp.json()["revision"] == 3
    assert assigned_tmp.json()["contractor_id"] == other_contractor

    assigned = await post_event(
        enabled,
        rid,
        {"action": "assign", "expected_revision": 3, "contractor_id": contractor},
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["revision"] == 4
    assert assigned.json()["state"] == "assigned"
    assert assigned.json()["contractor_id"] == contractor

    # 4. FIN-03 obligation separation checks
    # Draft invoice refused
    draft_inv = await create_invoice(enabled, book_id, chart, contractor, "100.00", issue=False)
    assert (await link_obligation(enabled, rid, book_id, draft_inv)).status_code == 422

    # Receivable invoice (e.g. rent/customer) refused
    recv_inv = await create_invoice(
        enabled, book_id, chart, contractor, "100.00", direction="receivable"
    )
    assert (await link_obligation(enabled, rid, book_id, recv_inv)).status_code == 422

    # Wrong contractor payable invoice refused
    wrong_party_inv = await create_invoice(enabled, book_id, chart, other_contractor, "100.00")
    assert (await link_obligation(enabled, rid, book_id, wrong_party_inv)).status_code == 422

    # Wrong currency payable invoice refused
    eur_inv = await create_invoice(enabled, book_id, chart, contractor, "100.00", currency="EUR")
    assert (await link_obligation(enabled, rid, book_id, eur_inv)).status_code == 422

    # Link first valid payable invoice (300.00 USD <= 500.00 USD)
    inv_1 = await create_invoice(enabled, book_id, chart, contractor, "300.00")
    linked_1 = await link_obligation(enabled, rid, book_id, inv_1, key="pm-obligation-1")
    assert linked_1.status_code == 200, linked_1.text
    ob1 = linked_1.json()
    assert ob1["number"] == 1
    assert ob1["amount_minor"] == 30000
    assert ob1["currency"] == "USD"
    assert ob1["invoice_document_id"] == str(inv_1)
    assert ob1["obligation_id"] is not None

    # Idempotent replay of obligation link returns same record
    replay_ob1 = await link_obligation(enabled, rid, book_id, inv_1, key="pm-obligation-1")
    assert replay_ob1.status_code == 200
    assert replay_ob1.json() == ob1

    # Duplicate link of same invoice with new key is refused (409)
    assert (await link_obligation(enabled, rid, book_id, inv_1)).status_code == 409

    # Once an obligation is linked, cancelling or switching contractor is refused (409)
    assert (
        await post_event(enabled, rid, {"action": "cancel", "expected_revision": 4})
    ).status_code == 409
    assert (
        await post_event(
            enabled,
            rid,
            {"action": "assign", "expected_revision": 4, "contractor_id": other_contractor},
        )
    ).status_code == 409

    # Exceeding approved limit (300 + 200.01 > 500.00) is refused (409)
    inv_over = await create_invoice(enabled, book_id, chart, contractor, "200.01")
    assert (await link_obligation(enabled, rid, book_id, inv_over)).status_code == 409

    # Exact remaining limit (300 + 200 = 500) succeeds
    inv_2 = await create_invoice(enabled, book_id, chart, contractor, "200.00")
    linked_2 = await link_obligation(enabled, rid, book_id, inv_2)
    assert linked_2.status_code == 200, linked_2.text
    assert linked_2.json()["number"] == 2
    assert linked_2.json()["amount_minor"] == 20000

    # 5. Complete work order; history and obligations list match
    completed = await post_event(
        enabled, rid, {"action": "complete", "expected_revision": 4, "note": "FAKE Verified dry"}
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["state"] == "completed"
    assert completed.json()["revision"] == 5

    # Cannot cancel after completion
    assert (
        await post_event(enabled, rid, {"action": "cancel", "expected_revision": 5})
    ).status_code == 409

    events_res = await enabled.client.get(f"{root(enabled)}/{rid}/events", headers=enabled.headers)
    assert events_res.status_code == 200, events_res.text
    assert [e["action"] for e in events_res.json()["items"]] == [
        "complete",
        "assign",
        "assign",
        "approve",
    ]

    obs_res = await enabled.client.get(
        f"{root(enabled)}/{rid}/obligations", headers=enabled.headers
    )
    assert obs_res.status_code == 200, obs_res.text
    assert sum(item["amount_minor"] for item in obs_res.json()["items"]) == 50000

    # 6. Changing owner and manager on property_parties preserves obligations and payee
    new_owner = await enabled.counterparty()
    new_mgr = await enabled.counterparty()
    unit_view = (
        await enabled.client.get(
            f"/v1/businesses/{enabled.tenant}/property/objects/{unit_id}", headers=enabled.headers
        )
    ).json()
    changed = await enabled.client.put(
        f"/v1/businesses/{enabled.tenant}/property/objects/{unit_id}",
        json={
            "schema_version": 1,
            "expected_revision": unit_view["revision"],
            "location_id": unit_view["location_id"],
            "kind": "unit",
            "parent_id": unit_view["parent_id"],
            "name": unit_view["name"],
            "owner_id": new_owner,
            "manager_id": new_mgr,
        },
        headers={**enabled.headers, "Idempotency-Key": str(uuid7())},
    )
    assert changed.status_code == 200, changed.text
    after_req = (await enabled.client.get(f"{root(enabled)}/{rid}", headers=enabled.headers)).json()
    assert after_req["contractor_id"] == contractor
    after_obs = (
        await enabled.client.get(f"{root(enabled)}/{rid}/obligations", headers=enabled.headers)
    ).json()["items"]
    assert len(after_obs) == 2
    assert all(item["invoice_document_id"] in {str(inv_1), str(inv_2)} for item in after_obs)


async def test_lease_mismatch_cancel_before_obligations_and_cross_request_duplicate(
    enabled: Catalog,
    agreements: Agreements,
    app_pool: RuntimePool,
    idp: FakeIdp,
    manager_a: FakeUser,
) -> None:
    lease_id, _, _ = await lease_with_evidence(enabled, agreements)
    parcel = await make_parcel(enabled, "FAKE Other Parcel")
    # Lease belongs to unit, not parcel -> 422
    _, bad_lease = await create_request(enabled, parcel, lease_id=str(lease_id))
    assert bad_lease.status_code == 422

    # Valid cancel flow before obligations
    rid_cancel, res = await create_request(enabled, parcel, category="general", priority="routine")
    assert res.status_code == 200
    cancelled = await post_event(
        enabled, rid_cancel, {"action": "cancel", "expected_revision": 1, "note": "FAKE Duplicate"}
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["state"] == "cancelled"

    # Same invoice cannot be linked across two different maintenance requests
    contractor = await enabled.counterparty()
    book_id, chart = await make_book(enabled, app_pool, idp, manager_a)
    inv = await create_invoice(enabled, book_id, chart, contractor, "150.00")
    r1, r1_res = await create_request(enabled, parcel)
    r2, r2_res = await create_request(enabled, parcel)
    assert r1_res.status_code == 200
    assert r2_res.status_code == 200
    for rid in (r1, r2):
        assert (
            await post_event(
                enabled,
                rid,
                {
                    "action": "approve",
                    "expected_revision": 1,
                    "approved_limit_minor": 20000,
                    "currency": "USD",
                },
            )
        ).status_code == 200
        assert (
            await post_event(
                enabled,
                rid,
                {"action": "assign", "expected_revision": 2, "contractor_id": contractor},
            )
        ).status_code == 200
    assert (await link_obligation(enabled, r1, book_id, inv)).status_code == 200
    assert (await link_obligation(enabled, r2, book_id, inv)).status_code == 409


async def test_concurrent_obligations_never_exceed_approved_limit(
    enabled: Catalog,
    app_pool: RuntimePool,
    idp: FakeIdp,
    manager_a: FakeUser,
) -> None:
    parcel = await make_parcel(enabled, "FAKE Race Parcel")
    contractor = await enabled.counterparty()
    book_id, chart = await make_book(enabled, app_pool, idp, manager_a)
    rid, res = await create_request(enabled, parcel, category="hvac")
    assert res.status_code == 200
    assert (
        await post_event(
            enabled,
            rid,
            {
                "action": "approve",
                "expected_revision": 1,
                "approved_limit_minor": 40000,
                "currency": "USD",
            },
        )
    ).status_code == 200
    assert (
        await post_event(
            enabled, rid, {"action": "assign", "expected_revision": 2, "contractor_id": contractor}
        )
    ).status_code == 200
    inv_a = await create_invoice(enabled, book_id, chart, contractor, "250.00")
    inv_b = await create_invoice(enabled, book_id, chart, contractor, "250.00")
    res_a, res_b = await asyncio.gather(
        link_obligation(enabled, rid, book_id, inv_a),
        link_obligation(enabled, rid, book_id, inv_b),
    )
    assert sorted((res_a.status_code, res_b.status_code)) == [200, 409]
    obs = (
        await enabled.client.get(f"{root(enabled)}/{rid}/obligations", headers=enabled.headers)
    ).json()["items"]
    assert len(obs) == 1
    assert obs[0]["amount_minor"] == 25000


async def test_database_immutability_and_isolation_guards(
    enabled: Catalog,
    app_pool: RuntimePool,
) -> None:
    parcel = await make_parcel(enabled, "FAKE Guard Parcel")
    rid, res = await create_request(enabled, parcel)
    assert res.status_code == 200

    # Branch manager of other branch sees empty list and 404
    other_branch, _ = seed_other_branch(enabled.owner_conn, enabled.world.a)
    away = seed_user(enabled.owner_conn, f"pm-away-{uuid7()}")
    from gorgona_booking.db.provisioning import add_membership

    add_membership(
        enabled.owner_conn,
        tenant_id=enabled.tenant,
        user_id=away.user_id,
        role="manager",
        location_id=other_branch,
    )
    away_headers = enabled.idp.bearer(away.subject, email=away.email)
    listed = await enabled.client.get(root(enabled), headers=away_headers)
    assert listed.status_code == 200
    assert listed.json()["items"] == []
    assert (
        await enabled.client.get(f"{root(enabled)}/{rid}", headers=away_headers)
    ).status_code == 404

    # Direct UPDATE of immutable request fields fails in PostgreSQL
    with pytest.raises(psycopg.Error):
        async with tenant_transaction(app_pool, enabled.tenant) as conn:
            await conn.execute(
                "update gba.property_maintenance_requests set title = 'FAKE tampered' "
                "where tenant_id = %s and id = %s",
                (enabled.tenant, rid),
            )


async def test_module_disablement_allows_replay_and_closeout_and_blocks_new_commitments(
    enabled: Catalog,
    app_pool: RuntimePool,
    idp: FakeIdp,
    manager_a: FakeUser,
) -> None:
    parcel = await make_parcel(enabled, "FAKE Disablement Parcel")
    contractor = await enabled.counterparty()
    book_id, chart = await make_book(enabled, app_pool, idp, manager_a)
    rid, res = await create_request(enabled, parcel, key="pm-disable-create")
    assert res.status_code == 200
    assert (
        await post_event(
            enabled,
            rid,
            {
                "action": "approve",
                "expected_revision": 1,
                "approved_limit_minor": 30000,
                "currency": "USD",
            },
            key="pm-disable-approve",
        )
    ).status_code == 200
    assert (
        await post_event(
            enabled,
            rid,
            {"action": "assign", "expected_revision": 2, "contractor_id": contractor},
        )
    ).status_code == 200
    inv = await create_invoice(enabled, book_id, chart, contractor, "100.00")

    # Disable property module
    cfg = Config(enabled.client, idp)
    cur = await cfg.get(manager_a, enabled.tenant)
    assert cur.status_code == 200, cur.text
    body = cur.json()
    mods = [m for m in body["published"]["module_ids"] if m != "property"]
    await cfg.publish(manager_a, enabled.tenant, body["published"]["version"], mods)

    # New request, new assign, and new obligation link are refused (409)
    _, blocked_new = await create_request(enabled, parcel)
    assert blocked_new.status_code == 409
    assert (
        await post_event(
            enabled,
            rid,
            {"action": "assign", "expected_revision": 3, "contractor_id": contractor},
        )
    ).status_code == 409
    assert (await link_obligation(enabled, rid, book_id, inv)).status_code == 409

    # Replay of earlier create key still returns original record
    replayed = await enabled.client.put(
        f"{root(enabled)}/{rid}",
        json=request_body(parcel),
        headers={**enabled.headers, "Idempotency-Key": "pm-disable-create"},
    )
    assert replayed.status_code == 200
    assert replayed.json()["request_id"] == str(rid)

    # Completing already-assigned work remains allowed after disablement
    completed = await post_event(enabled, rid, {"action": "complete", "expected_revision": 3})
    assert completed.status_code == 200
    assert completed.json()["state"] == "completed"
