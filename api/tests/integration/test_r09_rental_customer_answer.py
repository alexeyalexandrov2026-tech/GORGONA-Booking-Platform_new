"""RENT-01 R-09: initial rental answers require live, exact customer delegation."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid7

import pytest
from psycopg.errors import CheckViolation

from gorgona_booking.auth.principal import set_user_context
from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from tests.integration.seed import FakeUser, seed_other_branch
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
from tests.integration.test_r4b_rental_agreements import priced_booking

__all__ = ["accepted", "client", "idp", "manager_a", "owner_a", "owner_b", "parties", "rental"]
pytestmark = pytest.mark.anyio


async def _linked_booking(rental: Rental) -> str:
    _, booking = await priced_booking(rental)
    binding = await rental.put(
        f"/bookings/{booking}/customer-company",
        {"expected_revision": 0, "company_id": str(rental.world.b.tenant_id)},
    )
    assert binding.status_code == 200, binding.text
    return booking


async def test_customer_accepts_exact_base_quote_through_a_live_grant(
    rental: Rental, parties: Parties, owner_a: FakeUser, owner_b: FakeUser, app_pool: RuntimePool
) -> None:
    booking = await _linked_booking(rental)
    refused = await rental.get(f"/bookings/{booking}/customer-proposal/{uuid7()}")
    assert refused.status_code == 403, (
        f"R09_CUSTOMER_ROUTE_STATUS {refused.status_code}: {refused.text}"
    )

    grant = await parties.active_grant(
        owner_a,
        owner_b,
        [owner_b],
        permissions=["rental.customer_answer"],
        location_id=str(rental.world.a.location_id),
    )
    path = f"/bookings/{booking}/customer-proposal/{grant}"
    headers = parties.headers(owner_b)
    first = await rental.get(path, headers)
    assert first.status_code == 200, first.text
    offer = first.json()
    assert offer["status"] == "pending"
    assert offer["booking_id"] == booking
    assert offer["quote"]["total"] == 10_000
    assert "customer_id" not in offer
    assert "note" not in offer
    assert (await rental.get(f"/bookings/{booking}/agreement", headers)).status_code == 403
    wrong_grant = await rental.get(f"/bookings/{booking}/customer-proposal/{uuid7()}", headers)
    assert wrong_grant.status_code == 403, wrong_grant.text

    command = {
        "schema_version": 1,
        "binding_revision": offer["binding_revision"],
        "review_hash": offer["review_hash"],
        "signatory": "FAKE Renter",
    }
    url = rental.base + path
    for signatory in ("FAKE\x00Renter", "FAKE\x07Renter", "FAKE\nRenter"):
        unsafe = await rental.client.post(
            url, json={**command, "signatory": signatory}, headers=parties.headers(owner_b)
        )
        assert unsafe.status_code == 422, (signatory, unsafe.text)
    stale = await rental.client.post(
        url, json={**command, "review_hash": "0" * 64}, headers=headers
    )
    assert error(stale) == (409, "RENTAL_PROPOSAL_STALE"), stale.text
    relinked = await rental.put(
        f"/bookings/{booking}/customer-company",
        {"expected_revision": 1, "company_id": str(rental.world.b.tenant_id)},
    )
    assert relinked.status_code == 200, relinked.text
    stale_binding = await rental.client.post(url, json=command, headers=headers)
    assert error(stale_binding) == (409, "RENTAL_REVISION_CONFLICT"), stale_binding.text
    second = await rental.get(path, headers)
    assert second.status_code == 200, second.text
    command.update(
        binding_revision=second.json()["binding_revision"],
        review_hash=second.json()["review_hash"],
    )
    competing_headers = parties.headers(owner_b)
    first_answer, competing_answer = await asyncio.gather(
        rental.client.post(url, json=command, headers=headers),
        rental.client.post(url, json=command, headers=competing_headers),
    )
    assert sorted([first_answer.status_code, competing_answer.status_code]) == [200, 409]
    if first_answer.status_code == 200:
        saved, lost, winner_headers = first_answer, competing_answer, headers
    else:
        saved, lost, winner_headers = competing_answer, first_answer, competing_headers
    assert error(lost) == (409, "RENTAL_AGREEMENT_EXISTS"), lost.text
    receipt = saved.json()
    assert receipt["version"] == 1
    assert receipt["review_hash"] == command["review_hash"]
    replay = await rental.client.post(url, json=command, headers=winner_headers)
    assert replay.status_code == 200, replay.text
    assert replay.json() == receipt
    reopened = await rental.get(path, headers)
    assert reopened.status_code == 200, reopened.text
    assert reopened.json() == receipt
    # R-09 review: a re-save of the same company binding blocks neither the retry nor the receipt.
    resaved = await rental.put(
        f"/bookings/{booking}/customer-company",
        {"expected_revision": 2, "company_id": str(rental.world.b.tenant_id)},
    )
    assert resaved.status_code == 200, resaved.text
    retried = await rental.client.post(url, json=command, headers=winner_headers)
    assert (retried.status_code, retried.json()) == (200, receipt), retried.text
    shown = await rental.get(path, headers)
    assert (shown.status_code, shown.json()) == (200, receipt), shown.text

    async with tenant_transaction(app_pool, rental.tenant) as conn:
        proof = await (
            await conn.execute(
                "select source, customer_company_id, customer_grant_id, customer_binding_revision, "
                "customer_review_hash, recorded_by, total "
                "from gba.rental_agreement_versions where agreement_id = %s",
                (receipt["agreement_id"],),
            )
        ).fetchall()
        assert proof == [
            (
                "platform",
                rental.world.b.tenant_id,
                grant,
                2,
                command["review_hash"],
                owner_b.user_id,
                10_000,
            )
        ]

    revoked = await parties.act(owner_a, rental.tenant, grant, "revoke", 2)
    assert revoked.status_code == 200, revoked.text
    assert (await rental.client.post(url, json=command, headers=winner_headers)).status_code == 403


SCOPE = "rental_agreement_customer_scope"


async def _forge_acceptance(
    app_pool: RuntimePool,
    rental: Rental,
    booking: str,
    quote: dict[str, object],
    grant: object,
    owner: FakeUser,
    user: FakeUser,
    location: object,
) -> str | None:
    """A platform version 1 written by SQL as `user` in `location`'s branch scope."""
    agreement = uuid7()
    async with tenant_transaction(app_pool, rental.tenant) as conn:
        await set_user_context(conn, owner.user_id)
        async with conn.transaction(force_rollback=True):
            await conn.execute(
                "insert into gba.rental_agreements (tenant_id, id, booking_id, created_by) "
                "values (%s, %s, %s, %s)",
                (rental.tenant, agreement, booking, owner.user_id),
            )
            await set_user_context(conn, user.user_id)
            await conn.execute(
                "select pg_catalog.set_config('gba.location_id', %s, true)", (str(location),)
            )
            try:
                async with conn.transaction():
                    await conn.execute(
                        "insert into gba.rental_agreement_versions "
                        "(tenant_id, agreement_id, version, rate_card_id, starts_at, ends_at, "
                        "month_count, week_count, day_count, hour_count, rental_amount, "
                        "rental_days, total, source, accepted_by, accepted_at, recorded_by, "
                        "customer_company_id, customer_grant_id, customer_binding_revision, "
                        "customer_review_hash) "
                        "values (%s, %s, 1, %s, %s, %s, 0, 0, 2, 0, 10000, 2, 10000, "
                        "'platform', 'FAKE forged', now(), %s, %s, %s, 1, %s)",
                        (
                            rental.tenant,
                            agreement,
                            quote["rate_card_id"],
                            quote["starts_at"],
                            quote["ends_at"],
                            user.user_id,
                            rental.world.b.tenant_id,
                            grant,
                            "a" * 64,
                        ),
                    )
            except CheckViolation as exc:
                return exc.diag.constraint_name
    return "accepted"


