"""Integration tests for SPECIAL-01 (0145): Education/Fitness capacity & session tracking,
Hospitality housekeeping & stay lifecycle, Events ticket capacity & cancellation conservation,
and branch isolation.
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
from tests.integration.test_counterparties import card
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp


@pytest.fixture
def enable_special_venues_for_test(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(
        modules.MODULES_BY_ID,
        "hospitality_events",
        modules.MODULES_BY_ID["hospitality_events"].model_copy(
            update={"enableable": True, "readiness": Readiness.TECHNICALLY_VERIFIED}
        ),
    )


async def test_education_fitness_hospitality_and_events_end_to_end(
    client: httpx.AsyncClient,
    idp: FakeIdp,
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    enable_special_venues_for_test: None,
) -> None:
    tenant_a = world.a.tenant_id
    home = world.a.location_id
    branch_b, _ = seed_other_branch(owner_conn, world.a)

    owner = seed_user(owner_conn, f"sp-owner-{uuid7()}")
    mgr_b = seed_user(owner_conn, f"sp-mgrb-{uuid7()}")
    add_membership(owner_conn, tenant_id=tenant_a, user_id=owner.user_id, role="owner")
    add_membership(
        owner_conn, tenant_id=tenant_a, user_id=mgr_b.user_id, role="manager", location_id=branch_b
    )
    owner_conn.commit()

    cfg = Config(client, idp)
    await cfg.profile(owner, tenant_a, 0, [12, 13, 17, 18])
    await cfg.publish(owner, tenant_a, 0, ["counterparties", "hospitality_events"])

    h = idp.bearer(owner.subject, email=owner.email)
    hb = idp.bearer(mgr_b.subject, email=mgr_b.email)
    biz = f"/v1/businesses/{tenant_a}"
    sv = f"{biz}/special-venues"

    guest_id = uuid7()
    assert (
        await client.put(
            f"{biz}/counterparties/{guest_id}",
            headers={**h, "Idempotency-Key": f"sp-cp-{uuid7()}"},
            json=card(display_name="Alex Guest", roles=["customer"]),
        )
    ).status_code == 200

    # 1. Education / Fitness: capacity=1, 2 sessions -> 2nd rejected, use 2 -> completed
    prog_id, enr1_id, enr2_id = uuid7(), uuid7(), uuid7()
    assert (
        await client.put(
            f"{sv}/programs/{prog_id}",
            headers={**h, "Idempotency-Key": f"sp-p-{uuid7()}"},
            json={
                "schema_version": 1,
                "expected_revision": 0,
                "location_id": str(home),
                "code": "PY_COHORT_01",
                "title": "Python Bootcamp Cohort 1",
                "program_kind": "education_cohort",
                "capacity": 1,
                "included_sessions": 2,
                "price_minor": 30000,
                "currency": "USD",
            },
        )
    ).status_code == 200
    assert (
        await client.put(
            f"{sv}/enrollments/{enr1_id}",
            headers={**h, "Idempotency-Key": f"sp-e1-{uuid7()}"},
            json={
                "schema_version": 1,
                "location_id": str(home),
                "program_id": str(prog_id),
                "participant_counterparty_id": str(guest_id),
            },
        )
    ).status_code == 200
    r_full = await client.put(
        f"{sv}/enrollments/{enr2_id}",
        headers={**h, "Idempotency-Key": f"sp-e2-{uuid7()}"},
        json={
            "schema_version": 1,
            "location_id": str(home),
            "program_id": str(prog_id),
            "participant_counterparty_id": str(guest_id),
        },
    )
    assert r_full.status_code == 409
    assert r_full.json()["error"]["code"] == "SPECIAL_CAPACITY_EXCEEDED"

    r_use = await client.post(
        f"{sv}/enrollments/{enr1_id}/use-sessions",
        headers={**h, "Idempotency-Key": f"sp-eu-{uuid7()}"},
        json={"schema_version": 1, "sessions_delta": 2, "result_grade": "A+"},
    )
    assert r_use.status_code == 200
    assert r_use.json()["status"] == "completed"
    assert r_use.json()["result_grade"] == "A+"

    # 2. Hospitality: room clean -> check_in (occupied) -> check_out (dirty) -> 2nd check_in blocked
    room_id, stay1_id, stay2_id = uuid7(), uuid7(), uuid7()
    assert (
        await client.put(
            f"{sv}/rooms/{room_id}",
            headers={**h, "Idempotency-Key": f"sp-rm-{uuid7()}"},
            json={
                "schema_version": 1,
                "expected_revision": 0,
                "location_id": str(home),
                "room_number": "402",
                "room_type": "Deluxe King",
                "max_guests": 2,
                "nightly_rate_minor": 22000,
                "currency": "USD",
                "housekeeping_status": "clean",
            },
        )
    ).status_code == 200
    for sid in (stay1_id, stay2_id):
        assert (
            await client.put(
                f"{sv}/stays/{sid}",
                headers={**h, "Idempotency-Key": f"sp-st-{sid}"},
                json={
                    "schema_version": 1,
                    "location_id": str(home),
                    "room_id": str(room_id),
                    "guest_counterparty_id": str(guest_id),
                    "check_in_date": "2026-11-01",
                    "check_out_date": "2026-11-03",
                    "guest_count": 2,
                },
            )
        ).status_code == 200
    assert (
        await client.post(
            f"{sv}/stays/{stay1_id}/transition",
            headers={**h, "Idempotency-Key": f"sp-ci1-{uuid7()}"},
            json={"schema_version": 1, "action": "check_in"},
        )
    ).json()["status"] == "checked_in"
    assert (
        await client.post(
            f"{sv}/stays/{stay1_id}/transition",
            headers={**h, "Idempotency-Key": f"sp-co1-{uuid7()}"},
            json={"schema_version": 1, "action": "check_out"},
        )
    ).json()["status"] == "checked_out"
    # Room is now dirty; checking in stay2 MUST fail until housekeeping marks it clean
    r_dirty = await client.post(
        f"{sv}/stays/{stay2_id}/transition",
        headers={**h, "Idempotency-Key": f"sp-ci2-{uuid7()}"},
        json={"schema_version": 1, "action": "check_in"},
    )
    assert r_dirty.status_code == 409
    assert r_dirty.json()["error"]["code"] == "SPECIAL_STATE_INVALID"

    # 3. Events: capacity = 2 -> issue 2 -> 3rd fails -> cancel 2 -> issue 2 succeeds & check_in
    ev_id, tk1_id, tk2_id, tk3_id = uuid7(), uuid7(), uuid7(), uuid7()
    assert (
        await client.put(
            f"{sv}/events/{ev_id}",
            headers={**h, "Idempotency-Key": f"sp-ev-{uuid7()}"},
            json={
                "schema_version": 1,
                "expected_revision": 0,
                "location_id": str(home),
                "code": "SYMPHONY_2026",
                "title": "Autumn Gala Concert",
                "event_date": "2026-11-15",
                "capacity": 2,
                "ticket_price_minor": 7500,
                "currency": "USD",
            },
        )
    ).status_code == 200
    assert (
        await client.put(
            f"{sv}/tickets/{tk1_id}",
            headers={**h, "Idempotency-Key": f"sp-tk1-{uuid7()}"},
            json={
                "schema_version": 1,
                "location_id": str(home),
                "event_id": str(ev_id),
                "attendee_counterparty_id": str(guest_id),
                "ticket_code": "TKT-001",
                "quantity": 2,
            },
        )
    ).status_code == 200
    assert (
        await client.put(
            f"{sv}/tickets/{tk2_id}",
            headers={**h, "Idempotency-Key": f"sp-tk2-{uuid7()}"},
            json={
                "schema_version": 1,
                "location_id": str(home),
                "event_id": str(ev_id),
                "attendee_counterparty_id": str(guest_id),
                "ticket_code": "TKT-002",
                "quantity": 1,
            },
        )
    ).status_code == 409
    assert (
        await client.post(
            f"{sv}/tickets/{tk1_id}/transition",
            headers={**h, "Idempotency-Key": f"sp-tkc-{uuid7()}"},
            json={"schema_version": 1, "action": "cancel"},
        )
    ).json()["status"] == "cancelled"
    assert (
        await client.put(
            f"{sv}/tickets/{tk3_id}",
            headers={**h, "Idempotency-Key": f"sp-tk3-{uuid7()}"},
            json={
                "schema_version": 1,
                "location_id": str(home),
                "event_id": str(ev_id),
                "attendee_counterparty_id": str(guest_id),
                "ticket_code": "TKT-003",
                "quantity": 2,
            },
        )
    ).status_code == 200
    assert (
        await client.post(
            f"{sv}/tickets/{tk3_id}/transition",
            headers={**h, "Idempotency-Key": f"sp-tki-{uuid7()}"},
            json={"schema_version": 1, "action": "check_in"},
        )
    ).json()["status"] == "checked_in"

    # Branch B isolation: Branch B manager cannot transition Branch A stay
    assert (
        await client.post(
            f"{sv}/stays/{stay2_id}/transition",
            headers={**hb, "Idempotency-Key": f"sp-brb-{uuid7()}"},
            json={"schema_version": 1, "action": "cancel"},
        )
    ).status_code == 404
