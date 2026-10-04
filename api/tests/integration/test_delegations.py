"""Cross-company delegation in real PostgreSQL: consent, limits, revocation and isolation."""

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid7
from zoneinfo import ZoneInfo

import httpx
import psycopg
import pytest

from gorgona_booking.db.pool import RuntimePool, tenant_transaction, unscoped_transaction
from gorgona_booking.db.provisioning import add_membership, owner_tenant_transaction
from tests.integration import test_management_api as shared
from tests.integration.booking_support import BookingWorld
from tests.integration.customer_support import customer_day
from tests.integration.seed import FakeUser, seed_other_branch, seed_salon, seed_user
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp

ALL = ["booking.read", "booking.write", "catalog.read", "staff.read"]
READ_ONLY = ["booking.read", "catalog.read", "staff.read"]


def _member(owner_conn: psycopg.Connection, tenant_id: UUID, role: str, label: str) -> FakeUser:
    user = seed_user(owner_conn, f"delegation-{label}-{uuid7()}")
    add_membership(owner_conn, tenant_id=tenant_id, user_id=user.user_id, role=role)
    return user


@pytest.fixture
def owner_a(world: BookingWorld, owner_conn: psycopg.Connection) -> FakeUser:
    return _member(owner_conn, world.a.tenant_id, "owner", "owner-a")


@pytest.fixture
def owner_b(world: BookingWorld, owner_conn: psycopg.Connection) -> FakeUser:
    return _member(owner_conn, world.b.tenant_id, "owner", "owner-b")


@pytest.fixture
def dispatcher(world: BookingWorld, owner_conn: psycopg.Connection) -> FakeUser:
    """A company-wide front-desk employee of the servicing business."""
    return _member(owner_conn, world.b.tenant_id, "front_desk", "dispatcher")


class Parties:
    def __init__(self, client: httpx.AsyncClient, idp: FakeIdp, world: BookingWorld) -> None:
        self.client, self.idp, self.world = client, idp, world

    def headers(self, user: FakeUser, key: str | None = None) -> dict[str, str]:
        return {
            **self.idp.bearer(user.subject, email=user.email),
            "Idempotency-Key": key or str(uuid7()),
        }

    async def issue(
        self,
        user: FakeUser,
        grant_id: UUID,
        *,
        business: UUID | None = None,
        key: str | None = None,
        terms: Mapping[str, object] | None = None,
    ) -> httpx.Response:
        body = {
            "servicer_business_id": str(self.world.b.tenant_id),
            "permissions": ALL,
            "location_id": None,
            "expires_at": (datetime.now(UTC) + timedelta(days=30)).isoformat(),
            **(terms or {}),
        }
        owner = business or self.world.a.tenant_id
        return await self.client.put(
            f"/v1/businesses/{owner}/delegations/{grant_id}",
            json=body,
            headers=self.headers(user, key),
        )

    async def act(
        self,
        user: FakeUser,
        business: UUID,
        grant_id: UUID,
        action: str,
        revision: int,
        delegates: list[FakeUser] | None = None,
        key: str | None = None,
    ) -> httpx.Response:
        body: dict[str, object] = {"expected_revision": revision}
        if delegates is not None:
            body["delegate_user_ids"] = [str(item.user_id) for item in delegates]
        path = f"/v1/businesses/{business}/delegations/{grant_id}"
        if action == "delegates":
            return await self.client.put(
                f"{path}/delegates", json=body, headers=self.headers(user, key)
            )
        return await self.client.post(
            f"{path}/{action}", json=body, headers=self.headers(user, key)
        )

    async def active_grant(
        self,
        owner: FakeUser,
        servicer: FakeUser,
        delegates: list[FakeUser],
        **terms: object,
    ) -> UUID:
        grant_id = uuid7()
        issued = await self.issue(owner, grant_id, terms=terms)
        assert issued.status_code == 200, issued.text
        accepted = await self.act(
            servicer, self.world.b.tenant_id, grant_id, "accept", 1, delegates
        )
        assert accepted.status_code == 200, accepted.text
        return grant_id


