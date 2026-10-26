"""N1: broker authority and carrier profiles as dated facts (package N; FAKE data only).

ADR-0034 and docs/plan/PACKAGE_N1_DESIGN_2026-10-26.md: a business's broker authority and each
carrier's profile are insert-only versions with a source and a check date; eligibility is computed
for a date and names every failing reason; only owners and managers with transport.broker read or
write them.
"""

from typing import Any
from uuid import UUID, uuid7

import psycopg
import pytest

from gorgona_booking.auth.permissions import (
    DELEGABLE_PERMISSIONS,
    ROLE_PERMISSIONS,
    Permission,
)
from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import add_membership
from tests.integration import test_management_api as shared
from tests.integration.booking_support import BookingWorld
from tests.integration.configuration_support import Config
from tests.integration.seed import FakeUser, seed_user
from tests.integration.test_counterparties import card
from tests.integration.test_delegations import Parties, _member, owner_a, owner_b, parties
from tests.integration.test_m1_transport_planning import Transport, accepted, error, transport
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
manager_b = shared.manager_b
__all__ = [
    "accepted",
    "client",
    "idp",
    "manager_a",
    "manager_b",
    "owner_a",
    "owner_b",
    "parties",
    "transport",
]
TRANSPORT = ["transport.read", "transport.plan", "transport.assign", "transport.events"]


def authority(revision: int, **changes: Any) -> dict[str, Any]:
    return {
        "expected_revision": revision,
        "jurisdiction": "US",
        "authority_number": "MC-123456",
        "bond_reference": "FAKE-BOND-1",
        "status": "active",
        "effective_from": "2026-01-01",
        "expires_on": None,
        "source": "owner.statement",
        "checked_on": "2026-10-20",
        **changes,
    }


def profile(revision: int, **changes: Any) -> dict[str, Any]:
    return {
        "expected_revision": revision,
        "jurisdiction": "US",
        "authority_number": "MC-777777",
        "liability_expires_on": "2027-05-01",
        "cargo_expires_on": "2027-05-01",
        "safety_rating": "satisfactory",
        "source": "carrier.packet",
        "checked_on": "2026-10-20",
        **changes,
    }


async def reasons(t: Transport, path: str, on: str) -> tuple[bool, list[str]]:
    seen = await t.get(f"{path}?on={on}")
    assert seen.status_code == 200, seen.text
    body = seen.json()
    assert body["on"] == on
    return bool(body["eligible"]), list(body["reasons"])


async def carrier(t: Transport, name: str = "FAKE Carrier") -> UUID:
    party = uuid7()
    saved = await t.client.put(
        f"/v1/businesses/{t.tenant}/counterparties/{party}",
        json=card(display_name=name, roles=["supplier"]),
        headers={**t.headers, "Idempotency-Key": str(uuid7())},
    )
    assert saved.status_code == 200, saved.text
    return party


# N1-01 ------------------------------------------------------------------------------


async def test_the_broker_authority_is_versioned(transport: Transport) -> None:
    t = transport
    empty = await t.get("/broker-authority")
    assert empty.status_code == 200, empty.text
    assert (empty.json()["current"], empty.json()["versions"]) == (None, [])
    first = await t.put("/broker-authority", authority(0))
    assert first.status_code == 200, first.text
    current = first.json()["current"]
    assert (current["revision"], current["authority_number"], current["status"]) == (
        1,
        "MC-123456",
        "active",
    )
    stale = await t.put("/broker-authority", authority(0, bond_reference="FAKE-BOND-2"))
    assert stale.status_code == 409, stale.text
    second = await t.put("/broker-authority", authority(1, bond_reference="FAKE-BOND-2"))
    assert second.status_code == 200, second.text
    view = second.json()
    assert [v["revision"] for v in view["versions"]] == [1, 2]
    assert [v["bond_reference"] for v in view["versions"]] == ["FAKE-BOND-1", "FAKE-BOND-2"]
    for invalid in (
        authority(2, status="paused"),
        authority(2, jurisdiction="usa"),
        authority(2, authority_number=" "),
        authority(2, expires_on="2025-12-31"),
    ):
        refused = await t.put("/broker-authority", invalid)
        assert refused.status_code == 422, refused.text


# N1-02 ------------------------------------------------------------------------------


async def test_broker_eligibility_names_every_reason(transport: Transport) -> None:
    t = transport
    path = "/broker-authority/eligibility"
    assert await reasons(t, path, "2026-10-26") == (False, ["no_authority"])
    saved = await t.put("/broker-authority", authority(0, expires_on="2027-01-01"))
    assert saved.status_code == 200, saved.text
    assert await reasons(t, path, "2026-10-26") == (True, [])
    assert await reasons(t, path, "2025-12-31") == (False, ["not_effective"])
    # The check of 2026-10-20 is stale after 90 days; the authority expires on 2027-01-01.
    assert await reasons(t, path, "2027-01-02") == (False, ["expired"])
    assert await reasons(t, path, "2027-01-19") == (False, ["expired", "stale_check"])
    saved = await t.put("/broker-authority", authority(1, status="withdrawn"))
    assert saved.status_code == 200, saved.text
    assert await reasons(t, path, "2026-10-26") == (False, ["withdrawn"])
    assert (await t.get(f"{path}?on=not-a-date")).status_code == 422