async def test_branch_scoped_sql_rechecks_the_acceptance_grant(
    rental: Rental,
    parties: Parties,
    owner_a: FakeUser,
    owner_b: FakeUser,
    manager_a: FakeUser,
    app_pool: RuntimePool,
) -> None:
    """R-09 review: in a branch-scoped session the acceptance guard rechecks the grant (0126)."""
    booking = await _linked_booking(rental)
    here = rental.world.a.location_id
    away, _ = seed_other_branch(rental.owner_conn, rental.world.a)
    reading = await parties.active_grant(
        owner_a, owner_b, [owner_b], permissions=["rental.customer_answer"]
    )
    proposal = await rental.get(
        f"/bookings/{booking}/customer-proposal/{reading}", parties.headers(owner_b)
    )
    assert proposal.status_code == 200, proposal.text
    quote = proposal.json()["quote"]
    assert (await parties.act(owner_a, rental.tenant, reading, "revoke", 2)).status_code == 200

    elsewhere = await parties.active_grant(
        owner_a, owner_b, [owner_b], permissions=["rental.customer_answer"], location_id=str(away)
    )
    forged = await _forge_acceptance(
        app_pool, rental, booking, quote, elsewhere, owner_a, owner_b, here
    )
    assert forged == SCOPE
    assert (await parties.act(owner_a, rental.tenant, elsewhere, "revoke", 2)).status_code == 200

    live = await parties.active_grant(
        owner_a, owner_b, [owner_b], permissions=["rental.customer_answer"], location_id=str(here)
    )
    forged = await _forge_acceptance(
        app_pool, rental, booking, quote, live, owner_a, manager_a, here
    )
    assert forged == SCOPE
    assert (await parties.act(owner_a, rental.tenant, live, "revoke", 2)).status_code == 200
    forged = await _forge_acceptance(app_pool, rental, booking, quote, live, owner_a, owner_b, here)
    assert forged == SCOPE
    assert (await rental.get(f"/bookings/{booking}/agreement")).status_code == 404