@pytest.fixture
def parties(client: httpx.AsyncClient, idp: FakeIdp, world: BookingWorld) -> Parties:
    return Parties(client, idp, world)


def _booking(world: BookingWorld, hour: int, location: UUID | None = None) -> dict[str, str]:
    return {
        "location_id": str(location or world.a.location_id),
        "resource_id": str(world.artist_a1),
        "variant_id": str(world.catalog_a.base_variant_id),
        "starts_at": datetime.fromisoformat(f"{customer_day()}T{hour:02d}:00:00")
        .replace(tzinfo=ZoneInfo("America/New_York"))
        .isoformat(),
        "customer_name": "FAKE delegated guest",
        "customer_email": "delegated@example.com",
        "customer_phone": "+15551234570",
    }


async def test_owner_offer_servicer_acceptance_and_delegated_booking_cycle(
    client: httpx.AsyncClient,
    parties: Parties,
    world: BookingWorld,
    owner_a: FakeUser,
    owner_b: FakeUser,
    dispatcher: FakeUser,
    app_pool: RuntimePool,
) -> None:
    grant_id, key = uuid7(), str(uuid7())
    terms = {"expires_at": (datetime.now(UTC) + timedelta(days=30)).isoformat()}
    issued = await parties.issue(owner_a, grant_id, key=key, terms=terms)
    assert issued.status_code == 200, issued.text
    offer = issued.json()
    assert (offer["status"], offer["revision"], offer["delegates"]) == ("pending", 1, [])
    assert offer["owner_business_id"] == str(world.a.tenant_id)
    assert offer["servicer_name"] is None
    assert (await parties.issue(owner_a, grant_id, key=key, terms=terms)).json() == offer
    reused = await parties.issue(owner_a, grant_id, key=key)
    assert reused.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    salon = f"/v1/salons/{world.a.tenant_id}"
    dispatcher_headers = parties.idp.bearer(dispatcher.subject, email=dispatcher.email)
    # A pending offer grants nothing.
    assert (await client.get(f"{salon}/workspace", headers=dispatcher_headers)).status_code == 403
    received = await client.get(
        f"/v1/businesses/{world.b.tenant_id}/delegations",
        headers=parties.idp.bearer(owner_b.subject, email=owner_b.email),
    )
    assert [item["grant_id"] for item in received.json()["items"]] == [str(grant_id)]
    accepted = await parties.act(owner_b, world.b.tenant_id, grant_id, "accept", 1, [dispatcher])
    assert accepted.status_code == 200, accepted.text
    grant = accepted.json()
    assert (grant["status"], grant["revision"]) == ("active", 2)
    assert grant["servicer_name"] is not None
    assert [item["user_id"] for item in grant["delegates"]] == [str(dispatcher.user_id)]
    me = (await client.get("/v1/me", headers=dispatcher_headers)).json()
    assert [item["business_id"] for item in me["delegations"]] == [str(world.a.tenant_id)]
    assert [item["salon_id"] for item in me["memberships"]] == [str(world.b.tenant_id)]

    assert (await client.get(f"{salon}/workspace", headers=dispatcher_headers)).status_code == 200
    created = await client.post(
        f"{salon}/bookings",
        json=_booking(world, 11),
        headers={**dispatcher_headers, "Idempotency-Key": str(uuid7())},
    )
    assert created.status_code == 201, created.text
    booking_id = created.json()["booking_id"]
    cancelled = await client.post(
        f"{salon}/bookings/{booking_id}/cancel",
        json={},
        headers={**dispatcher_headers, "Idempotency-Key": str(uuid7())},
    )
    assert cancelled.status_code == 200, cancelled.text
    # Owner-only areas, client lists, audit and settings are never delegated.
    for path in (
        f"{salon}/clients",
        f"{salon}/activity",
        f"{salon}/settings",
        f"{salon}/members",
        f"/v1/businesses/{world.a.tenant_id}",
        f"/v1/businesses/{world.a.tenant_id}/legal-entities",
        f"/v1/businesses/{world.a.tenant_id}/departments",
        f"/v1/businesses/{world.a.tenant_id}/delegations",
    ):
        assert (await client.get(path, headers=dispatcher_headers)).status_code == 403, path
    # The servicer's owner is not a delegate and has no access to the owner's bookings.
    owner_b_headers = parties.idp.bearer(owner_b.subject, email=owner_b.email)
    assert (await client.get(f"{salon}/bookings", headers=owner_b_headers)).status_code == 403
    async with tenant_transaction(app_pool, world.a.tenant_id) as conn:
        access = await (
            await conn.execute(
                "select actor, target_id, details from gba.audit_events "
                "where action = 'delegation.access' order by occurred_at"
            )
        ).fetchall()
        assert access
        assert {row[0] for row in access} == {f"user:{dispatcher.user_id}"}
        assert {row[1] for row in access} == {str(grant_id)}
        assert {row[2]["servicer_business_id"] for row in access} == {str(world.b.tenant_id)}
        assert {row[2]["permission"] for row in access} >= {"booking.write", "staff.read"}
        issued_audit = await (
            await conn.execute(
                "select count(*) from gba.audit_events where action = 'delegation.issued'"
            )
        ).fetchone()
        assert issued_audit == (1,)
    async with tenant_transaction(app_pool, world.b.tenant_id) as conn:
        assert (await (await conn.execute("select count(*) from gba.bookings")).fetchone()) == (0,)
        accepted_audit = await (
            await conn.execute(
                "select count(*) from gba.audit_events where action = 'delegation.accepted'"
            )
        ).fetchone()
        assert accepted_audit == (1,)


