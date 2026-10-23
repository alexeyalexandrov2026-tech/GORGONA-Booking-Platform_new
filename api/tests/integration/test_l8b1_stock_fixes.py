"""L8b1: review fix R12 in the stock world (package L, BEAUTY-01; FAKE data only).

Design docs/plan/PACKAGE_L8_DESIGN_2026-10-23.md decision 65: a visit's materials are written off
from a storage place of the visit's own branch.
"""

from uuid import UUID

import pytest

from gorgona_booking.db.pool import RuntimePool
from tests.integration import test_l3_consumption as shared
from tests.integration.seed import seed_other_branch
from tests.integration.test_inventory import error
from tests.integration.test_l3_consumption import keyed, salon, started_visit
from tests.integration.test_stock import DAY, Stock
from tests.integration.test_stock_write_offs import received

pytestmark = pytest.mark.anyio
stock = shared.stock
inventory = shared.inventory
accepted = shared.accepted
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
kit = shared.kit
__all__ = ["accepted", "client", "idp", "inventory", "kit", "manager_a", "stock"]


# L8-13 (R12) ------------------------------------------------------------------------


async def test_materials_are_written_off_in_the_visits_branch(
    stock: Stock, kit: dict[str, UUID], app_pool: RuntimePool
) -> None:
    away, _ = seed_other_branch(stock.inventory.owner_conn, stock.inventory.world.a)
    remote = await stock.inventory.place(away, code="AWAY")
    # The other branch holds the same material, so only the branch can refuse the write-off.
    await received(stock, str(kit["dye"]), "100.0", "50.00", place_id=remote["place_id"])
    booking = await started_visit(stock, app_pool)
    done = await stock.inventory.client.post(
        f"{salon(stock)}/bookings/{booking}/complete", json={}, headers=keyed(stock)
    )
    assert done.status_code == 200, done.text
    before = stock.counts()
    path = f"{salon(stock)}/bookings/{booking}/consumption"
    body = {
        "legal_entity_id": str(stock.entity),
        "place_id": remote["place_id"],
        "document_date": DAY,
    }
    refused = await stock.inventory.client.post(path, json=body, headers=keyed(stock))
    assert error(refused) == (422, "VISIT_PLACE_OTHER_BRANCH"), refused.text
    assert stock.counts() == before
    # The visit's own branch is used as before.
    home = {**body, "place_id": stock.place["place_id"]}
    posted = await stock.inventory.client.post(path, json=home, headers=keyed(stock))
    assert posted.status_code == 200, posted.text
    assert posted.json()["stock_document_id"] is not None
