"""Company groups in real PostgreSQL: consent, history and no data access (ADR-0018)."""

import asyncio
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.db.pool import RuntimePool, tenant_transaction, unscoped_transaction
from gorgona_booking.db.provisioning import add_membership, owner_tenant_transaction
from tests.integration import test_management_api as shared
from tests.integration.booking_support import BookingWorld
from tests.integration.seed import FakeUser, Salon, seed_salon, seed_user
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp


def _member(owner_conn: psycopg.Connection, tenant_id: UUID, role: str, label: str) -> FakeUser:
    user = seed_user(owner_conn, f"group-{label}-{uuid7()}")
    add_membership(owner_conn, tenant_id=tenant_id, user_id=user.user_id, role=role)
    return user


class Groups:
    def __init__(self, client: httpx.AsyncClient, idp: FakeIdp) -> None:
        self.client, self.idp = client, idp

    def headers(self, user: FakeUser, key: str | None = None) -> dict[str, str]:
        return {
            **self.idp.bearer(user.subject, email=user.email),
            "Idempotency-Key": key or str(uuid7()),
        }

    async def create(
        self,
        user: FakeUser,
        business: UUID,
        group_id: UUID,
        code: str = "HOLDING",
        key: str | None = None,
    ) -> httpx.Response:
        return await self.client.put(
            f"/v1/businesses/{business}/groups/{group_id}",
            json={"code": code, "name": f"FAKE {code} group"},
            headers=self.headers(user, key),
        )

    async def invite(
        self, user: FakeUser, business: UUID, group_id: UUID, member: UUID
    ) -> httpx.Response:
        return await self.client.put(
            f"/v1/businesses/{business}/groups/{group_id}/members/{member}",
            json={},
            headers=self.headers(user),
        )

    async def decide(
        self, user: FakeUser, business: UUID, group_id: UUID, action: str, revision: int
    ) -> httpx.Response:
        return await self.client.post(
            f"/v1/businesses/{business}/groups/{group_id}/{action}",
            json={"expected_revision": revision},
            headers=self.headers(user),
        )

    async def remove(
        self, user: FakeUser, business: UUID, group_id: UUID, member: UUID, revision: int
    ) -> httpx.Response:
        return await self.client.post(
            f"/v1/businesses/{business}/groups/{group_id}/members/{member}/remove",
            json={"expected_revision": revision},
            headers=self.headers(user),
        )

    async def view(self, user: FakeUser, business: UUID, group_id: UUID) -> httpx.Response:
        return await self.client.get(
            f"/v1/businesses/{business}/groups/{group_id}",
            headers=self.idp.bearer(user.subject, email=user.email),
        )


@pytest.fixture
def groups(client: httpx.AsyncClient, idp: FakeIdp) -> Groups:
    return Groups(client, idp)


@pytest.fixture
def owners(
    world: BookingWorld, owner_conn: psycopg.Connection
) -> tuple[FakeUser, FakeUser, Salon, FakeUser]:
    third = seed_salon(owner_conn, "group-third")
    return (
        _member(owner_conn, world.a.tenant_id, "owner", "owner-a"),
        _member(owner_conn, world.b.tenant_id, "owner", "owner-b"),
        third,
        _member(owner_conn, third.tenant_id, "owner", "owner-c"),
    )