async def test_revocation_removal_and_expiry_block_the_next_command(
    client: httpx.AsyncClient,
    parties: Parties,
    world: BookingWorld,
    owner_a: FakeUser,
    owner_b: FakeUser,
    dispatcher: FakeUser,
    owner_conn: psycopg.Connection,
) -> None:
    second = _member(owner_conn, world.b.tenant_id, "front_desk", "second")
    salon = f"/v1/salons/{world.a.tenant_id}"
    headers = parties.idp.bearer(dispatcher.subject, email=dispatcher.email)
    second_headers = parties.idp.bearer(second.subject, email=second.email)
    grant_id = await parties.active_grant(owner_a, owner_b, [dispatcher, second])
    key = str(uuid7())
    created = await client.post(
        f"{salon}/bookings", json=_booking(world, 11), headers={**headers, "Idempotency-Key": key}
    )
    assert created.status_code == 201, created.text
    # The servicer removes one delegate: that person loses access at once.
    changed = await parties.act(owner_b, world.b.tenant_id, grant_id, "delegates", 2, [second])
    assert changed.status_code == 200, changed.text
    assert (await client.get(f"{salon}/workspace", headers=headers)).status_code == 403
    assert (await client.get(f"{salon}/workspace", headers=second_headers)).status_code == 200
    # The owner revokes: the next command and an old receipt replay are both refused.
    revoked = await parties.act(owner_a, world.a.tenant_id, grant_id, "revoke", 3)
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["revoked_by_side"] == "owner"
    assert (await client.get(f"{salon}/workspace", headers=second_headers)).status_code == 403
    replay = await client.post(
        f"{salon}/bookings", json=_booking(world, 11), headers={**headers, "Idempotency-Key": key}
    )
    assert replay.status_code == 403
    assert created.json()["booking_id"] not in replay.text
    me = (await client.get("/v1/me", headers=second_headers)).json()
    assert me["delegations"] == []

    # The servicer may end an active relationship from its side too.
    servicer_grant = await parties.active_grant(owner_a, owner_b, [second])
    ended = await parties.act(owner_b, world.b.tenant_id, servicer_grant, "revoke", 2)
    assert ended.json()["revoked_by_side"] == "servicer"
    assert (await client.get(f"{salon}/workspace", headers=second_headers)).status_code == 403

    # Expiry ends access without any revocation.
    expiring = await parties.active_grant(
        owner_a,
        owner_b,
        [second],
        expires_at=(datetime.now(UTC) + timedelta(seconds=3)).isoformat(),
    )
    assert (await client.get(f"{salon}/workspace", headers=second_headers)).status_code == 200
    await asyncio.sleep(3.5)
    assert (await client.get(f"{salon}/workspace", headers=second_headers)).status_code == 403
    listed = await client.get(
        f"/v1/businesses/{world.a.tenant_id}/delegations/{expiring}",
        headers=parties.idp.bearer(owner_a.subject, email=owner_a.email),
    )
    assert (listed.json()["status"], listed.json()["expired"]) == ("active", True)
    renewed = await parties.act(owner_b, world.b.tenant_id, expiring, "delegates", 2, [second])
    assert renewed.json()["error"]["code"] == "DELEGATION_STATE_INVALID"


