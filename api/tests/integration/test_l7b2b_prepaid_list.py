"""L7b2b: the prepaid balances of a business are listed for the Prepaid screen and the desk.

Design docs/plan/PACKAGE_L7_DESIGN_2026-10-22.md decision 46: creation order, at most 50 a page
with an `after` cursor, optionally of one customer; finance read rights; FAKE data only.
"""

from uuid import uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.db.provisioning import add_membership
from tests.integration import test_l5_commissions as shared
from tests.integration.booking_support import BookingWorld
from tests.integration.seed import FakeUser, seed_user
from tests.integration.test_counterparties import card
from tests.integration.test_external_payments import PaymentWorld
from tests.integration.test_l5_commissions import Kit
from tests.integration.test_l6_prepaid import salon, sell
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
manager_b = shared.manager_b
enabled = shared.enabled
invoices = shared.invoices
payments = shared.payments
kit = shared.kit
__all__ = ["client", "enabled", "idp", "invoices", "kit", "manager_a", "manager_b", "payments"]


async def listed(payments: PaymentWorld, query: str = "") -> httpx.Response:
    return await payments.ledger.client.get(
        f"{salon(payments)}/prepaid{query}", headers=payments.ledger.auth
    )


async def test_balances_list_in_creation_order_with_a_cursor_and_a_customer_filter(
    payments: PaymentWorld, world: BookingWorld, kit: Kit
) -> None:
    empty = await listed(payments)
    assert empty.status_code == 200, empty.text
    assert empty.json() == {"items": [], "next_cursor": None}
    other = uuid7()
    saved = await payments.ledger.client.put(
        f"/v1/businesses/{payments.ledger.business}/counterparties/{other}",
        json=card(display_name="FAKE Other Customer", roles=["customer"]),
        headers=payments.ledger.headers(),
    )
    assert saved.status_code == 200, saved.text
    package = await sell(
        payments,
        kit,
        kind="package",
        price="100.00",
        units=2,
        variant=world.catalog_a.base_variant_id,
    )
    certificate = await sell(payments, kit, kind="certificate", price="30.00", paid=False)
    # The payment helper settles for the fixture customer only, so this sale stays unpaid.
    foreign = await sell(payments, kit, kind="certificate", price="40.00", party=other, paid=False)
    order = [package["prepaid_id"], certificate["prepaid_id"], foreign["prepaid_id"]]

    first = await listed(payments, "?limit=2")
    assert first.status_code == 200, first.text
    page = first.json()
    assert [x["prepaid_id"] for x in page["items"]] == order[:2]
    assert page["next_cursor"] == order[1]
    assert [x["usable"] for x in page["items"]] == [True, False]
    assert page["items"][0]["remaining_units"] == 2
    second = await listed(payments, f"?limit=2&after={page['next_cursor']}")
    assert second.status_code == 200, second.text
    assert [x["prepaid_id"] for x in second.json()["items"]] == order[2:]
    assert second.json()["next_cursor"] is None

    everything = await listed(payments)
    assert [x["prepaid_id"] for x in everything.json()["items"]] == order
    one = await listed(payments, f"?counterparty_id={other}")
    assert one.status_code == 200, one.text
    assert [x["prepaid_id"] for x in one.json()["items"]] == [order[2]]
    assert one.json()["items"][0]["counterparty_id"] == str(other)


async def test_the_list_needs_finance_rights_and_stays_in_its_business(
    payments: PaymentWorld,
    world: BookingWorld,
    kit: Kit,
    owner_conn: psycopg.Connection,
    idp: FakeIdp,
    manager_b: FakeUser,
) -> None:
    await sell(payments, kit, kind="certificate", price="25.00")
    desk = seed_user(owner_conn, f"l7b2b-desk-{uuid7()}")
    add_membership(owner_conn, tenant_id=world.a.tenant_id, user_id=desk.user_id, role="front_desk")
    http = payments.ledger.client
    refused = await http.get(
        f"{salon(payments)}/prepaid", headers=idp.bearer(desk.subject, email=desk.email)
    )
    assert refused.status_code == 403, refused.text
    stranger = await http.get(
        f"{salon(payments)}/prepaid", headers=idp.bearer(manager_b.subject, email=manager_b.email)
    )
    assert stranger.status_code in (403, 404), stranger.text
    assert "prepaid_id" not in stranger.text
    for query in ("?limit=0", "?limit=51", "?after=not-an-id", "?counterparty_id=x"):
        assert (await listed(payments, query)).status_code == 422, query