async def test_consent_history_and_no_data_access(
    client: httpx.AsyncClient,
    groups: Groups,
    world: BookingWorld,
    owners: tuple[FakeUser, FakeUser, Salon, FakeUser],
    app_pool: RuntimePool,
) -> None:
    owner_a, owner_b, third, owner_c = owners
    a, b, c = world.a.tenant_id, world.b.tenant_id, third.tenant_id
    group_id, key = uuid7(), str(uuid7())
    created = await groups.create(owner_a, a, group_id, key=key)
    assert created.status_code == 200, created.text
    assert (created.json()["role"], created.json()["memberships"]) == ("organizer", [])
    assert (await groups.create(owner_a, a, group_id, key=key)).json() == created.json()
    reused = await groups.create(owner_a, a, uuid7(), code="OTHER", key=key)
    assert reused.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    for member in (b, c):
        assert (await groups.invite(owner_a, a, group_id, member)).status_code == 200
    seen_by_b = (await groups.view(owner_b, b, group_id)).json()
    assert seen_by_b["role"] == "member"
    assert [m["member_business_id"] for m in seen_by_b["memberships"]] == [str(b)]
    joined = await groups.decide(owner_b, b, group_id, "accept", 1)
    assert joined.status_code == 200, joined.text
    assert joined.json()["memberships"][0]["status"] == "active"
    assert joined.json()["memberships"][0]["member_name"] is not None
    # Another member never learns who else is invited or in the group.
    seen_by_c = (await groups.view(owner_c, c, group_id)).json()
    assert [m["member_business_id"] for m in seen_by_c["memberships"]] == [str(c)]
    organizer_view = (await groups.view(owner_a, a, group_id)).json()
    assert {m["member_business_id"]: m["status"] for m in organizer_view["memberships"]} == {
        str(b): "active",
        str(c): "invited",
    }

    # Membership grants nothing: each company still sees only its own rows.
    a_headers = groups.idp.bearer(owner_a.subject, email=owner_a.email)
    b_headers = groups.idp.bearer(owner_b.subject, email=owner_b.email)
    for headers, other in ((a_headers, b), (b_headers, a)):
        for path in (
            f"/v1/salons/{other}/bookings",
            f"/v1/salons/{other}/workspace",
            f"/v1/businesses/{other}",
            f"/v1/businesses/{other}/legal-entities",
            f"/v1/businesses/{other}/departments",
        ):
            assert (await client.get(path, headers=headers)).status_code == 403, path
    me = (await client.get("/v1/me", headers=a_headers)).json()
    assert [item["salon_id"] for item in me["memberships"]] == [str(a)]
    assert me["delegations"] == []

    left = await groups.decide(owner_b, b, group_id, "leave", 2)
    assert left.json()["memberships"][0]["status"] == "left"
    removed = await groups.remove(owner_a, a, group_id, c, 1)
    assert {m["member_business_id"]: m["status"] for m in removed.json()["memberships"]} == {
        str(b): "left",
        str(c): "removed",
    }
    # History stays; a fresh invitation is a new membership.
    assert (await groups.invite(owner_a, a, group_id, b)).status_code == 200
    statuses = sorted(
        m["status"] for m in (await groups.view(owner_a, a, group_id)).json()["memberships"]
    )
    assert statuses == ["invited", "left", "removed"]
    async with tenant_transaction(app_pool, a) as conn:
        actions = await (
            await conn.execute(
                "select action, count(*) from gba.audit_events "
                "where target_type = 'business_group' group by action order by action"
            )
        ).fetchall()
    assert actions == [
        ("business_group.created", 1),
        ("business_group.invited", 3),
        ("business_group.removed", 1),
    ]
    async with tenant_transaction(app_pool, b) as conn:
        actions = await (
            await conn.execute(
                "select action from gba.audit_events where target_type = 'business_group' "
                "order by occurred_at"
            )
        ).fetchall()
    assert actions == [("business_group.joined",), ("business_group.left",)]


async def test_parties_permissions_states_and_races(
    client: httpx.AsyncClient,
    groups: Groups,
    world: BookingWorld,
    owners: tuple[FakeUser, FakeUser, Salon, FakeUser],
    owner_conn: psycopg.Connection,
) -> None:
    owner_a, owner_b, third, owner_c = owners
    a, b, c = world.a.tenant_id, world.b.tenant_id, third.tenant_id
    artist = _member(owner_conn, a, "artist", "artist-a")
    manager = _member(owner_conn, a, "manager", "manager-a")
    assert (await groups.create(owner_b, a, uuid7())).status_code == 403
    assert (await groups.create(artist, a, uuid7())).status_code == 403
    group_id = uuid7()
    assert (await groups.create(manager, a, group_id)).status_code == 200
    assert (await groups.create(owner_a, a, uuid7())).status_code == 409  # same code
    for member, code in (
        (a, "GROUP_STATE_INVALID"),
        (uuid7(), "INVALID_REFERENCE"),
    ):
        response = await groups.invite(owner_a, a, group_id, member)
        assert response.json()["error"]["code"] == code
    assert (await groups.invite(owner_a, a, uuid7(), b)).status_code == 404
    assert (await groups.invite(owner_b, b, group_id, c)).status_code == 404
    assert (await groups.invite(owner_a, a, group_id, b)).status_code == 200
    assert (await groups.invite(owner_a, a, group_id, b)).status_code == 409
    # Only the member decides for itself; only the organizer removes.
    assert (await groups.decide(owner_a, a, group_id, "accept", 1)).status_code == 404
    assert (await groups.decide(owner_c, c, group_id, "accept", 1)).status_code == 404
    assert (await groups.remove(owner_b, b, group_id, b, 1)).status_code == 404
    assert (await groups.decide(owner_b, b, group_id, "accept", 2)).status_code == 409
    assert (await groups.decide(owner_b, b, group_id, "leave", 1)).json()["error"][
        "code"
    ] == "GROUP_STATE_INVALID"
    results = await asyncio.gather(
        groups.decide(owner_b, b, group_id, "accept", 1),
        groups.remove(owner_a, a, group_id, b, 1),
    )
    assert sorted(response.status_code for response in results) == [200, 409]
    assert (await groups.view(owner_c, c, group_id)).status_code == 404
    listed = await client.get(
        f"/v1/businesses/{c}/groups",
        headers=groups.idp.bearer(owner_c.subject, email=owner_c.email),
    )
    assert listed.json()["items"] == []