async def test_both_accounts_and_the_grant_limit_every_command(
    client: httpx.AsyncClient,
    parties: Parties,
    world: BookingWorld,
    owner_a: FakeUser,
    owner_b: FakeUser,
    dispatcher: FakeUser,
    owner_conn: psycopg.Connection,
) -> None:
    artist = _member(owner_conn, world.b.tenant_id, "artist", "artist")
    outsider = _member(owner_conn, world.b.tenant_id, "front_desk", "not-named")
    salon = f"/v1/salons/{world.a.tenant_id}"
    await parties.active_grant(owner_a, owner_b, [dispatcher, artist])

    def headers(user: FakeUser) -> dict[str, str]:
        return parties.headers(user)

    async def book(user: FakeUser, hour: int) -> int:
        response = await client.post(
            f"{salon}/bookings", json=_booking(world, hour), headers=headers(user)
        )
        return response.status_code

    # The servicer role still limits the grant: an artist reads but cannot book.
    assert (await client.get(f"{salon}/bookings", headers=headers(artist))).status_code == 200
    assert await book(artist, 11) == 403
    assert (await client.get(f"{salon}/workspace", headers=headers(outsider))).status_code == 403
    for statement, params in (
        (
            "update gba.memberships set status = 'suspended' where user_id = %s",
            (dispatcher.user_id,),
        ),
        (
            "update gba.memberships set status = 'active', location_id = %s where user_id = %s",
            (world.b.location_id, dispatcher.user_id),
        ),
    ):
        with owner_tenant_transaction(owner_conn, world.b.tenant_id):
            owner_conn.execute(statement, params)
        assert await book(dispatcher, 12) == 403
    with owner_tenant_transaction(owner_conn, world.b.tenant_id):
        owner_conn.execute(
            "update gba.memberships set location_id = null where user_id = %s",
            (dispatcher.user_id,),
        )
    assert await book(dispatcher, 12) == 201
    for tenant_id in (world.b.tenant_id, world.a.tenant_id):
        with owner_tenant_transaction(owner_conn, tenant_id):
            owner_conn.execute(
                "update gba.tenants set status = 'suspended' where id = %s", (tenant_id,)
            )
        assert await book(dispatcher, 13) == 403
        with owner_tenant_transaction(owner_conn, tenant_id):
            owner_conn.execute(
                "update gba.tenants set status = 'active' where id = %s", (tenant_id,)
            )
    assert await book(dispatcher, 13) == 201


async def test_read_only_and_location_limited_terms(
    client: httpx.AsyncClient,
    parties: Parties,
    world: BookingWorld,
    owner_a: FakeUser,
    owner_b: FakeUser,
    dispatcher: FakeUser,
    owner_conn: psycopg.Connection,
) -> None:
    other_location, _ = seed_other_branch(owner_conn, world.a)
    salon = f"/v1/salons/{world.a.tenant_id}"
    grant_id = await parties.active_grant(owner_a, owner_b, [dispatcher], permissions=READ_ONLY)
    assert (
        await client.get(f"{salon}/bookings", headers=parties.headers(dispatcher))
    ).status_code == 200
    denied = await client.post(
        f"{salon}/bookings", json=_booking(world, 11), headers=parties.headers(dispatcher)
    )
    assert denied.status_code == 403
    assert (await parties.act(owner_a, world.a.tenant_id, grant_id, "revoke", 2)).status_code == 200
    await parties.active_grant(owner_a, owner_b, [dispatcher], location_id=str(world.a.location_id))
    workspace = await client.get(f"{salon}/workspace", headers=parties.headers(dispatcher))
    assert [item["id"] for item in workspace.json()["locations"]] == [str(world.a.location_id)]
    assert str(other_location) not in workspace.text
    elsewhere = await client.post(
        f"{salon}/bookings",
        json=_booking(world, 11, other_location),
        headers=parties.headers(dispatcher),
    )
    assert elsewhere.status_code in (403, 422), elsewhere.text
    here = await client.post(
        f"{salon}/bookings", json=_booking(world, 11), headers=parties.headers(dispatcher)
    )
    assert here.status_code == 201, here.text


