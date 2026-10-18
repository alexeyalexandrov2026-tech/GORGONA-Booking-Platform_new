"""K4a: reads the finance screen needs for provider operations; synthetic only.

The screen lists every operation of a state through the cursor, names a revoked connection, and
shows each connection's clearing account without any secret. No provider account, real key,
network call or real money is involved.
"""

from typing import Any
from uuid import uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.db.pool import RuntimePool
from gorgona_booking.db.provisioning import add_membership, owner_tenant_transaction
from tests.integration import test_provider_payments as shared
from tests.integration.booking_support import BookingWorld
from tests.integration.configuration_support import Config
from tests.integration.seed import FakeUser, seed_user
from tests.integration.test_credit_notes import CreditWorld
from tests.integration.test_provider_payments import Money, event
from tests.integration.test_provider_receipt_attestations import Routed
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
manager_b = shared.manager_b
enabled = shared.enabled
invoices = shared.invoices
payments = shared.payments
credits = shared.credits
inbox = shared.inbox
writer_pool = shared.writer_pool
routed = shared.routed
worker_pool = shared.worker_pool
backend = shared.backend
money = shared.money


async def pages(money: Money, state: str | None, limit: int = 1) -> list[dict[str, Any]]:
    """Every operation the server lists for `state`, one page at a time."""
    items: list[dict[str, Any]] = []
    after: str | None = None
    for _ in range(50):
        params: dict[str, str | int] = {"limit": limit}
        if state is not None:
            params["state"] = state
        if after is not None:
            params["after"] = after
        response = await money.http.get(
            f"{money.root}/provider-operations", params=params, headers=money.credits.ledger.auth
        )
        assert response.status_code == 200, response.text
        page = response.json()
        items.extend(page["items"])
        after = page["next_cursor"]
        if after is None:
            return items
    raise AssertionError("the cursor never ended")


async def connections(money: Money, auth: dict[str, str] | None = None) -> httpx.Response:
    return await money.http.get(
        f"{money.root}/provider-connections", headers=auth or money.credits.ledger.auth
    )


# U-01 -----------------------------------------------------------------------


async def test_the_state_filter_lists_every_matching_operation_across_pages(
    money: Money,
) -> None:
    observed = [f"pi_FAKEscreen{n}" for n in range(3)]
    slow = [f"pi_FAKEslow{n}" for n in range(2)]
    await money.observe(
        *(event("payment_intent.succeeded", object_id=x) for x in observed),
        *(event("payment_intent.processing", status="processing", object_id=x) for x in slow),
    )
    found = await pages(money, "observed")
    assert sorted(x["provider_object_id"] for x in found) == sorted(observed)
    assert {x["state"] for x in found} == {"observed"}
    found = await pages(money, "not_final")
    assert sorted(x["provider_object_id"] for x in found) == sorted(slow)
    assert len(await pages(money, None, limit=2)) == 5
    assert await pages(money, "applied") == []


async def test_an_unknown_state_filter_is_refused(money: Money) -> None:
    response = await money.http.get(
        f"{money.root}/provider-operations",
        params={"state": "paid"},
        headers=money.credits.ledger.auth,
    )
    assert response.status_code == 422, response.text


# U-02 -----------------------------------------------------------------------


async def test_a_revoked_connection_lists_its_operations_as_revoked(
    money: Money, owner_conn: psycopg.Connection
) -> None:
    await money.observe(event("payment_intent.succeeded"))
    with owner_tenant_transaction(owner_conn, money.routed.tenant_id):
        owner_conn.execute(
            "update gba.provider_receipt_connections set revoked=true,revoked_reason='compromise' "
            "where tenant_id=%s and id=%s",
            (money.routed.tenant_id, money.routed.connection_id),
        )
    (listed,) = await money.listed()
    assert listed["state"] == "revoked"
    assert await pages(money, "observed") == []
    assert len(await pages(money, "revoked")) == 1
    (item,) = (await connections(money)).json()["items"]
    assert item["revoked"] is True


# U-07, U-09 -----------------------------------------------------------------


async def test_connections_show_the_clearing_account_and_no_secret(
    credits: CreditWorld,
    routed: Routed,
    writer_pool: RuntimePool,
    worker_pool: RuntimePool,
) -> None:
    unregistered = Money(credits, routed, writer_pool, worker_pool)
    before = await connections(unregistered)
    assert before.status_code == 200, before.text
    body = before.json()
    assert (body["business_id"], body["book_id"], body["next_cursor"]) == (
        str(credits.ledger.business),
        str(credits.ledger.book),
        None,
    )
    (item,) = body["items"]
    assert set(item) == {"connection_id", "account_id", "revoked", "clearing_account"}
    assert (item["connection_id"], item["revoked"], item["clearing_account"]) == (
        str(routed.connection_id),
        False,
        None,
    )
    assert item["account_id"].startswith("acct_")
    registered = await unregistered.register()
    assert registered.status_code == 200, registered.text
    after = await connections(unregistered)
    (item,) = after.json()["items"]
    assert item["clearing_account"] == {
        "account_id": str(unregistered.clearing),
        "registered_by": str(credits.ledger.user.user_id),
        "registered_at": registered.json()["registered_at"],
    }
    for text in (before.text, after.text):
        assert routed.secret_ref not in text
        assert "whsec_" not in text
        assert str(routed.verification_config_id) not in text


@pytest.mark.parametrize(
    ("role", "branch", "expected"),
    [
        ("owner", False, 200),
        ("front_desk", False, 403),
        ("artist", False, 403),
        ("manager", True, 403),
    ],
)
async def test_provider_screen_reads_keep_company_finance_permissions(
    money: Money,
    owner_conn: psycopg.Connection,
    world: BookingWorld,
    idp: FakeIdp,
    role: str,
    branch: bool,
    expected: int,
) -> None:
    await money.observe(event("payment_intent.succeeded"))
    member = seed_user(owner_conn, f"FAKE-K4a-{role}-{uuid7()}")
    add_membership(
        owner_conn,
        tenant_id=money.credits.ledger.business,
        user_id=member.user_id,
        role=role,
        location_id=world.a.location_id if branch else None,
    )
    auth = idp.bearer(member.subject, email=member.email)
    listed = await money.http.get(f"{money.root}/provider-operations", headers=auth)
    assert listed.status_code == expected, listed.text
    assert (await connections(money, auth)).status_code == expected


async def test_another_company_cannot_read_the_connections(
    money: Money, manager_b: FakeUser, idp: FakeIdp
) -> None:
    refused = await connections(money, Config(money.http, idp).auth(manager_b))
    assert refused.status_code in (403, 404), refused.text