async def test_database_rules_hold_for_direct_sql(
    groups: Groups,
    world: BookingWorld,
    owners: tuple[FakeUser, FakeUser, Salon, FakeUser],
    owner_conn: psycopg.Connection,
    app_pool: RuntimePool,
) -> None:
    owner_a, owner_b, _, _ = owners
    a, b = world.a.tenant_id, world.b.tenant_id
    group_id = uuid7()
    assert (await groups.create(owner_a, a, group_id)).status_code == 200
    assert (await groups.invite(owner_a, a, group_id, b)).status_code == 200
    assert (await groups.decide(owner_b, b, group_id, "accept", 1)).status_code == 200
    members = "update gba.business_group_members set "
    bump = ", revision = revision + 1 where group_id = %s"
    for tenant_id, statement in (
        (a, members + "status = 'active'" + bump),
        (b, members + "status = 'removed', ended_by = invited_by, ended_at = now()" + bump),
        (b, members + "decided_by = invited_by" + bump),
        (b, members + "member_tenant_id = organizer_tenant_id" + bump),
    ):
        with (
            owner_tenant_transaction(owner_conn, tenant_id),
            pytest.raises(psycopg.errors.CheckViolation),
            owner_conn.transaction(),
        ):
            owner_conn.execute(statement, (group_id,))
    # No update or delete policy exists for group identities: nothing can be targeted.
    for tenant_id, statement in (
        (a, "update gba.business_groups set name = 'CHANGED' where id = %s"),
        (a, "delete from gba.business_groups where id = %s"),
        (b, "delete from gba.business_group_members where group_id = %s"),
    ):
        with owner_tenant_transaction(owner_conn, tenant_id):
            assert owner_conn.execute(statement, (group_id,)).rowcount == 0
    async with tenant_transaction(app_pool, b) as conn:
        # A member cannot create a group or an invitation in the organizer's name.
        for statement, params in (
            (
                "insert into gba.business_groups (organizer_tenant_id, id, code, name, "
                "organizer_display_name, created_by) values (%s, %s, 'FORGED', 'FAKE', 'FAKE', %s)",
                (a, uuid7(), owner_b.user_id),
            ),
            (
                "insert into gba.business_group_members (organizer_tenant_id, group_id, "
                "member_tenant_id, invited_by) values (%s, %s, %s, %s)",
                (a, group_id, world.b.tenant_id, owner_b.user_id),
            ),
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                async with conn.transaction():
                    await conn.execute(statement, params)
        await conn.execute(
            "select pg_catalog.set_config('gba.location_id', %s, true)", (str(world.b.location_id),)
        )
        assert (await (await conn.execute("select * from gba.business_groups")).fetchall()) == []
    async with unscoped_transaction(app_pool) as conn:
        assert (await (await conn.execute("select * from gba.business_groups")).fetchall()) == []
        assert (
            await (await conn.execute("select * from gba.business_group_members")).fetchall()
        ) == []


@pytest.mark.parametrize("table", ["business_groups", "business_group_members"])
async def test_group_scope_policy_damage_fails_readiness(
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


async def test_decision_after_a_committed_removal_is_a_stale_revision(
    groups: Groups,
    world: BookingWorld,
    owners: tuple[FakeUser, FakeUser, Salon, FakeUser],
) -> None:
    # Whichever side commits first, the other sees a stale revision, not a missing record.
    owner_a, owner_b, _, _ = owners
    a, b = world.a.tenant_id, world.b.tenant_id
    group_id = uuid7()
    assert (await groups.create(owner_a, a, group_id)).status_code == 200
    assert (await groups.invite(owner_a, a, group_id, b)).status_code == 200
    assert (await groups.remove(owner_a, a, group_id, b, 1)).status_code == 200
    late = await groups.decide(owner_b, b, group_id, "accept", 1)
    assert (late.status_code, late.json()["error"]["code"]) == (409, "CONFLICT")
    ended = await groups.decide(owner_b, b, group_id, "accept", 2)
    assert ended.json()["error"]["code"] == "GROUP_STATE_INVALID"
