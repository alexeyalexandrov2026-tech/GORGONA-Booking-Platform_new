"""L7b1: a visit's completion is read back for the visit desk (booking.read; FAKE data only)."""

import pytest

from gorgona_booking.db.pool import RuntimePool
from tests.integration import test_stock as shared
from tests.integration.test_inventory import error
from tests.integration.test_l3_consumption import keyed, salon, started_visit
from tests.integration.test_stock import Stock

pytestmark = pytest.mark.anyio
stock = shared.stock
inventory = shared.inventory
accepted = shared.accepted
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
__all__ = ["accepted", "client", "idp", "inventory", "manager_a", "stock"]


async def test_a_completion_reads_back_and_a_missing_one_is_not_found(
    stock: Stock, app_pool: RuntimePool
) -> None:
    booking = await started_visit(stock, app_pool)
    path = f"{salon(stock)}/bookings/{booking}/completion"
    missing = await stock.inventory.client.get(path, headers=stock.inventory.headers)
    assert error(missing) == (404, "VISIT_NOT_COMPLETED")
    done = await stock.inventory.client.post(
        f"{salon(stock)}/bookings/{booking}/complete", json={}, headers=keyed(stock)
    )
    assert done.status_code == 200, done.text
    read = await stock.inventory.client.get(path, headers=stock.inventory.headers)
    assert read.status_code == 200, read.text
    assert read.json() == done.json()
    # Anyone who reads bookings reads the completion; another company sees nothing.
    _, desk = stock.inventory.member("front_desk")
    assert (await stock.inventory.client.get(path, headers=desk)).status_code == 200
    foreign = await stock.inventory.client.get(
        f"/v1/salons/{stock.inventory.world.b.tenant_id}/bookings/{booking}/completion",
        headers=stock.inventory.headers,
    )
    assert foreign.status_code in (403, 404), foreign.text
