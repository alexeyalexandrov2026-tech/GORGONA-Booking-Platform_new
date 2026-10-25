"""M6b-01: orders are listed completely in pages of 50 (FAKE data only)."""

from uuid import uuid7

import pytest

from tests.integration import test_management_api as shared
from tests.integration.test_m1_transport_planning import Transport, accepted, load, transport
from tests.integration.test_m6a_transport_lists import every

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
__all__ = ["accepted", "client", "idp", "manager_a", "transport"]


async def test_orders_are_listed_completely(transport: Transport) -> None:
    t = transport
    orders = []
    for _ in range(103):
        order = uuid7()
        made = await t.order(order, [load(uuid7(), 3)])
        assert made.status_code == 200, made.text
        orders.append(str(order))
    first = (await t.get("/orders")).json()
    assert (len(first["items"]), first["next_cursor"]) == (50, first["items"][-1]["order_id"])
    # Before M6b the list stopped silently at 100 orders.
    assert await every(t, "/orders", "order_id") == sorted(orders)
    last = (await t.get(f"/orders?after={sorted(orders)[-1]}")).json()
    assert (last["items"], last["next_cursor"]) == ([], None)
    assert (await t.get("/orders?after=not-a-cursor")).status_code == 422
