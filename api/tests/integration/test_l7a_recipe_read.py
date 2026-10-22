"""L7a: a service's recipe can be read back (catalog.read), not only replaced (FAKE data only)."""

from uuid import uuid7

import pytest

from tests.integration import test_stock as shared
from tests.integration.test_l3_consumption import recipe, revision_of, salon
from tests.integration.test_stock import Stock

pytestmark = pytest.mark.anyio
stock = shared.stock
inventory = shared.inventory
accepted = shared.accepted
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
__all__ = ["accepted", "client", "idp", "inventory", "manager_a", "stock"]


async def test_a_saved_recipe_reads_back_with_its_revision(stock: Stock) -> None:
    dye = await stock.inventory.item(name="FAKE dye", unit="ml", quantity_scale=1)
    base = stock.inventory.world.catalog_a.base_variant_id
    path = f"{salon(stock)}/services/{base}/materials"
    empty = await stock.inventory.client.get(path, headers=stock.inventory.headers)
    assert empty.status_code == 200, empty.text
    revision = await revision_of(stock, base)
    assert empty.json() == {"owner_id": str(base), "owner_revision": revision, "lines": []}
    saved = await recipe(
        stock, "services", base, [{"item_id": dye["item_id"], "quantity": "2.5"}], revision
    )
    assert saved.status_code == 200, saved.text
    read = await stock.inventory.client.get(path, headers=stock.inventory.headers)
    assert read.status_code == 200, read.text
    assert read.json() == saved.json()
    # A front desk member reads the catalog; another company sees nothing.
    _, desk = stock.inventory.member("front_desk")
    assert (await stock.inventory.client.get(path, headers=desk)).status_code == 200
    world = stock.inventory.world
    foreign = await stock.inventory.client.get(
        f"/v1/salons/{world.b.tenant_id}/services/{base}/materials", headers=stock.inventory.headers
    )
    assert foreign.status_code in (403, 404), foreign.text
    missing = await stock.inventory.client.get(
        f"{salon(stock)}/services/{uuid7()}/materials", headers=stock.inventory.headers
    )
    assert missing.status_code == 404, missing.text
