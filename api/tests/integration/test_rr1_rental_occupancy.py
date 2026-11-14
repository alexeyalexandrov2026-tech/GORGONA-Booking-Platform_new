"""Package R review RR-01 through RR-04."""

from typing import Any
from uuid import uuid7

import psycopg
import pytest

from gorgona_booking.db.migrate import apply_migrations, load_migrations
from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.seed import seed_other_branch
from tests.integration.test_h3_upgrade import copy_fixture_data, snapshot
from tests.integration.test_l8b2_finance_races import race
from tests.integration.test_provider_routing_upgrade import checksums
from tests.integration.test_r1_rental_catalog import (
    Rental,
    accepted,
    client,
    error,
    idp,
    manager_a,
    manager_b,
    rental,
)
from tests.integration.test_r2_rental_bookings import at, book
from tests.integration.test_r3a_rental_assignment import assign, booked
from tests.integration.test_r4b_rental_agreements import accept
from tests.integration.test_r4c_rental_extensions import agreed, extend, holds
from tests.integration.test_r6a_rental_inspections import inspect
from tests.integration.test_r7b_upgrade import previous_r7a_database, previous_receipt_database

pytestmark = pytest.mark.anyio
__all__ = [
    "accepted",
    "client",
    "idp",
    "manager_a",
    "manager_b",
    "previous_r7a_database",
    "previous_receipt_database",
    "rental",
]


async def test_two_assignments_serialize_on_one_booking(
    rental: Rental, app_pool: RuntimePool, test_database: ProvisionedDatabase
) -> None:
    car, (first, second), _, booking = await agreed(rental, 2)
    answers = await race(
        app_pool,
        test_database,
        rental.tenant,
        "select 1 from gba.rental_classes where id = %s for update",
        car,
        [assign(rental, booking, first), assign(rental, booking, second)],
    )
    assert [answer.status_code for answer in answers] == [200, 200]
    assert sorted(row[0] for row in holds(rental, booking)) == ["confirmed", "released"]


async def test_the_next_handover_waits_for_the_first_return(rental: Rental) -> None:
    car, (unit,), customer, first = await agreed(rental, 1)
    second = await booked(rental, car, customer, at(3), at(5))
    assert (await accept(rental, second, [])).is_success
    for booking in (first, second):
        assert (await assign(rental, booking, unit)).is_success
    assert (await inspect(rental, first, "handover")).is_success
    blocked = await inspect(rental, second, "handover")
    assert error(blocked) == (409, "RENTAL_INSPECTION_STATE"), blocked.text
    assert (await inspect(rental, first, "return")).is_success
    assert (await inspect(rental, second, "handover")).is_success


@pytest.mark.parametrize("action", ["assign", "extend", "cancel"])
async def test_handover_keeps_a_returnable_assignment(rental: Rental, action: str) -> None:
    _, (unit, spare), _, booking = await agreed(rental, 2)
    assert (await assign(rental, booking, unit)).is_success
    assert (await inspect(rental, booking, "handover")).is_success
    before = holds(rental, booking)
    if action == "assign":
        response = await assign(rental, booking, spare)
    elif action == "extend":
        response = await extend(rental, booking, at(1), at(4))
    else:
        response = await rental.client.post(
            f"{rental.base}/bookings/{booking}/cancellation",
            json={"schema_version": 1, "reason": "FAKE cancellation"},
            headers={**rental.headers, "Idempotency-Key": str(uuid7())},
        )
    assert error(response) == (409, "RENTAL_BOOKING_HANDED_OVER"), response.text
    assert holds(rental, booking) == before
    assert (await inspect(rental, booking, "return")).is_success


@pytest.mark.parametrize("action", ["move", "retire"])
async def test_removing_capacity_preserves_the_booking(rental: Rental, action: str) -> None:
    car, (unit,), _, _ = await agreed(rental, 1)
    away, _ = seed_other_branch(rental.owner_conn, rental.world.a)
    move: dict[str, Any] = {"location_id": str(away)}
    update = move if action == "move" else {"state": "retired"}
    refused = await rental.unit(unit, car, revision=1, **update)
    assert error(refused) == (409, "RENTAL_UNAVAILABLE"), refused.text
    assert (await rental.unit(uuid7(), car)).is_success
    assert (await rental.unit(unit, car, revision=1, **update)).is_success


async def test_capacity_change_and_booking_share_the_class_lock(
    rental: Rental, app_pool: RuntimePool, test_database: ProvisionedDatabase
) -> None:
    car, (unit, spare), customer, _ = await agreed(rental, 2)
    answers = await race(
        app_pool,
        test_database,
        rental.tenant,
        "select 1 from gba.rental_classes where id = %s for update",
        car,
        [
            book(rental, car, customer, at(1), at(3)),
            rental.unit(unit, car, revision=1, state="retired"),
        ],
    )
    assert sorted(answer.status_code for answer in answers) == [200, 409]
    assert error(next(answer for answer in answers if not answer.is_success))[1] == (
        "RENTAL_UNAVAILABLE"
    )
    assert (await rental.get(f"/units/{spare}")).is_success


async def test_database_refuses_to_retire_committed_capacity(
    rental: Rental, app_pool: RuntimePool
) -> None:
    _, (unit,), _, _ = await agreed(rental, 1)
    with pytest.raises(psycopg.errors.CheckViolation) as refused:
        async with tenant_transaction(app_pool, rental.tenant) as conn:
            await conn.execute(
                "update gba.rental_units set state = 'retired', revision = revision + 1 "
                "where id = %s",
                (unit,),
            )
    assert refused.value.diag.constraint_name == "rental_units_availability_check"


async def test_nonempty_0107_upgrade_preserves_rental_facts(
    rental: Rental, test_database: ProvisionedDatabase, previous_r7a_database: ProvisionedDatabase
) -> None:
    _, (unit,), _, booking = await agreed(rental, 1)
    assert (await assign(rental, booking, unit)).is_success
    assert (await inspect(rental, booking, "handover")).is_success
    migrations = load_migrations()
    apply_migrations(previous_r7a_database.owner_dsn, migrations[:107])
    copy_fixture_data(test_database, previous_r7a_database)
    before = snapshot(previous_r7a_database)
    assert before["rental_bookings"][0] > 0
    assert before["rental_inspections"][0] > 0
    applied = checksums(previous_r7a_database)
    assert len(applied) == 107
    upgrade = apply_migrations(previous_r7a_database.owner_dsn, migrations[:108])
    assert [m.version for m in upgrade] == [108]
    assert snapshot(previous_r7a_database) == before
    assert checksums(previous_r7a_database)[:107] == applied
    assert apply_migrations(previous_r7a_database.owner_dsn, migrations[:108]) == []