async def test_terms_parties_and_states_are_enforced(
    client: httpx.AsyncClient,
    parties: Parties,
    world: BookingWorld,
    owner_a: FakeUser,
    owner_b: FakeUser,
    dispatcher: FakeUser,
    owner_conn: psycopg.Connection,
) -> None:
    manager_a = _member(owner_conn, world.a.tenant_id, "manager", "manager-a")
    branch_b = _member(owner_conn, world.b.tenant_id, "front_desk", "branch-b")
    with owner_tenant_transaction(owner_conn, world.b.tenant_id):
        owner_conn.execute(
            "update gba.memberships set location_id = %s where user_id = %s",
            (world.b.location_id, branch_b.user_id),
        )
    later = datetime.now(UTC) + timedelta(days=30)
    for user, terms, status, code in (
        (manager_a, {}, 403, "PERMISSION_DENIED"),
        (owner_b, {}, 403, "TENANT_ACCESS_DENIED"),
        (
            owner_a,
            {"servicer_business_id": str(world.a.tenant_id)},
            422,
            "DELEGATION_STATE_INVALID",
        ),
        (owner_a, {"servicer_business_id": str(uuid7())}, 422, "INVALID_REFERENCE"),
        (owner_a, {"location_id": str(world.b.location_id)}, 422, "INVALID_REFERENCE"),
        (owner_a, {"expires_at": "2020-01-01T00:00:00Z"}, 422, "DELEGATION_STATE_INVALID"),
        (
            owner_a,
            {"expires_at": (later + timedelta(days=400)).isoformat()},
            422,
            "DELEGATION_STATE_INVALID",
        ),
    ):
        response = await parties.issue(user, uuid7(), terms=terms)
        assert (response.status_code, response.json()["error"]["code"]) == (status, code), terms
    grant_id = uuid7()
    assert (await parties.issue(owner_a, grant_id)).status_code == 200
    duplicate = await parties.issue(owner_a, uuid7())
    assert duplicate.status_code == 409
    a, b = world.a.tenant_id, world.b.tenant_id
    for user, business, action, revision, delegates, code in (
        (owner_a, a, "accept", 1, [dispatcher], "DELEGATION_STATE_INVALID"),
        (owner_b, b, "revoke", 1, None, "DELEGATION_STATE_INVALID"),
        (owner_b, b, "accept", 2, [dispatcher], "CONFLICT"),
        (owner_b, b, "accept", 1, [owner_a], "INVALID_REFERENCE"),
        (owner_b, b, "accept", 1, [branch_b], "INVALID_REFERENCE"),
    ):
        response = await parties.act(user, business, grant_id, action, revision, delegates)
        assert response.json()["error"]["code"] == code, (action, response.text)
    declined = await parties.act(owner_b, b, grant_id, "decline", 1)
    assert declined.json()["status"] == "declined"
    late = await parties.act(owner_b, b, grant_id, "accept", 2, [dispatcher])
    assert late.json()["error"]["code"] == "DELEGATION_STATE_INVALID"
    # A declined offer frees the pair for a new one; accept and revoke race on revision 1.
    racing = uuid7()
    assert (await parties.issue(owner_a, racing)).status_code == 200
    results = await asyncio.gather(
        parties.act(owner_b, b, racing, "accept", 1, [dispatcher]),
        parties.act(owner_a, a, racing, "revoke", 1),
    )
    assert sorted(response.status_code for response in results) == [200, 409]
    # A third company sees neither the relationship nor its parties' lists.
    c = seed_salon(owner_conn, "delegation-third")
    owner_c = _member(owner_conn, c.tenant_id, "owner", "owner-c")
    c_headers = parties.idp.bearer(owner_c.subject, email=owner_c.email)
    assert (
        await client.get(f"/v1/businesses/{c.tenant_id}/delegations/{grant_id}", headers=c_headers)
    ).status_code == 404
    assert (
        await client.get(f"/v1/businesses/{c.tenant_id}/delegations", headers=c_headers)
    ).json()["items"] == []
    assert (
        await client.get(f"/v1/businesses/{a}/delegations", headers=c_headers)
    ).status_code == 403


