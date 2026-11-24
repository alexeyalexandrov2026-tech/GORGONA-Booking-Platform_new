"""RENT-01 R-09: a company binding is explicit, versioned and tenant-isolated."""

from uuid import uuid7

import pytest
from psycopg.errors import InsufficientPrivilege

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
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

__all__ = ["accepted", "client", "idp", "manager_a", "rental"]
pytestmark = pytest.mark.anyio


async def test_customer_company_binding_is_versioned_and_retry_safe(rental: Rental) -> None:
    _, booking = await priced_booking(rental)
    path = f"/bookings/{booking}/customer-company"
    initial = await rental.get(path)
    assert initial.status_code == 200, (
        f"R09_BINDING_GET_STATUS {initial.status_code}: {initial.text}"
    )
    assert initial.json()["booking_id"] == booking
    assert initial.json()["revision"] == 0
    assert initial.json()["company_id"] is None
    assert initial.json()["versions"] == []

    customer_company = str(rental.world.b.tenant_id)
    request = {"expected_revision": 0, "company_id": customer_company}
    key = str(uuid7())
    linked = await rental.put(path, request, key=key)
    assert linked.status_code == 200, linked.text
    assert (linked.json()["revision"], linked.json()["company_id"]) == (1, customer_company)
    replay = await rental.put(path, request, key=key)
    assert replay.status_code == 200, replay.text
    assert replay.json() == linked.json()
    reused = await rental.put(path, {**request, "company_id": None}, key=key)
    assert error(reused) == (422, "IDEMPOTENCY_KEY_REUSED"), reused.text

    stale = await rental.put(path, {**request, "company_id": None})
    assert error(stale) == (409, "RENTAL_REVISION_CONFLICT"), stale.text
    removed = await rental.put(path, {"expected_revision": 1, "company_id": None})
    assert removed.status_code == 200, removed.text
    assert (removed.json()["revision"], removed.json()["company_id"]) == (2, None)
    replay_after_removal = await rental.put(path, request, key=key)
    assert replay_after_removal.status_code == 200, replay_after_removal.text
    assert replay_after_removal.json() == linked.json()
    current = await rental.get(path)
    assert current.status_code == 200, current.text
    assert current.json() == removed.json()
    assert [(row["revision"], row["company_id"]) for row in removed.json()["versions"]] == [
        (1, customer_company),
        (2, None),
    ]


async def test_customer_company_binding_requires_company_wide_manager(rental: Rental) -> None:
    _, booking = await priced_booking(rental)
    path = f"/bookings/{booking}/customer-company"
    body = {"expected_revision": 0, "company_id": str(rental.world.b.tenant_id)}
    for role, branch in (("manager", rental.world.a.location_id), ("front_desk", None)):
        headers = rental.member(role, branch)
        assert (await rental.get(path, headers)).status_code == 403
        assert (await rental.put(path, body, headers)).status_code == 403
    for company in (rental.tenant, uuid7()):
        refused = await rental.put(path, {**body, "company_id": str(company)})
        assert refused.status_code == 422, refused.text
    assert (await rental.get(path)).json()["versions"] == []


async def test_customer_company_binding_is_append_only_and_isolated(
    rental: Rental, app_pool: RuntimePool
) -> None:
    _, booking = await priced_booking(rental)
    path = f"/bookings/{booking}/customer-company"
    company = rental.world.b.tenant_id
    linked = await rental.put(path, {"expected_revision": 0, "company_id": str(company)})
    assert linked.status_code == 200, linked.text
    async with tenant_transaction(app_pool, rental.tenant) as conn:
        for statement in (
            "update gba.rental_customer_companies set company_id = null where booking_id = %s",
            "delete from gba.rental_customer_companies where booking_id = %s",
        ):
            with pytest.raises(InsufficientPrivilege):
                async with conn.transaction():
                    await conn.execute(statement, (booking,))
    async with tenant_transaction(app_pool, company) as conn:
        rows = await (
            await conn.execute(
                "select revision from gba.rental_customer_companies where booking_id = %s",
                (booking,),
            )
        ).fetchall()
        assert rows == []
    assert (await rental.get(path)).json() == linked.json()
