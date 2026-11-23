"""Integration tests for SPECIAL-03 (0147): Assets, inspections, work orders and safety
incidents across profiles 27, 28, 29, 32, 33, 34, including critical-incident safety lock,
decommissioned-asset guard, insert-only inspections and branch isolation.
"""

from uuid import uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.business import modules
from gorgona_booking.business.readiness_registry import Readiness
from gorgona_booking.db.provisioning import add_membership
from tests.integration import test_management_api as shared
from tests.integration.booking_support import BookingWorld
from tests.integration.configuration_support import Config
from tests.integration.seed import seed_other_branch, seed_user
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp


@pytest.fixture
def enable_assets_for_test(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(
        modules.MODULES_BY_ID,
        "assets",
        modules.MODULES_BY_ID["assets"].model_copy(
            update={"enableable": True, "readiness": Readiness.TECHNICALLY_VERIFIED}
        ),
    )


async def test_assets_lifecycle_critical_incident_lock_and_branch_isolation(
    client: httpx.AsyncClient,
    idp: FakeIdp,
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    enable_assets_for_test: None,
) -> None:
    tenant_a = world.a.tenant_id
    home = world.a.location_id
    branch_b, _ = seed_other_branch(owner_conn, world.a)

    owner = seed_user(owner_conn, f"asset-owner-{uuid7()}")
    mgr_b = seed_user(owner_conn, f"asset-mgrb-{uuid7()}")
    add_membership(owner_conn, tenant_id=tenant_a, user_id=owner.user_id, role="owner")
    add_membership(
        owner_conn, tenant_id=tenant_a, user_id=mgr_b.user_id, role="manager", location_id=branch_b
    )
    owner_conn.commit()

    cfg = Config(client, idp)
    await cfg.profile(owner, tenant_a, 0, [27, 28, 29, 32, 33, 34])
    await cfg.publish(owner, tenant_a, 0, ["assets"])

    h = idp.bearer(owner.subject, email=owner.email)
    hb = idp.bearer(mgr_b.subject, email=mgr_b.email)
    assets_url = f"/v1/businesses/{tenant_a}/assets"

    asset_id, insp_id, wo_id, inc_id, dead_id = uuid7(), uuid7(), uuid7(), uuid7(), uuid7()

    # 1. Register active utility infrastructure asset + verify idempotent replay
    k_asset = f"asset-create-{uuid7()}"
    asset_payload = {
        "schema_version": 1,
        "expected_revision": 0,
        "location_id": str(home),
        "asset_domain": "utility_infrastructure",
        "code": "SUB-NORTH-1",
        "name": "North Pump Station",
        "status": "active",
        "serial_or_parcel": "PARCEL-44A",
    }
    r1 = await client.put(
        f"{assets_url}/items/{asset_id}",
        headers={**h, "Idempotency-Key": k_asset},
        json=asset_payload,
    )
    assert r1.status_code == 200
    assert r1.json()["revision"] == 1
    r1_rep = await client.put(
        f"{assets_url}/items/{asset_id}",
        headers={**h, "Idempotency-Key": k_asset},
        json=asset_payload,
    )
    assert r1_rep.status_code == 200
    assert r1_rep.json() == r1.json()

    # 2. Record insert-only inspection with meter reading
    r_insp = await client.put(
        f"{assets_url}/inspections/{insp_id}",
        headers={**h, "Idempotency-Key": f"insp-{uuid7()}"},
        json={
            "schema_version": 1,
            "location_id": str(home),
            "asset_id": str(asset_id),
            "inspection_kind": "meter_reading",
            "outcome": "attention_required",
            "meter_reading": "5120.250",
            "notes": "Pressure gauge drift detected",
        },
    )
    assert r_insp.status_code == 200
    assert r_insp.json()["outcome"] == "attention_required"

    # 3. Open & complete work order linked to inspection; terminal order refuses modification
    r_wo = await client.put(
        f"{assets_url}/work-orders/{wo_id}",
        headers={**h, "Idempotency-Key": f"wo-open-{uuid7()}"},
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "location_id": str(home),
            "asset_id": str(asset_id),
            "inspection_id": str(insp_id),
            "work_kind": "corrective",
            "priority": "high",
            "status": "open",
            "summary": "Calibrate pressure valve",
        },
    )
    assert r_wo.status_code == 200
    r_wo_done = await client.put(
        f"{assets_url}/work-orders/{wo_id}",
        headers={**h, "Idempotency-Key": f"wo-done-{uuid7()}"},
        json={
            "schema_version": 1,
            "expected_revision": 1,
            "location_id": str(home),
            "asset_id": str(asset_id),
            "inspection_id": str(insp_id),
            "work_kind": "corrective",
            "priority": "high",
            "status": "completed",
            "summary": "Calibrate pressure valve",
            "completion_notes": "Replaced gasket and recalibrated",
        },
    )
    assert r_wo_done.status_code == 200
    assert r_wo_done.json()["completed_at"] is not None

    r_wo_reopen = await client.put(
        f"{assets_url}/work-orders/{wo_id}",
        headers={**h, "Idempotency-Key": f"wo-reopen-{uuid7()}"},
        json={
            "schema_version": 1,
            "expected_revision": 2,
            "location_id": str(home),
            "asset_id": str(asset_id),
            "inspection_id": str(insp_id),
            "work_kind": "corrective",
            "priority": "high",
            "status": "open",
            "summary": "Calibrate pressure valve",
        },
    )
    assert r_wo_reopen.status_code == 409

    # 4. Critical open incident auto-moves active asset to out_of_service and blocks reactivation
    r_inc = await client.put(
        f"{assets_url}/incidents/{inc_id}",
        headers={**h, "Idempotency-Key": f"inc-open-{uuid7()}"},
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "location_id": str(home),
            "asset_id": str(asset_id),
            "incident_kind": "environmental_spill",
            "severity": "critical",
            "status": "open",
            "description": "Coolant leak detected at manifold",
        },
    )
    assert r_inc.status_code == 200
    items_after_inc = (await client.get(f"{assets_url}/items", headers=h)).json()["items"]
    cur = next(i for i in items_after_inc if i["asset_id"] == str(asset_id))
    assert cur["status"] == "out_of_service"
    assert cur["revision"] == 2

    r_react_blocked = await client.put(
        f"{assets_url}/items/{asset_id}",
        headers={**h, "Idempotency-Key": f"react-blk-{uuid7()}"},
        json={**asset_payload, "expected_revision": 2, "status": "active"},
    )
    assert r_react_blocked.status_code == 409
    assert r_react_blocked.json()["error"]["code"] == "ASSET_CRITICAL_INCIDENT_OPEN"

    # Resolve incident -> asset can now return to active
    r_inc_res = await client.put(
        f"{assets_url}/incidents/{inc_id}",
        headers={**h, "Idempotency-Key": f"inc-res-{uuid7()}"},
        json={
            "schema_version": 1,
            "expected_revision": 1,
            "location_id": str(home),
            "asset_id": str(asset_id),
            "incident_kind": "environmental_spill",
            "severity": "critical",
            "status": "resolved",
            "description": "Coolant leak detected at manifold",
            "resolution_summary": "Contained, cleaned and verified",
        },
    )
    assert r_inc_res.status_code == 200
    assert r_inc_res.json()["resolved_at"] is not None

    r_react_ok = await client.put(
        f"{assets_url}/items/{asset_id}",
        headers={**h, "Idempotency-Key": f"react-ok-{uuid7()}"},
        json={**asset_payload, "expected_revision": 2, "status": "active"},
    )
    assert r_react_ok.status_code == 200
    assert r_react_ok.json()["status"] == "active"

    # 5. Decommissioned asset rejects new open work order
    assert (
        await client.put(
            f"{assets_url}/items/{dead_id}",
            headers={**h, "Idempotency-Key": f"dead-asset-{uuid7()}"},
            json={
                "schema_version": 1,
                "expected_revision": 0,
                "location_id": str(home),
                "asset_domain": "mining_equipment",
                "code": "RIG-OLD-9",
                "name": "Retired Drill",
                "status": "decommissioned",
            },
        )
    ).status_code == 200
    r_dead_wo = await client.put(
        f"{assets_url}/work-orders/{uuid7()}",
        headers={**h, "Idempotency-Key": f"dead-wo-{uuid7()}"},
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "location_id": str(home),
            "asset_id": str(dead_id),
            "work_kind": "preventive",
            "status": "open",
            "summary": "Routine service",
        },
    )
    assert r_dead_wo.status_code == 409

    # 6. Branch B manager sees zero home-branch assets, inspections, work orders or incidents
    assert (await client.get(f"{assets_url}/items", headers=hb)).json()["items"] == []
    assert (await client.get(f"{assets_url}/inspections", headers=hb)).json()["items"] == []
    assert (await client.get(f"{assets_url}/work-orders", headers=hb)).json()["items"] == []
    assert (await client.get(f"{assets_url}/incidents", headers=hb)).json()["items"] == []
