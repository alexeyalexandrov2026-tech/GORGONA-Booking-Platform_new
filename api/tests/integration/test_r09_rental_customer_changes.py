"""R-09: agreement changes keep the offered price, grant and occupancy history."""

from uuid import uuid7

import pytest

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from tests.integration.seed import FakeUser
from tests.integration.test_delegations import Parties, owner_a, owner_b, parties
from tests.integration.test_r1_rental_catalog import (
    Rental,
    accepted,
    client,
    error,
    idp,
    manager_a,
    rental,
)
from tests.integration.test_r2_rental_bookings import at
from tests.integration.test_r3a_rental_assignment import assign
from tests.integration.test_r3b_rental_blocks import block
from tests.integration.test_r4b_rental_agreements import change
from tests.integration.test_r4c_rental_extensions import agreed, holds

__all__ = ["accepted", "client", "idp", "manager_a", "owner_a", "owner_b", "parties", "rental"]
pytestmark = pytest.mark.anyio


async def _binding(rental: Rental, booking: str) -> None:
    linked = await rental.put(
        f"/bookings/{booking}/customer-company",
        {"expected_revision": 0, "company_id": str(rental.world.b.tenant_id)},
    )
    assert linked.status_code == 200, linked.text


async def test_customer_accepts_only_the_latest_issued_terms(
    rental: Rental, parties: Parties, owner_a: FakeUser, owner_b: FakeUser, app_pool: RuntimePool
) -> None:
    _, _, _, booking = await agreed(rental, 1)
    await _binding(rental, booking)
    staff_path = f"/bookings/{booking}/customer-changes"
    first = {
        "expected_previous_offer_revision": 0,
        "expected_agreement_version": 1,
        "expected_binding_revision": 1,
        "extras": [{"code": "child_seat", "quantity": 1}],
        "reason": "FAKE customer asked for a seat",
    }
    key = str(uuid7())
    issued = await rental.put(staff_path, first, key=key)
    assert issued.status_code == 200, f"R09_ISSUE_CHANGE_STATUS {issued.status_code}: {issued.text}"
    replay = await rental.put(staff_path, first, key=key)
    assert replay.json() == issued.json()
    assert issued.json()["quote"]["total"] == 11_400
    assert (await rental.get(f"/bookings/{booking}/agreement")).json()["current_version"] == 1

    second = await rental.put(
        staff_path,
        {
            **first,
            "expected_previous_offer_revision": 1,
            "extras": [{"code": "child_seat", "quantity": 2}],
        },
    )
    assert second.status_code == 200, second.text
    grant = await parties.active_grant(
        owner_a,
        owner_b,
        [owner_b],
        permissions=["rental.customer_answer"],
        location_id=str(rental.world.a.location_id),
    )
    headers = parties.headers(owner_b)
    old = await rental.get(f"{staff_path}/1/{grant}", headers)
    assert error(old) == (409, "RENTAL_PROPOSAL_STALE"), old.text
    path = f"{staff_path}/2/{grant}"
    pending = await rental.get(path, headers)
    customer_view = pending.json()
    assert customer_view.pop("pickup_timezone")
    assert customer_view.pop("extra_names") == {"child_seat": "FAKE seat"}
    assert customer_view == second.json()
    assert customer_view["quote"]["total"] == 12_800
    assert (await rental.get(path)).status_code == 403

    body = {
        "schema_version": 1,
        "review_hash": pending.json()["review_hash"],
        "signatory": "FAKE customer",
    }
    wrong = await rental.client.post(
        rental.base + path, json={**body, "review_hash": "0" * 64}, headers=headers
    )
    assert error(wrong) == (409, "RENTAL_PROPOSAL_STALE"), wrong.text
    accepted_reply = await rental.client.post(rental.base + path, json=body, headers=headers)
    assert accepted_reply.status_code == 200, accepted_reply.text
    assert accepted_reply.json()["agreement_version"] == 2
    assert (
        await rental.client.post(
            rental.base + path,
            json=body,
            headers=headers,
        )
    ).json() == accepted_reply.json()
    assert (await rental.get(path, headers)).json() == accepted_reply.json()

    async with tenant_transaction(app_pool, rental.tenant) as conn:
        row = await (
            await conn.execute(
                "select v.version, v.source, v.total, v.customer_change_offer_revision, "
                "v.customer_grant_id, v.recorded_by "
                "from gba.rental_agreement_versions v join gba.rental_agreements a "
                "on (a.tenant_id, a.id) = (v.tenant_id, v.agreement_id) "
                "where a.booking_id = %s and v.version > 1",
                (booking,),
            )
        ).fetchall()
    assert row == [(2, "platform", 12_800, 2, grant, owner_b.user_id)]
    revoked = await parties.act(owner_a, rental.tenant, grant, "revoke", 2)
    assert revoked.status_code == 200, revoked.text
    assert (await rental.get(path, headers)).status_code == 403


