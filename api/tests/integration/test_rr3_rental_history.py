"""Package R review of the handover measurement context and settled agreement terms."""

import pytest

from gorgona_booking.db.pool import RuntimePool
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.seed import FakeUser
from tests.integration.test_l8b2_finance_races import race
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
from tests.integration.test_r3a_rental_assignment import assign
from tests.integration.test_r4b_rental_agreements import change
from tests.integration.test_r4c_rental_extensions import agreed
from tests.integration.test_r5b_rental_provider_holds import (
    connect,
    held,
    held_charge,
    link,
    receipt,
    writer_pool,
)
from tests.integration.test_r6a_rental_inspections import inspect
from tests.integration.test_r6b_rental_usage import usage
from tests.integration.test_r7a_rental_settlement import books, settle
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
__all__ = ["accepted", "client", "idp", "manager_a", "manager_b", "rental", "writer_pool"]


async def test_meter_survives_catalogue_edits_and_settlement(
    rental: Rental, app_pool: RuntimePool, idp: FakeIdp, manager_a: FakeUser
) -> None:
    book = await books(rental, app_pool, idp, manager_a)
    car, (unit,), _, booking = await agreed(rental, 1)
    assert (await assign(rental, booking, unit)).is_success
    assert (await inspect(rental, booking, "handover", meter=100)).is_success
    edited = await rental.klass(car, revision=1, meter_kind="none")
    assert edited.is_success, edited.text
    back = await inspect(rental, booking, "return", meter=160)
    assert back.is_success, back.text
    assert (await usage(rental, booking)).json()["distance"] == 60
    saved = await settle(rental, book, booking)
    assert saved.is_success, saved.text
    revised = await change(rental, booking, [])
    assert revised.status_code == 409, revised.text
    assert error(revised) == (409, "RENTAL_AGREEMENT_SETTLED")
    assert (await usage(rental, booking)).json()["distance"] == 60


async def test_settled_agreement_refuses_a_new_version(
    rental: Rental, app_pool: RuntimePool, idp: FakeIdp, manager_a: FakeUser
) -> None:
    book = await books(rental, app_pool, idp, manager_a)
    _, (unit,), _, booking = await agreed(rental, 1)
    assert (await assign(rental, booking, unit)).is_success
    assert (await inspect(rental, booking, "handover")).is_success
    assert (await inspect(rental, booking, "return")).is_success
    saved = await settle(rental, book, booking)
    assert saved.is_success, saved.text
    revised = await change(rental, booking, [])
    assert revised.status_code == 409, revised.text
    assert error(revised) == (409, "RENTAL_AGREEMENT_SETTLED")


async def test_one_sandbox_intent_across_two_rental_classes(
    rental: Rental,
    app_pool: RuntimePool,
    writer_pool: RuntimePool,
    test_database: ProvisionedDatabase,
    manager_a: FakeUser,
) -> None:
    routed = await connect(rental, app_pool, manager_a)
    first = await held(rental)
    second = await held(rental)
    evidence = await receipt(writer_pool, routed, held_charge())
    results = await race(
        app_pool,
        test_database,
        rental.tenant,
        "select 1 from gba.provider_receipt_connections where id = %s for update",
        routed.connection_id,
        [link(rental, first, 1, evidence), link(rental, second, 1, evidence)],
    )
    assert sorted(result.status_code for result in results) == [200, 409]
    refusal = next(result for result in results if not result.is_success)
    assert error(refusal) == (409, "RENTAL_SECURITY_EVIDENCE")
