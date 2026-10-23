"""L8b2: two racing consumptions of one visit write it off once (package L, BEAUTY-01; FAKE data).

Design docs/plan/PACKAGE_L8_DESIGN_2026-10-23.md decision 69.
"""

from uuid import UUID

import pytest

from gorgona_booking.db.pool import RuntimePool
from tests.integration import test_l3_consumption as shared
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.test_l3_consumption import keyed, salon, started_visit
from tests.integration.test_l8b2_finance_races import race
from tests.integration.test_stock import DAY, Stock

pytestmark = pytest.mark.anyio
stock = shared.stock
inventory = shared.inventory
accepted = shared.accepted
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
kit = shared.kit
__all__ = ["accepted", "client", "idp", "inventory", "kit", "manager_a", "stock"]


async def test_two_racing_consumptions_write_the_visit_off_once(
    stock: Stock,
    kit: dict[str, UUID],
    app_pool: RuntimePool,
    test_database: ProvisionedDatabase,
) -> None:
    booking = await started_visit(stock, app_pool)
    done = await stock.inventory.client.post(
        f"{salon(stock)}/bookings/{booking}/complete", json={}, headers=keyed(stock)
    )
    assert done.status_code == 200, done.text
    before = stock.counts()
    path = f"{salon(stock)}/bookings/{booking}/consumption"
    body = {
        "legal_entity_id": str(stock.entity),
        "place_id": stock.place["place_id"],
        "document_date": DAY,
    }
    answers = await race(
        app_pool,
        test_database,
        stock.tenant,
        "select 1 from gba.visit_completions where booking_id = %s for update",
        booking,
        [
            stock.inventory.client.post(path, json=body, headers=keyed(stock, "l8b2-use-1")),
            stock.inventory.client.post(path, json=body, headers=keyed(stock, "l8b2-use-2")),
        ],
    )
    assert [a.status_code for a in answers] == [200, 200], [a.text for a in answers]
    documents = {a.json()["stock_document_id"] for a in answers}
    assert len(documents) == 1
    assert None not in documents
    after = stock.counts()
    assert after["stock_entries"] == before["stock_entries"] + 1
    value, on_account = stock.reconciled()
    assert value == on_account
