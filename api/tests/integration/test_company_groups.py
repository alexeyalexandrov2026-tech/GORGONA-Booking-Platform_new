"""Groups never substitute consent or delegation for a company's own boundary."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.auth.permissions import Permission
from gorgona_booking.auth.principal import Principal
from gorgona_booking.business.company_groups import save_group
from gorgona_booking.business.group_contracts import GroupInput
from gorgona_booking.business.group_reports import booking_report
from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import add_membership, owner_tenant_transaction
from gorgona_booking.db.schema_guard import GROUP_TABLES
from gorgona_booking.errors import DatabaseUnavailableError
from gorgona_booking.tenancy.authorization import authorized_tenant
from tests.integration import test_delegations as d
from tests.integration.booking_support import BookingWorld
from tests.integration.seed import seed_other_branch, seed_salon
from tests.support.fake_idp import FakeIdp


@pytest.mark.parametrize(
    "cause", ["not_designated", "wrong_operator", "expired", "suspended", "not_consented"]
)
async def test_group_report_cannot_use_other_authority(
    client: httpx.AsyncClient,
    world: BookingWorld,
    parties: d.Parties,
    idp: FakeIdp,
    owner_conn: psycopg.Connection,
    cause: str,
) -> None:
    _group_id, path, invitation_id = await accepted_group(client, world, parties, idp)
    booking = await client.post(
        f"/v1/salons/{world.a.tenant_id}/bookings",
        headers=d._headers(idp, parties.owner_a),
        json=d._booking(world),
    )
    assert booking.status_code == 201, booking.text
    if cause == "not_designated":
        await d._grant(client, idp, world, parties, permissions=["report.booking.read"])
    elif cause == "wrong_operator":
        third = seed_salon(owner_conn, "fake-third-serving-company")
        third_membership = add_membership(
            owner_conn, tenant_id=third.tenant_id, user_id=parties.owner_b.user_id, role="owner"
        )
        grant_id = uuid7()
        grant = await client.put(
            d._grant_path(world.a, grant_id),
            headers=d._headers(idp, parties.owner_a),
            json=d._terms(third.tenant_id, permissions=["report.booking.read"]),
        )
        assert grant.status_code == 200, grant.text
        designated = await client.put(
            d._delegate_path(third, grant_id, third_membership),
            headers=d._headers(idp, parties.owner_b),
        )
        assert designated.status_code == 200, designated.text
    else:
        grant_id = await report_grant(client, world, parties, idp, owner_conn)
        if cause == "expired":
            with owner_tenant_transaction(owner_conn, world.a.tenant_id):
                owner_conn.execute(
                    "insert into gba.delegation_grant_versions "
                    "(tenant_id, grant_id, grantee_business_id, revision, state, purpose, "
                    "permissions, "
                    "valid_from, valid_until, created_by) values (%s, %s, %s, 2, 'active', "
                    "'FAKE expired', "
                    "array['report.booking.read'], now() - interval '2 days', now() - interval "
                    "'1 day', %s)",
                    (world.a.tenant_id, grant_id, world.b.tenant_id, parties.owner_a.user_id),
                )
        elif cause == "suspended":
            with owner_tenant_transaction(owner_conn, world.b.tenant_id):
                owner_conn.execute(
                    "update gba.memberships set status = 'suspended' where tenant_id = %s and "
                    "user_id = %s",
                    (world.b.tenant_id, parties.owner_b.user_id),
                )
        else:
            withdrawal = await client.put(
                f"/v1/businesses/{world.a.tenant_id}/group-invitations/{invitation_id}/consent",
                headers=d._headers(idp, parties.owner_a),
                json={"expected_revision": 1, "state": "withdrawn"},
            )
            assert withdrawal.status_code == 200, withdrawal.text
    result = await report(client, path, parties, idp)
    if cause == "suspended":
        assert result.status_code == 403
    else:
        assert result.status_code == 200, result.text
        assert result.json()["items"] == result.json()["sources"] == []


async def test_report_filters_branch_without_enabling_booking_reads(
    client: httpx.AsyncClient,
    world: BookingWorld,
    parties: d.Parties,
    idp: FakeIdp,
    owner_conn: psycopg.Connection,
) -> None:
    _group_id, path, _invitation_id = await accepted_group(client, world, parties, idp)
    other_location, other_resource = seed_other_branch(owner_conn, world.a)
    for body in (
        d._booking(world),
        d._booking(
            world, hour=14, location_id=str(other_location), resource_id=str(other_resource)
        ),
    ):
        created = await client.post(
            f"/v1/salons/{world.a.tenant_id}/bookings",
            headers=d._headers(idp, parties.owner_a),
            json=body,
        )
        assert created.status_code == 201, created.text
    grant_id = await report_grant(
        client, world, parties, idp, owner_conn, location_id=str(world.a.location_id)
    )
    current = await report(client, path, parties, idp)
    assert current.status_code == 200, current.text
    assert len(current.json()["items"]) == 1
    assert current.json()["items"][0]["booking_count"] == 1
    assert current.json()["sources"][0]["location_id"] == str(world.a.location_id)
    assert current.json()["sources"][0]["grant_id"] == str(grant_id)
    # No direct membership in A: report-only permission is insufficient for its bookings API.
    assert (
        await client.get(
            f"/v1/salons/{world.a.tenant_id}/bookings", headers=d._headers(idp, parties.owner_b)
        )
    ).status_code == 403


@pytest.mark.parametrize("damage", ["missing", "widened", "extra"])
async def test_group_boundaries_fail_closed(
    client: httpx.AsyncClient,
    world: BookingWorld,
    parties: d.Parties,
    idp: FakeIdp,
    owner_conn: psycopg.Connection,
    damage: str,
) -> None:
    _group_id, path = await group(client, world, parties, idp)
    try:
        if damage == "extra":
            owner_conn.execute(
                "create policy FAKE_unsafe on gba.company_group_consents for select using (true)"
            )
        else:
            owner_conn.execute(
                "drop policy company_group_consents_operator_read on gba.company_group_consents"
            )
            if damage == "widened":
                owner_conn.execute(
                    "create policy company_group_consents_operator_read on "
                    "gba.company_group_consents for select using (true)"
                )
        denied = await report(client, path, parties, idp)
        assert denied.status_code == 503, denied.text
        assert (await client.get("/health/ready")).status_code == 503
    finally:
        if damage == "extra":
            owner_conn.execute("drop policy FAKE_unsafe on gba.company_group_consents")
        else:
            if damage == "widened":
                owner_conn.execute(
                    "drop policy company_group_consents_operator_read on gba.company_group_consents"
                )
            owner_conn.execute(
                "create policy company_group_consents_operator_read on "
                "gba.company_group_consents for select using "
                "(operator_business_id = gba.current_tenant_id())"
            )


async def test_group_metadata_is_scoped_and_reporting_rejects_old_snapshots(
    client: httpx.AsyncClient,
    world: BookingWorld,
    parties: d.Parties,
    idp: FakeIdp,
    app_pool: RuntimePool,
) -> None:
    group_id, _path, _invitation_id = await accepted_group(client, world, parties, idp)
    for guc, value in (
        ("gba.location_id", world.b.location_id),
        ("gba.delegation_grant_id", uuid7()),
    ):
        async with tenant_transaction(app_pool, world.b.tenant_id) as conn:
            await conn.execute("select set_config(%s, %s, true)", (guc, str(value)))
            for table in GROUP_TABLES:
                assert await (await conn.execute(f"select * from gba.{table}")).fetchall() == []
    principal = Principal(parties.owner_b.user_id, "FAKE group operator", frozenset())
    async with app_pool.connection() as conn, conn.transaction():
        await conn.execute("set transaction isolation level repeatable read")
        now = datetime.now(UTC)
        with pytest.raises(DatabaseUnavailableError, match="READ COMMITTED"):
            await booking_report(
                conn,
                principal,
                world.b.tenant_id,
                group_id,
                from_at=now,
                until_at=now + timedelta(days=1),
                after=None,
                limit=25,
            )


pytestmark = pytest.mark.anyio
client, idp, parties = d.client, d.idp, d.parties


@pytest.mark.parametrize("side", ["participant", "operator"])
async def test_withdrawal_waits_for_inflight_report_and_next_report_sees_it(
    client: httpx.AsyncClient,
    world: BookingWorld,
    parties: d.Parties,
    idp: FakeIdp,
    app_pool: RuntimePool,
    side: str,
) -> None:
    group_id, path, invitation_id = await accepted_group(client, world, parties, idp)
    principal = Principal(parties.owner_b.user_id, "FAKE operator", frozenset())
    async with authorized_tenant(
        app_pool, principal, world.b.tenant_id, Permission.GROUP_MANAGE, exclusive="company-groups"
    ) as access:
        now = datetime.now(UTC)
        await booking_report(
            access.conn,
            principal,
            world.b.tenant_id,
            group_id,
            from_at=now,
            until_at=now + timedelta(days=1),
            after=None,
            limit=25,
        )

        async def withdraw() -> httpx.Response:
            if side == "participant":
                return await client.put(
                    f"/v1/businesses/{world.a.tenant_id}/group-invitations/{invitation_id}/consent",
                    headers=d._headers(idp, parties.owner_a),
                    json={"expected_revision": 1, "state": "withdrawn"},
                )
            return await client.post(
                f"{path}/invitations/{invitation_id}/withdraw",
                headers=d._headers(idp, parties.owner_b),
                json={"expected_revision": 1, "state": "withdrawn"},
            )

        task = asyncio.create_task(withdraw())
        try:
            await asyncio.sleep(0.1)
            assert not task.done(), "withdrawal must wait for the in-flight report transaction"
        except BaseException:
            task.cancel()
            raise
    withdrawn = await asyncio.wait_for(task, timeout=5)
    assert withdrawn.status_code == 200, withdrawn.text
    current = await report(client, path, parties, idp)
    assert current.json()["sources"] == []
    assert current.json()["excluded_business_ids"] == []


async def group(
    client: httpx.AsyncClient, world: BookingWorld, parties: d.Parties, idp: FakeIdp
) -> tuple[UUID, str]:
    group_id = uuid7()
    path = f"/v1/businesses/{world.b.tenant_id}/groups/{group_id}"
    auth = d._headers(idp, parties.owner_b)
    body = {"expected_revision": 0, "code": "FAKE_GROUP", "name": "FAKE independent companies"}
    response = await client.put(path, headers=auth, json=body)
    assert response.status_code == 200, response.text
    assert (await client.put(path, headers=auth, json=body)).json() == response.json()
    return group_id, path


async def test_group_versions_replay_and_owner_authority(
    client: httpx.AsyncClient, world: BookingWorld, parties: d.Parties, idp: FakeIdp
) -> None:
    _group_id, path = await group(client, world, parties, idp)
    update = {"expected_revision": 1, "code": "FAKE_GROUP", "name": "FAKE renamed group"}
    response = await client.put(path, headers=d._headers(idp, parties.owner_b), json=update)
    assert response.status_code == 200, response.text
    assert response.json()["revision"] == 2
    old = await client.get(path, headers=d._headers(idp, parties.owner_b), params={"revision": 1})
    assert old.json()["name"] == "FAKE independent companies"
    assert (
        await client.put(path, headers=d._headers(idp, parties.owner_b), json=update)
    ).status_code == 409
    assert (await client.get(path, headers=d._headers(idp, parties.delegate))).status_code == 403
    foreign = await client.get(path, headers=d._headers(idp, parties.owner_a))
    assert foreign.status_code == 403


async def test_explicit_participant_consent_is_independent_of_report_grant(
    client: httpx.AsyncClient, world: BookingWorld, parties: d.Parties, idp: FakeIdp
) -> None:
    _group_id, path = await group(client, world, parties, idp)
    invite_id = uuid7()
    invitation = f"{path}/invitations/{invite_id}"
    auth = d._headers(idp, parties.owner_b)
    response = await client.put(
        invitation, headers=auth, json={"participant_business_id": str(world.a.tenant_id)}
    )
    assert response.status_code == 200, response.text
    incoming = f"/v1/businesses/{world.a.tenant_id}/group-invitations/{invite_id}/consent"
    accepted = await client.put(
        incoming,
        headers=d._headers(idp, parties.owner_a),
        json={"expected_revision": 0, "state": "accepted"},
    )
    assert accepted.status_code == 200, accepted.text
    now = datetime.now(UTC)
    params = {
        "from_at": (now - timedelta(days=1)).isoformat(),
        "until_at": (now + timedelta(days=1)).isoformat(),
    }
    report = await client.get(f"{path}/booking-report", headers=auth, params=params)
    assert report.status_code == 200, report.text
    assert report.json()["items"] == []
    assert report.json()["excluded_business_ids"] == [str(world.a.tenant_id)]
    withdrawn = await client.put(
        incoming,
        headers=d._headers(idp, parties.owner_a),
        json={"expected_revision": 1, "state": "withdrawn"},
    )
    assert withdrawn.status_code == 200, withdrawn.text
    report = await client.get(f"{path}/booking-report", headers=auth, params=params)
    assert report.json()["excluded_business_ids"] == []
    assert report.json()["items"] == []


async def test_group_command_rolls_back_identity_version_audit_and_receipt(
    world: BookingWorld, parties: d.Parties, app_pool: RuntimePool
) -> None:
    principal = Principal(parties.owner_b.user_id, "FAKE operator", frozenset())

    async def abort_after_save() -> None:
        async with authorized_tenant(
            app_pool,
            principal,
            world.b.tenant_id,
            Permission.GROUP_MANAGE,
            exclusive="company-groups",
        ) as access:
            await save_group(
                access.conn,
                business_id=world.b.tenant_id,
                group_id=uuid7(),
                user_id=principal.user_id,
                actor=access.actor,
                key=str(uuid7()),
                body=GroupInput(expected_revision=0, code="FAKE_ABORT", name="FAKE group"),
            )
            raise RuntimeError("FAKE abort after save")

    with pytest.raises(RuntimeError, match="FAKE abort after save"):
        await abort_after_save()
    async with tenant_transaction(app_pool, world.b.tenant_id) as conn:
        for table in ("company_groups", "company_group_versions", "idempotency_keys"):
            assert await (await conn.execute(f"select count(*) from gba.{table}")).fetchone() == (
                0,
            )
        assert await (
            await conn.execute("select count(*) from gba.audit_events where action = 'group.saved'")
        ).fetchone() == (0,)


async def test_database_preserves_group_identity_history_and_consent(
    client: httpx.AsyncClient,
    world: BookingWorld,
    parties: d.Parties,
    idp: FakeIdp,
    owner_conn: psycopg.Connection,
) -> None:
    group_id, _path, invitation_id = await accepted_group(client, world, parties, idp)
    with owner_tenant_transaction(owner_conn, world.b.tenant_id):
        for sql, identity in (
            ("update gba.company_groups set code = 'FAKE_CHANGED' where id = %s", group_id),
            ("delete from gba.company_groups where id = %s", group_id),
            (
                "update gba.company_group_versions set name = 'FAKE_CHANGED' where group_id = %s",
                group_id,
            ),
            ("delete from gba.company_group_versions where group_id = %s", group_id),
            ("delete from gba.company_group_invitations where id = %s", invitation_id),
        ):
            with pytest.raises(psycopg.errors.CheckViolation), owner_conn.transaction():
                owner_conn.execute(sql, (identity,))
        with pytest.raises(psycopg.errors.CheckViolation), owner_conn.transaction():
            owner_conn.execute(
                "insert into gba.company_group_versions "
                "(tenant_id, group_id, revision, name, created_by) values (%s, %s, 3, 'FAKE', %s)",
                (world.b.tenant_id, group_id, parties.owner_b.user_id),
            )
    with owner_tenant_transaction(owner_conn, world.a.tenant_id):
        for sql in (
            "update gba.company_group_consents set state = 'withdrawn' where invitation_id = %s",
            "delete from gba.company_group_consents where invitation_id = %s",
        ):
            with pytest.raises(psycopg.errors.CheckViolation), owner_conn.transaction():
                owner_conn.execute(sql, (invitation_id,))
        assert owner_conn.execute(
            "select revision, state from gba.company_group_consents where invitation_id = %s",
            (invitation_id,),
        ).fetchall() == [(1, "accepted")]


async def accepted_group(
    client: httpx.AsyncClient, world: BookingWorld, parties: d.Parties, idp: FakeIdp
) -> tuple[UUID, str, UUID]:
    group_id, path = await group(client, world, parties, idp)
    invitation_id = uuid7()
    invited = await client.put(
        f"{path}/invitations/{invitation_id}",
        headers=d._headers(idp, parties.owner_b),
        json={"participant_business_id": str(world.a.tenant_id)},
    )
    assert invited.status_code == 200, invited.text
    accepted = await client.put(
        f"/v1/businesses/{world.a.tenant_id}/group-invitations/{invitation_id}/consent",
        headers=d._headers(idp, parties.owner_a),
        json={"expected_revision": 0, "state": "accepted"},
    )
    assert accepted.status_code == 200, accepted.text
    return group_id, path, invitation_id


async def report(
    client: httpx.AsyncClient, path: str, parties: d.Parties, idp: FakeIdp
) -> httpx.Response:
    starts = datetime.fromisoformat(d._start(11))
    return await client.get(
        f"{path}/booking-report",
        headers=d._headers(idp, parties.owner_b),
        params={
            "from_at": (starts - timedelta(days=1)).isoformat(),
            "until_at": (starts + timedelta(days=1)).isoformat(),
        },
    )


async def report_grant(
    client: httpx.AsyncClient,
    world: BookingWorld,
    parties: d.Parties,
    idp: FakeIdp,
    owner_conn: psycopg.Connection,
    **changes: object,
) -> UUID:
    grant_id = await d._grant(
        client, idp, world, parties, permissions=["report.booking.read"], **changes
    )
    with owner_tenant_transaction(owner_conn, world.b.tenant_id):
        member = owner_conn.execute(
            "select id from gba.memberships where tenant_id = %s and user_id = %s",
            (world.b.tenant_id, parties.owner_b.user_id),
        ).fetchone()
    assert member is not None
    designated = await d._designate(client, idp, world, parties, grant_id, member[0])
    assert designated.status_code == 200, designated.text
    return grant_id


@pytest.mark.parametrize("withdrawal", ["consent", "invitation", "grant"])
async def test_counts_need_consent_and_current_designated_report_grant(
    client: httpx.AsyncClient,
    world: BookingWorld,
    parties: d.Parties,
    idp: FakeIdp,
    owner_conn: psycopg.Connection,
    app_pool: RuntimePool,
    withdrawal: str,
) -> None:
    _group_id, path, invitation_id = await accepted_group(client, world, parties, idp)
    add_membership(
        owner_conn, tenant_id=world.a.tenant_id, user_id=parties.owner_b.user_id, role="owner"
    )
    booking = await client.post(
        f"/v1/salons/{world.a.tenant_id}/bookings",
        headers=d._headers(idp, parties.owner_a),
        json=d._booking(world),
    )
    assert booking.status_code == 201, booking.text
    # A direct owner of both companies still needs designation and a report-only grant.
    assert (await report(client, path, parties, idp)).json()["items"] == []
    grant_id = await report_grant(
        client, world, parties, idp, owner_conn, location_id=str(world.a.location_id)
    )
    current = await report(client, path, parties, idp)
    assert current.status_code == 200, current.text
    assert current.json()["excluded_business_ids"] == []
    assert current.json()["items"] == [
        {
            "owner_business_id": str(world.a.tenant_id),
            "legal_entity_id": None,
            "legal_entity_assignment": "unassigned",
            "location_id": str(world.a.location_id),
            "status": "CONFIRMED",
            "booking_count": 1,
        }
    ]
    async with tenant_transaction(app_pool, world.b.tenant_id) as conn:
        assert await d._count(app_pool, world.b.tenant_id, "select count(*) from gba.bookings") == 0
        row = await (
            await conn.execute("select current_setting('gba.delegation_grant_id', true)")
        ).fetchone()
        assert row in [(None,), ("",)]
    if withdrawal == "consent":
        endpoint = f"/v1/businesses/{world.a.tenant_id}/group-invitations/{invitation_id}/consent"
        withdrawn = await client.put(
            endpoint,
            headers=d._headers(idp, parties.owner_a),
            json={"expected_revision": 1, "state": "withdrawn"},
        )
    elif withdrawal == "invitation":
        withdrawn = await client.post(
            f"{path}/invitations/{invitation_id}/withdraw",
            headers=d._headers(idp, parties.owner_b),
            json={"expected_revision": 1, "state": "withdrawn"},
        )
    else:
        withdrawn = await d._revoke(client, idp, world, parties, grant_id, 1)
    assert withdrawn.status_code == 200, withdrawn.text
    assert (await report(client, path, parties, idp)).json()["items"] == []


async def test_invitation_replay_duplicates_forgery_withdrawal_and_terminal_consent(
    client: httpx.AsyncClient, world: BookingWorld, parties: d.Parties, idp: FakeIdp
) -> None:
    _group_id, path = await group(client, world, parties, idp)
    invitation_id = uuid7()
    body = {"participant_business_id": str(world.a.tenant_id)}
    auth = d._headers(idp, parties.owner_b)
    endpoint = f"{path}/invitations/{invitation_id}"
    first = await client.put(endpoint, headers=auth, json=body)
    assert first.status_code == 200, first.text
    assert (await client.put(endpoint, headers=auth, json=body)).json() == first.json()
    assert (
        await client.put(f"{path}/invitations/{uuid7()}", headers=auth, json=body)
    ).status_code == 422
    assert (
        await client.put(
            f"{path}/invitations/{uuid7()}", headers=d._headers(idp, parties.owner_b), json=body
        )
    ).status_code == 409
    endpoint = f"/v1/businesses/{world.a.tenant_id}/group-invitations/{invitation_id}/consent"
    terms = {"expected_revision": 0, "state": "accepted"}
    assert (
        await client.put(endpoint, headers=d._headers(idp, parties.owner_b), json=terms)
    ).status_code == 403
    auth = d._headers(idp, parties.owner_a)
    first = await client.put(endpoint, headers=auth, json=terms)
    assert first.status_code == 200, first.text
    assert (await client.put(endpoint, headers=auth, json=terms)).json() == first.json()
    assert (
        await client.put(endpoint, headers=d._headers(idp, parties.owner_a), json=terms)
    ).status_code == 409
    withdraw = await client.put(
        endpoint,
        headers=d._headers(idp, parties.owner_a),
        json={"expected_revision": 1, "state": "withdrawn"},
    )
    assert withdraw.status_code == 200, withdraw.text
    assert (
        await client.put(
            endpoint,
            headers=d._headers(idp, parties.owner_a),
            json={"expected_revision": 2, "state": "accepted"},
        )
    ).status_code == 409
    # Replaying old consent is only a receipt; it must never restore current consent.
    assert (await client.put(endpoint, headers=auth, json=terms)).json() == first.json()
    page = await client.get(f"{path}/invitations", headers=d._headers(idp, parties.owner_b))
    assert page.json()["items"][0]["consent_state"] == "withdrawn"