async def test_database_rules_hold_for_direct_sql(
    parties: Parties,
    world: BookingWorld,
    owner_a: FakeUser,
    owner_b: FakeUser,
    dispatcher: FakeUser,
    owner_conn: psycopg.Connection,
    app_pool: RuntimePool,
) -> None:
    grant_id = await parties.active_grant(owner_a, owner_b, [dispatcher])
    outsider = _member(owner_conn, world.a.tenant_id, "manager", "owner-side-user")
    grants = "update gba.delegation_grants set "
    bump = ", revision = revision + 1 where id = %s"
    a, b = world.a.tenant_id, world.b.tenant_id
    for tenant_id, statement in (
        (a, grants + "permissions = '{booking.read}'" + bump),
        (a, grants + "expires_at = expires_at + interval '1 year'" + bump),
        (a, grants + "status = 'pending'" + bump),
        # A servicer cannot record the owner as the revoking side.
        (
            b,
            grants + "status = 'revoked', revoked_by_side = 'owner', revoked_by = created_by, "
            "revoked_at = now()" + bump,
        ),
        (a, grants + "status = 'revoked' where id = %s"),
        # Decision metadata cannot be rewritten on a later revision.
        (b, grants + "decided_by = created_by, decided_at = '2020-01-01T00:00:00Z'" + bump),
        (b, grants + "revoked_by = created_by" + bump),
        (b, "update gba.delegation_grant_members set display_name = 'CHANGED' where grant_id = %s"),
    ):
        with (
            owner_tenant_transaction(owner_conn, tenant_id),
            pytest.raises(psycopg.errors.CheckViolation),
            owner_conn.transaction(),
        ):
            owner_conn.execute(statement, (grant_id,))
    # No party can delete history: there is no delete policy, and the trigger is a backstop.
    for tenant_id, statement in (
        (a, "delete from gba.delegation_grants where id = %s"),
        (b, "delete from gba.delegation_grant_members where grant_id = %s"),
    ):
        with owner_tenant_transaction(owner_conn, tenant_id):
            assert owner_conn.execute(statement, (grant_id,)).rowcount == 0
    with owner_tenant_transaction(owner_conn, a):
        kept = owner_conn.execute(
            "select count(*) from gba.delegation_grant_members where grant_id = %s", (grant_id,)
        ).fetchone()
        assert kept == (1,)
    # Delegates must be company-wide members of the servicer; another company's user is refused.
    with (
        owner_tenant_transaction(owner_conn, world.b.tenant_id),
        pytest.raises(psycopg.errors.CheckViolation),
        owner_conn.transaction(),
    ):
        owner_conn.execute(
            "insert into gba.delegation_grant_members (owner_tenant_id, grant_id, "
            "servicer_tenant_id, user_id, display_name, added_by) "
            "values (%s, %s, %s, %s, 'FAKE outsider', %s)",
            (world.a.tenant_id, grant_id, world.b.tenant_id, outsider.user_id, owner_b.user_id),
        )
    async with tenant_transaction(app_pool, world.b.tenant_id) as conn:
        # The runtime role in the servicer context cannot issue in the owner's name.
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with conn.transaction():
                await conn.execute(
                    "insert into gba.delegation_grants (owner_tenant_id, id, servicer_tenant_id, "
                    "owner_display_name, permissions, expires_at, created_by) "
                    "values (%s, %s, %s, 'FAKE forged', '{booking.read}', "
                    "now() + interval '1 day', %s)",
                    (world.a.tenant_id, uuid7(), world.b.tenant_id, owner_b.user_id),
                )
    async with tenant_transaction(app_pool, world.a.tenant_id) as conn:
        # The owner may not add delegates in the servicer's name: the delegate check
        # or the insert policy refuses the row.
        with pytest.raises((psycopg.errors.InsufficientPrivilege, psycopg.errors.CheckViolation)):
            async with conn.transaction():
                await conn.execute(
                    "insert into gba.delegation_grant_members (owner_tenant_id, grant_id, "
                    "servicer_tenant_id, user_id, display_name, added_by) "
                    "values (%s, %s, %s, %s, 'FAKE forged', %s)",
                    (
                        world.a.tenant_id,
                        grant_id,
                        world.b.tenant_id,
                        outsider.user_id,
                        owner_a.user_id,
                    ),
                )
        await conn.execute(
            "select pg_catalog.set_config('gba.location_id', %s, true)", (str(world.a.location_id),)
        )
        assert (await (await conn.execute("select * from gba.delegation_grants")).fetchall()) == []
    async with unscoped_transaction(app_pool) as conn:
        assert (await (await conn.execute("select * from gba.delegation_grants")).fetchall()) == []
        assert (
            await (await conn.execute("select * from gba.delegation_grant_members")).fetchall()
        ) == []


