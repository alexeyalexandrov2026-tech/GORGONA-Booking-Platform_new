"""L7b2a: the commission plan of a specialist and the commission of a visit are read back."""

import httpx
import pytest

from gorgona_booking.db.pool import RuntimePool
from tests.integration import test_l5_commissions as shared
from tests.integration.booking_support import BookingWorld
from tests.integration.test_external_payments import PaymentWorld
from tests.integration.test_l5_commissions import (
    Kit,
    accrue,
    commission_body,
    paid_visit,
    plan_path,
    put_plan,
)

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


def code(response: httpx.Response) -> tuple[int, str]:
    return response.status_code, response.json()["error"]["code"]


async def test_a_plan_reads_back_and_a_missing_one_is_not_found(
    payments: PaymentWorld, world: BookingWorld, kit: Kit
) -> None:
    http, auth = payments.ledger.client, payments.ledger.auth
    missing = await http.get(plan_path(payments, world), headers=auth)
    assert code(missing) == (404, "COMMISSION_PLAN_MISSING")
    saved = await put_plan(payments, world, kit, [{"service_id": None, "percent": "10"}])
    assert saved.status_code == 200, saved.text
    read = await http.get(plan_path(payments, world), headers=auth)
    assert read.status_code == 200, read.text
    assert read.json() == saved.json()


async def test_a_commission_reads_back_and_a_missing_one_is_not_found(
    payments: PaymentWorld, world: BookingWorld, kit: Kit, app_pool: RuntimePool
) -> None:
    assert (
        await put_plan(payments, world, kit, [{"service_id": None, "percent": "10"}])
    ).status_code == 200
    booking = await paid_visit(payments, world, app_pool, kit)
    path = f"/v1/salons/{payments.ledger.business}/bookings/{booking}/commission"
    http, auth = payments.ledger.client, payments.ledger.auth
    assert code(await http.get(path, headers=auth)) == (404, "VISIT_NOT_COMMISSIONED")
    accrued = await accrue(payments, booking, commission_body(kit))
    assert accrued.status_code == 200, accrued.text
    read = await http.get(path, headers=auth)
    assert read.status_code == 200, read.text
    assert read.json() == accrued.json()