async def test_customer_grant_does_not_cross_bindings_branches_or_expiry(
    rental: Rental, parties: Parties, owner_a: FakeUser, owner_b: FakeUser
) -> None:
    booking = await _linked_booking(rental)
    _, unrelated = await priced_booking(rental)
    headers = parties.headers(owner_b)
    away, _ = seed_other_branch(rental.owner_conn, rental.world.a)
    wrong_branch = await parties.active_grant(
        owner_a, owner_b, [owner_b], permissions=["rental.customer_answer"], location_id=str(away)
    )
    wrong_location = await rental.get(
        f"/bookings/{booking}/customer-proposal/{wrong_branch}", headers
    )
    assert wrong_location.status_code == 404, wrong_location.text
    revoked = await parties.act(owner_a, rental.tenant, wrong_branch, "revoke", 2)
    assert revoked.status_code == 200, revoked.text
    ends_at = datetime.now(UTC) + timedelta(seconds=5)
    expiring = await parties.active_grant(
        owner_a,
        owner_b,
        [owner_b],
        permissions=["rental.customer_answer"],
        expires_at=ends_at.isoformat(),
    )
    unlinked = await rental.get(f"/bookings/{unrelated}/customer-proposal/{expiring}", headers)
    assert unlinked.status_code == 404, unlinked.text
    path = f"/bookings/{booking}/customer-proposal/{expiring}"
    read = await rental.get(path, headers)
    assert read.status_code == 200, read.text
    await asyncio.sleep(max(0.0, (ends_at - datetime.now(UTC)).total_seconds()) + 0.2)
    refused = await rental.client.post(
        rental.base + path,
        json={
            "schema_version": 1,
            "binding_revision": read.json()["binding_revision"],
            "review_hash": read.json()["review_hash"],
            "signatory": "FAKE Renter",
        },
        headers=headers,
    )
    assert refused.status_code == 403, refused.text
    assert (await rental.get(f"/bookings/{booking}/agreement")).status_code == 404


async def test_database_refuses_platform_proof_for_an_unnamed_actor(
    rental: Rental, parties: Parties, owner_a: FakeUser, owner_b: FakeUser, app_pool: RuntimePool
) -> None:
    booking = await _linked_booking(rental)
    grant = await parties.active_grant(
        owner_a, owner_b, [owner_b], permissions=["rental.customer_answer"]
    )
    path = f"/bookings/{booking}/customer-proposal/{grant}"
    proposal = await rental.get(path, parties.headers(owner_b))
    assert proposal.status_code == 200, proposal.text
    read = proposal.json()
    quote = read["quote"]
    agreement = uuid7()
    async with tenant_transaction(app_pool, rental.tenant) as conn:
        await set_user_context(conn, owner_a.user_id)
        async with conn.transaction(force_rollback=True):
            await conn.execute(
                "insert into gba.rental_agreements (tenant_id, id, booking_id, created_by) "
                "values (%s, %s, %s, %s)",
                (rental.tenant, agreement, booking, owner_a.user_id),
            )
            with pytest.raises(CheckViolation) as exc:
                async with conn.transaction():
                    await conn.execute(
                        "insert into gba.rental_agreement_versions "
                        "(tenant_id, agreement_id, version, rate_card_id, starts_at, ends_at, "
                        "month_count, week_count, day_count, hour_count, rental_amount, "
                        "rental_days, "
                        "total, source, accepted_by, accepted_at, recorded_by, "
                        "customer_company_id, "
                        "customer_grant_id, customer_binding_revision, customer_review_hash) "
                        "values (%s, %s, 1, %s, %s, %s, 0, 0, 2, 0, 10000, 2, 10000, "
                        "'platform', 'FAKE unlisted actor', now(), %s, %s, %s, 1, %s)",
                        (
                            rental.tenant,
                            agreement,
                            quote["rate_card_id"],
                            quote["starts_at"],
                            quote["ends_at"],
                            owner_a.user_id,
                            rental.world.b.tenant_id,
                            grant,
                            read["review_hash"],
                        ),
                    )
        assert exc.value.diag.constraint_name == "rental_agreement_customer_scope"