@pytest.mark.parametrize("table", ["delegation_grants", "delegation_grant_members"])
async def test_delegation_scope_policy_damage_fails_readiness(
    client: httpx.AsyncClient, owner_conn: psycopg.Connection, table: str
) -> None:
    # Fixed test parameters; privileged schema damage is confined to the disposable database.
    try:
        owner_conn.execute(
            f"alter policy {table}_unrestricted_scope on gba.{table} using (true) with check (true)"
        )
        assert (await client.get("/health/ready")).status_code == 503
    finally:
        owner_conn.execute(
            f"alter policy {table}_unrestricted_scope on gba.{table} "
            "using (gba.current_location_id() is null) "
            "with check (gba.current_location_id() is null)"
        )


async def test_member_list_shows_only_the_requested_company(
    client: httpx.AsyncClient,
    world: BookingWorld,
    owner_b: FakeUser,
    owner_conn: psycopg.Connection,
    parties: Parties,
) -> None:
    # The delegate picker lists servicer members; one's own membership elsewhere is not one.
    add_membership(owner_conn, tenant_id=world.a.tenant_id, user_id=owner_b.user_id, role="artist")
    members = await client.get(
        f"/v1/salons/{world.b.tenant_id}/members",
        headers=parties.idp.bearer(owner_b.subject, email=owner_b.email),
    )
    assert members.status_code == 200, members.text
    assert [(item["user_id"], item["role"]) for item in members.json()] == [
        (str(owner_b.user_id), "owner")
    ]


async def test_owner_suspension_is_not_bypassed_by_a_grant(
    client: httpx.AsyncClient,
    parties: Parties,
    world: BookingWorld,
    owner_a: FakeUser,
    owner_b: FakeUser,
    dispatcher: FakeUser,
    owner_conn: psycopg.Connection,
) -> None:
    salon = f"/v1/salons/{world.a.tenant_id}"
    await parties.active_grant(owner_a, owner_b, [dispatcher])
    assert (
        await client.get(f"{salon}/workspace", headers=parties.headers(dispatcher))
    ).status_code == 200
    membership = add_membership(
        owner_conn, tenant_id=world.a.tenant_id, user_id=dispatcher.user_id, role="artist"
    )
    with owner_tenant_transaction(owner_conn, world.a.tenant_id):
        owner_conn.execute(
            "update gba.memberships set status = 'suspended' where id = %s", (membership,)
        )
    blocked = await client.get(f"{salon}/workspace", headers=parties.headers(dispatcher))
    assert blocked.status_code == 403
    me = (await client.get("/v1/me", headers=parties.headers(dispatcher))).json()
    assert [item["business_id"] for item in me["delegations"]] == [str(world.a.tenant_id)]
