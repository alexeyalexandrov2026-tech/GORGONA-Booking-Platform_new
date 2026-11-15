"""Authenticated showings use the shared PostgreSQL occupancy."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.booking import repository as repo
from gorgona_booking.booking.models import SlotConflictError
from gorgona_booking.booking.service import BookingService
from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from tests.integration.seed import FakeUser
from tests.integration.test_property_catalog import Catalog
from tests.integration.test_property_listings import (
    catalog,
    client,
    enabled,
    idp,
    manager_a,
    manager_b,
    unit,
)

pytestmark = pytest.mark.anyio
__all__ = ["catalog", "client", "enabled", "idp", "manager_a", "manager_b"]


def url(c: Catalog, showing_id: UUID) -> str:
    return f"/v1/businesses/{c.tenant}/property/showings/{showing_id}"


async def book(
    c: Catalog,
    object_id: UUID,
    prospect: str,
    staff: UUID | None = None,
    *,
    showing_id: UUID | None = None,
    key: str | None = None,
    **kwargs: object,
) -> httpx.Response:
    showing = showing_id or uuid7()
    return await c.client.put(
        url(c, showing),
        headers={**c.headers, "Idempotency-Key": key or str(uuid7())},
        json={
            "schema_version": 1,
            "object_id": str(object_id),
            "prospect_id": prospect,
            "host_resource_id": str(staff) if staff is not None else None,
            "starts_at": "2031-07-10T14:00:00Z",
            "ends_at": "2031-07-10T15:00:00Z",
            **kwargs,
        },
    )


async def test_object_conflict_and_cancellation_releases_both(
    enabled: Catalog, app_pool: RuntimePool
) -> None:
    target = await unit(enabled)
    prospect = await enabled.counterparty()
    showing = uuid7()
    saved = await book(
        enabled,
        target,
        prospect,
        enabled.world.artist_a1,
        showing_id=showing,
        key="create-showing-1",
    )
    assert saved.status_code == 200, saved.text
    clash = await book(enabled, target, prospect, enabled.world.artist_a2)
    assert clash.status_code == 409, clash.text
    headers = {**enabled.headers, "Idempotency-Key": "cancel-showing-1"}
    endpoint = f"{url(enabled, showing)}/cancel"
    cancelled = await enabled.client.post(endpoint, json={"schema_version": 1}, headers=headers)
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"
    again = await enabled.client.post(endpoint, json={"schema_version": 1}, headers=headers)
    assert again.json() == cancelled.json()

    replay = await book(
        enabled,
        target,
        prospect,
        enabled.world.artist_a1,
        showing_id=showing,
        key="create-showing-1",
    )
    assert replay.json() == saved.json()
    async with tenant_transaction(app_pool, enabled.tenant) as conn:
        allocations = await (
            await conn.execute(
                "select state from gba.resource_allocations "
                "where source_kind = 'property_showing' and source_id = %s",
                (showing,),
            )
        ).fetchall()
        assert allocations == [("released",), ("released",)]
    assert (await book(enabled, target, prospect, enabled.world.artist_a1)).is_success


async def test_concurrent_showings_on_different_objects_share_the_host(
    enabled: Catalog, app_pool: RuntimePool
) -> None:
    left, right = await unit(enabled), await unit(enabled)
    prospect = await enabled.counterparty()
    outcomes = await asyncio.gather(
        book(enabled, left, prospect, enabled.world.artist_a1),
        book(enabled, right, prospect, enabled.world.artist_a1),
    )
    assert sorted(o.status_code for o in outcomes) == [200, 409]
    async with tenant_transaction(app_pool, enabled.tenant) as conn:
        result = await (await conn.execute("select count(*) from gba.property_showings")).fetchone()
        assert result == (1,)
        result = await (
            await conn.execute(
                "select count(*) from gba.resource_allocations "
                "where source_kind = 'property_showing' and state = 'confirmed'"
            )
        ).fetchone()
        assert result == (2,)


async def test_showing_rejects_invalid_references_and_intervals(enabled: Catalog) -> None:
    target = await unit(enabled)
    prospect = await enabled.counterparty()
    missing = await book(enabled, target, str(uuid7()))
    assert missing.status_code == 422, missing.text
    wrong_host = await book(enabled, target, prospect, uuid7())
    assert wrong_host.status_code == 422, wrong_host.text
    backwards = await book(enabled, target, prospect, ends_at="2031-07-10T13:00:00Z")
    assert backwards.status_code == 422, backwards.text


@pytest.mark.parametrize("showing_first", [False, True])
async def test_showing_and_booking_share_the_host(
    enabled: Catalog, app_pool: RuntimePool, showing_first: bool
) -> None:
    target = await unit(enabled)
    prospect = await enabled.counterparty()
    request = enabled.world.request(datetime(2031, 7, 10, 14, tzinfo=UTC))
    service = BookingService(app_pool)
    if showing_first:
        assert (await book(enabled, target, prospect, enabled.world.artist_a1)).is_success
        with pytest.raises(SlotConflictError):
            await service.create_confirmed_booking(
                enabled.tenant, request, actor="test:showing", idempotency_key=None
            )
    else:
        await service.create_confirmed_booking(
            enabled.tenant, request, actor="test:showing", idempotency_key=None
        )
        clash = await book(enabled, target, prospect, enabled.world.artist_a1)
        assert clash.status_code == 409, clash.text


async def test_branch_reads_are_scoped_and_project_schedule_only(
    enabled: Catalog, manager_b: FakeUser
) -> None:
    target = await unit(enabled)
    prospect = await enabled.counterparty()
    saved = await book(enabled, target, prospect)
    assert saved.is_success, saved.text
    endpoint = url(enabled, UUID(saved.json()["showing_id"]))
    branch = enabled.member("manager", enabled.world.a.location_id)
    read = await enabled.client.get(endpoint, headers=branch)
    assert read.is_success, read.text
    assert "prospect_id" not in read.json()
    denied = await enabled.client.post(
        f"{endpoint}/cancel",
        json={"schema_version": 1},
        headers={**branch, "Idempotency-Key": str(uuid7())},
    )
    assert denied.status_code == 403, denied.text
    foreign = await enabled.client.get(
        endpoint, headers=enabled.idp.bearer(manager_b.subject, email=manager_b.email)
    )
    assert foreign.status_code == 403, foreign.text


async def test_database_rejects_a_showing_without_allocations(
    enabled: Catalog, app_pool: RuntimePool, manager_a: FakeUser
) -> None:
    target = await unit(enabled)
    prospect = await enabled.counterparty()
    saved = await book(enabled, target, prospect)
    assert saved.is_success, saved.text
    with pytest.raises(psycopg.errors.CheckViolation, match="requires all its allocations"):
        async with tenant_transaction(app_pool, enabled.tenant) as conn:
            await conn.execute(
                "insert into gba.property_showings (tenant_id, id, object_id, location_id, "
                "object_resource_id, prospect_id, starts_at, ends_at, recorded_by) "
                "select tenant_id, %s, object_id, location_id, resource_id, %s, "
                "'2031-07-11T14:00:00Z', '2031-07-11T15:00:00Z', %s "
                "from gba.property_showing_resources where object_id = %s",
                (uuid7(), UUID(prospect), manager_a.user_id, target),
            )


async def test_showing_waits_on_the_shared_host_lock(
    enabled: Catalog, app_pool: RuntimePool
) -> None:
    target = await unit(enabled)
    prospect = await enabled.counterparty()
    host = enabled.world.artist_a1
    async with (
        asyncio.TaskGroup() as group,
        tenant_transaction(app_pool, enabled.tenant) as locked,
    ):
        await repo.lock_resource_schedule(locked, enabled.tenant, host)
        pid = await (await locked.execute("select pg_backend_pid()")).fetchone()
        assert pid is not None
        contender = group.create_task(book(enabled, target, prospect, host))
        async with asyncio.timeout(10):
            while True:
                waiting = await (
                    await locked.execute(
                        "select exists (select 1 from pg_locks where locktype = 'advisory' "
                        "and not granted and %s = any(pg_blocking_pids(pid)))",
                        (pid[0],),
                    )
                ).fetchone()
                if waiting == (True,):
                    break
                assert not contender.done()
                await asyncio.sleep(0.025)
    response = contender.result()
    assert response.is_success, response.text


async def test_unaccepted_module_refuses_showings(catalog: Catalog) -> None:
    refused = await book(catalog, uuid7(), str(uuid7()))
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "MODULE_NOT_READY"