# N1-03 ------------------------------------------------------------------------------


async def test_carrier_profiles_are_versioned_and_eligibility_names_every_reason(
    transport: Transport,
) -> None:
    t = transport
    party = await carrier(t)
    path = f"/carriers/{party}/eligibility"
    assert await reasons(t, path, "2026-10-26") == (False, ["no_profile"])
    unknown = await t.put(
        f"/carriers/{party}/profile",
        profile(
            0,
            authority_number=None,
            liability_expires_on=None,
            cargo_expires_on="2026-09-30",
            safety_rating="unsatisfactory",
        ),
    )
    assert unknown.status_code == 200, unknown.text
    assert await reasons(t, path, "2026-10-26") == (
        False,
        ["unknown_authority", "liability_unknown", "cargo_expired", "unsatisfactory"],
    )
    fixed = await t.put(f"/carriers/{party}/profile", profile(1))
    assert fixed.status_code == 200, fixed.text
    assert await reasons(t, path, "2026-10-26") == (True, [])
    assert await reasons(t, path, "2027-01-19") == (False, ["stale_check"])
    assert await reasons(t, path, "2027-05-02") == (
        False,
        ["liability_expired", "cargo_expired", "stale_check"],
    )
    conditional = await t.put(f"/carriers/{party}/profile", profile(2, safety_rating="conditional"))
    assert conditional.status_code == 200, conditional.text
    assert await reasons(t, path, "2026-10-26") == (True, [])
    view = (await t.get(f"/carriers/{party}/profile")).json()
    assert view["counterparty_id"] == str(party)
    assert [v["revision"] for v in view["versions"]] == [1, 2, 3]
    assert view["current"]["safety_rating"] == "conditional"
    stale = await t.put(f"/carriers/{party}/profile", profile(1))
    assert error(stale)[0] == 409, stale.text
    missing = await t.put(f"/carriers/{uuid7()}/profile", profile(0))
    assert missing.status_code in (404, 422), missing.text


# N1-04 ------------------------------------------------------------------------------


async def _rows(pool: RuntimePool, tenant: UUID) -> tuple[int, int]:
    async with tenant_transaction(pool, tenant) as conn:
        a = await (
            await conn.execute("select count(*) from gba.transport_broker_authorities")
        ).fetchone()
        b = await (
            await conn.execute("select count(*) from gba.transport_carrier_profiles")
        ).fetchone()
    assert a is not None
    assert b is not None
    return int(a[0]), int(b[0])


async def test_only_owners_and_managers_with_the_broker_right_read_or_write(
    transport: Transport,
    owner_conn: psycopg.Connection,
    world: BookingWorld,
    app_pool: RuntimePool,
    idp: FakeIdp,
    parties: Parties,
    owner_a: FakeUser,
    owner_b: FakeUser,
    manager_b: FakeUser,
    manager_a: FakeUser,
) -> None:
    t = transport
    assert Permission.TRANSPORT_BROKER in ROLE_PERMISSIONS["manager"]
    assert Permission.TRANSPORT_BROKER in ROLE_PERMISSIONS["owner"]
    assert Permission.TRANSPORT_BROKER not in ROLE_PERMISSIONS["front_desk"]
    assert Permission.TRANSPORT_BROKER not in DELEGABLE_PERMISSIONS
    party = await carrier(t)
    assert (await t.put("/broker-authority", authority(0))).status_code == 200
    assert (await t.put(f"/carriers/{party}/profile", profile(0))).status_code == 200
    desk = seed_user(owner_conn, f"n1-desk-{uuid7()}")
    add_membership(owner_conn, tenant_id=world.a.tenant_id, user_id=desk.user_id, role="front_desk")
    dispatcher = _member(owner_conn, world.b.tenant_id, "manager", "n1-dispatcher")
    await parties.active_grant(owner_a, owner_b, [dispatcher], permissions=TRANSPORT)
    before = await _rows(app_pool, t.tenant)
    for person, allowed in ((desk, (403,)), (dispatcher, (403,)), (manager_b, (403, 404))):
        headers = idp.bearer(person.subject, email=person.email)
        for method, path, body in (
            ("put", "/broker-authority", authority(1)),
            ("put", f"/carriers/{party}/profile", profile(1)),
            ("get", "/broker-authority", None),
            ("get", "/broker-authority/eligibility?on=2026-10-26", None),
            ("get", f"/carriers/{party}/profile", None),
            ("get", f"/carriers/{party}/eligibility?on=2026-10-26", None),
        ):
            answer = (
                await t.get(path, headers)
                if method == "get"
                else await t.put(path, body or {}, headers)
            )
            assert answer.status_code in allowed, (person, path, answer.text)
    assert await _rows(app_pool, t.tenant) == before
    for statement in (
        "update gba.transport_broker_authorities set status = 'withdrawn'",
        "delete from gba.transport_carrier_profiles",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with tenant_transaction(app_pool, t.tenant) as conn:
                await conn.execute(statement)
    # Without the transport module nothing is written.
    await Config(t.client, idp).publish(
        manager_a, t.tenant, 1, ["booking_resources", "counterparties"]
    )
    off = await t.put("/broker-authority", authority(1))
    assert off.status_code in (403, 409), off.text
    assert await _rows(app_pool, t.tenant) == before