async def test_period_acceptance_obeys_live_occupancy_and_moves_the_hold(
    rental: Rental, parties: Parties, owner_a: FakeUser, owner_b: FakeUser
) -> None:
    _, (unit, _), _, booking = await agreed(rental, 2)
    await _binding(rental, booking)
    assert (await assign(rental, booking, unit)).status_code == 200
    assert (await block(rental, unit, at(4), at(5))).status_code == 200
    grant = await parties.active_grant(
        owner_a, owner_b, [owner_b], permissions=["rental.customer_answer"]
    )
    staff_path = f"/bookings/{booking}/customer-changes"
    body = {
        "expected_previous_offer_revision": 0,
        "expected_agreement_version": 1,
        "expected_binding_revision": 1,
        "period": {"starts_at": at(1), "ends_at": at(5)},
        "extras": [],
        "reason": "FAKE period requested",
    }
    issued = await rental.put(staff_path, body)
    assert issued.status_code == 200, issued.text
    answer = {
        "schema_version": 1,
        "review_hash": issued.json()["review_hash"],
        "signatory": "FAKE renter",
    }
    refused = await rental.client.post(
        f"{rental.base}{staff_path}/1/{grant}", json=answer, headers=parties.headers(owner_b)
    )
    assert error(refused) == (409, "RENTAL_UNIT_BUSY"), refused.text
    assert [row[0] for row in holds(rental, booking)] == ["confirmed"]
    assert (await rental.get(f"/bookings/{booking}/agreement")).json()["current_version"] == 1

    acceptable = await rental.put(
        staff_path,
        {
            **body,
            "expected_previous_offer_revision": 1,
            "period": {"starts_at": at(1), "ends_at": at(4)},
        },
    )
    assert acceptable.status_code == 200, acceptable.text
    accepted_reply = await rental.client.post(
        f"{rental.base}{staff_path}/2/{grant}",
        json={**answer, "review_hash": acceptable.json()["review_hash"]},
        headers=parties.headers(owner_b),
    )
    assert accepted_reply.status_code == 200, accepted_reply.text
    assert accepted_reply.json()["agreement_version"] == 2
    assert [row[0] for row in holds(rental, booking)] == ["released", "confirmed"]
    current = await rental.get(f"/bookings/{booking}")
    assert current.json()["ends_at"] == "2031-06-04T10:00:00Z", current.text


async def test_offline_version_supersedes_an_unanswered_offer(
    rental: Rental, parties: Parties, owner_a: FakeUser, owner_b: FakeUser
) -> None:
    _, _, _, booking = await agreed(rental, 1)
    await _binding(rental, booking)
    staff_path = f"/bookings/{booking}/customer-changes"
    issued = await rental.put(
        staff_path,
        {
            "expected_previous_offer_revision": 0,
            "expected_agreement_version": 1,
            "expected_binding_revision": 1,
            "extras": [{"code": "child_seat", "quantity": 1}],
            "reason": "FAKE new seat",
        },
    )
    assert issued.status_code == 200, issued.text
    grant = await parties.active_grant(
        owner_a, owner_b, [owner_b], permissions=["rental.customer_answer"]
    )
    offline = await change(rental, booking, [{"code": "child_seat", "quantity": 2}])
    assert offline.status_code == 200, offline.text
    assert offline.json()["versions"][-1]["source"] == "email"
    declined = await rental.client.post(
        f"{rental.base}{staff_path}/1/{grant}",
        json={
            "schema_version": 1,
            "review_hash": issued.json()["review_hash"],
            "signatory": "FAKE customer",
        },
        headers=parties.headers(owner_b),
    )
    assert error(declined) == (409, "RENTAL_PROPOSAL_STALE"), declined.text
    assert (await rental.get(f"/bookings/{booking}/agreement")).json() == offline.json()
