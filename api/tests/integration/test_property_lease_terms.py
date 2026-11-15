"""PROPERTY-01 signed changes to an exclusive unit lease."""

import asyncio
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import owner_tenant_transaction
from gorgona_booking.db.schema_guard import assert_location_scope_ready
from gorgona_booking.errors import DatabaseUnavailableError
from tests.integration import test_property_leases as lease_tests
from tests.integration.configuration_support import Config
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.seed import FakeUser
from tests.integration.test_agreements import Agreements, draft
from tests.integration.test_property_catalog import Catalog
from tests.integration.test_property_leases import lease_body, leases, register, signed
from tests.integration.test_property_listings import unit

pytestmark = pytest.mark.anyio
agreements = lease_tests.agreements
catalog = lease_tests.catalog
client = lease_tests.client
enabled = lease_tests.enabled
idp = lease_tests.idp
manager_a = lease_tests.manager_a
manager_b = lease_tests.manager_b
__all__ = ["agreements", "catalog", "client", "enabled", "idp", "manager_a", "manager_b"]


def terms(c: Catalog, lease_id: UUID) -> str:
    return f"{leases(c)}/{lease_id}/terms"


async def change(
    c: Catalog,
    lease_id: UUID,
    action: str,
    agreement_revision: int,
    expected_revision: int = 1,
    *,
    key: str | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    return await c.client.post(
        terms(c, lease_id),
        json={
            "schema_version": 1,
            "action": action,
            "agreement_revision": agreement_revision,
            "expected_revision": expected_revision,
        },
        headers={**(headers or c.headers), "Idempotency-Key": key or str(uuid7())},
    )


async def amend(
    a: Agreements, subject: str, document: object, expected: int = 2, **dates: object
) -> int:
    partner = (await a.get(f"/agreements/{subject}")).json()["counterparty_id"]
    saved = await a.put(subject, draft(partner, expected_revision=expected, **dates))
    assert saved.is_success, saved.text
    result = await a.agree(subject, expected + 1, document={"document_id": document, "revision": 1})
    assert result.is_success, result.text
    return expected + 2


async def test_extend_signed_lease_preserves_registration(
    enabled: Catalog, agreements: Agreements
) -> None:
    document = (await agreements.create(file_id=await agreements.stored()))["document_id"]
    revised_document = (
        await agreements.create(title="FAKE signed extension", file_id=await agreements.stored())
    )["document_id"]
    object_id, lease_id = await unit(enabled), uuid7()
    subject = await signed(agreements, document)
    original = await register(enabled, lease_id, lease_body(object_id, subject), key="registration")
    assert original.is_success, original.text
    revision = await amend(agreements, subject, revised_document, effective_until="2027-01-31")
    extended = await change(enabled, lease_id, "extend", revision, key="extension")
    assert extended.status_code == 200, extended.text
    row = extended.json()
    assert (row["revision"], row["action"], row["agreement_revision"]) == (2, "extend", 4)
    assert (row["starts_on"], row["ends_on"], row["document_id"]) == (
        "2026-01-01",
        "2027-01-31",
        revised_document,
    )
    replay = await change(enabled, lease_id, "extend", revision, key="extension")
    assert (replay.status_code, replay.json()) == (200, row)
    registration_replay = await register(
        enabled, lease_id, lease_body(object_id, subject), key="registration"
    )
    assert registration_replay.json() == original.json()
    history = await enabled.client.get(terms(enabled, lease_id), headers=enabled.headers)
    assert history.is_success, history.text
    assert [(i["revision"], i["ends_on"]) for i in history.json()["items"]] == [
        (2, "2027-01-31"),
        (1, "2026-12-31"),
    ]


async def registered(
    c: Catalog, a: Agreements, object_id: UUID, document: object, **dates: object
) -> tuple[UUID, str]:
    contract = await signed(a, document, **dates)
    lease_id = uuid7()
    response = await register(c, lease_id, lease_body(object_id, contract))
    assert response.is_success, response.text
    return lease_id, contract


async def terminate(a: Agreements, contract: str, expected: int, last_day: str) -> int:
    result = await a.act(
        contract, "terminate", {"expected_revision": expected, "terminated_on": last_day}
    )
    assert result.is_success, result.text
    return expected + 1


async def test_conflicting_extension_rolls_back_and_retries_after_prestart_release(
    enabled: Catalog, agreements: Agreements
) -> None:
    document = (await agreements.create(file_id=await agreements.stored()))["document_id"]
    object_id = await unit(enabled)
    first, first_contract = await registered(
        enabled,
        agreements,
        object_id,
        document,
        effective_from="2030-01-01",
        effective_until="2030-06-30",
    )
    future, future_contract = await registered(
        enabled,
        agreements,
        object_id,
        document,
        effective_from="2030-07-01",
        effective_until="2030-12-31",
    )
    revision = await amend(
        agreements,
        first_contract,
        document,
        effective_from="2030-01-01",
        effective_until="2030-08-31",
    )
    refused = await change(enabled, first, "extend", revision, key="retry-overlap")
    assert (refused.status_code, refused.json()["error"]["code"]) == (409, "PROPERTY_LEASE_OVERLAP")
    original = await enabled.client.get(terms(enabled, first), headers=enabled.headers)
    assert [(i["revision"], i["ends_on"]) for i in original.json()["items"]] == [(1, "2030-06-30")]

    closure = await terminate(agreements, future_contract, 2, "2030-06-15")
    released = await change(enabled, future, "release", closure)
    assert released.is_success, released.text
    assert (released.json()["ends_on"], released.json()["terminated_on"]) == (None, "2030-06-15")
    retried = await change(enabled, first, "extend", revision, key="retry-overlap")
    assert retried.is_success, retried.text
    assert (retried.json()["revision"], retried.json()["ends_on"]) == (2, "2030-08-31")
    await registered(
        enabled,
        agreements,
        object_id,
        document,
        effective_from="2030-09-01",
        effective_until="2030-12-31",
    )


async def test_existing_term_can_be_released_after_disabling_property(
    enabled: Catalog, agreements: Agreements, manager_a: FakeUser
) -> None:
    document = (await agreements.create(file_id=await agreements.stored()))["document_id"]
    object_id = await unit(enabled)
    lease_id, contract = await registered(
        enabled,
        agreements,
        object_id,
        document,
        effective_from="2030-01-01",
        effective_until="2030-12-31",
    )
    revision = await amend(
        agreements,
        contract,
        document,
        effective_from="2030-01-01",
        effective_until="2031-01-31",
    )
    extension = await change(enabled, lease_id, "extend", revision, key="keep-extension")
    assert extension.is_success, extension.text
    closure = await terminate(agreements, contract, revision, "2030-06-30")
    config = Config(enabled.client, enabled.idp)
    await config.publish(
        manager_a, enabled.tenant, 2, ["booking_resources", "counterparties", "documents"]
    )
    refused = await change(enabled, lease_id, "extend", revision, 2)
    assert (refused.status_code, refused.json()["error"]["code"]) == (409, "MODULE_DISABLED")
    release = await change(enabled, lease_id, "release", closure, 2, key="mark-release")
    assert release.is_success, release.text
    assert (release.json()["revision"], release.json()["ends_on"]) == (3, "2030-06-30")
    again = await change(enabled, lease_id, "release", closure, 2, key="mark-release")
    assert again.json() == release.json()
    historical = await change(enabled, lease_id, "extend", revision, key="keep-extension")
    assert historical.json() == extension.json()
    terminal = await change(enabled, lease_id, "release", closure, 3)
    assert (terminal.status_code, terminal.json()["error"]["code"]) == (
        409,
        "PROPERTY_LEASE_RELEASED",
    )

    await config.publish(
        manager_a,
        enabled.tenant,
        3,
        ["booking_resources", "counterparties", "documents", "property"],
    )
    same_day = await signed(
        agreements, document, effective_from="2030-06-30", effective_until="2030-06-30"
    )
    overlap = await register(enabled, uuid7(), lease_body(object_id, same_day))
    assert (overlap.status_code, overlap.json()["error"]["code"]) == (409, "PROPERTY_LEASE_OVERLAP")
    await registered(
        enabled,
        agreements,
        object_id,
        document,
        effective_from="2030-07-01",
        effective_until="2030-12-31",
    )


async def test_extension_needs_current_stored_amendment_of_same_start(
    enabled: Catalog, agreements: Agreements
) -> None:
    document = (await agreements.create(file_id=await agreements.stored()))["document_id"]
    empty_document = (await agreements.create())["document_id"]
    lease_id, contract = await registered(enabled, agreements, await unit(enabled), document)
    old = await amend(agreements, contract, document, effective_until="2027-01-31")
    missing_file = await amend(
        agreements, contract, empty_document, expected=old, effective_until="2027-02-28"
    )
    for bad in (old, missing_file):
        denied = await change(enabled, lease_id, "extend", bad)
        assert (denied.status_code, denied.json()["error"]["code"]) == (422, "INVALID_REFERENCE")
    shifted = await amend(
        agreements,
        contract,
        document,
        expected=missing_file,
        effective_from="2026-02-01",
        effective_until="2027-03-31",
    )
    denied = await change(enabled, lease_id, "extend", shifted)
    assert (denied.status_code, denied.json()["error"]["code"]) == (422, "INVALID_REFERENCE")
    current = await amend(
        agreements, contract, document, expected=shifted, effective_until="2027-04-30"
    )
    partner = (await agreements.get(f"/agreements/{contract}")).json()["counterparty_id"]
    saved = await agreements.put(contract, draft(partner, expected_revision=current))
    assert saved.is_success, saved.text
    accepted = await change(enabled, lease_id, "extend", current)
    assert accepted.is_success, accepted.text
    assert accepted.json()["agreement_revision"] == current
    stale = await change(enabled, lease_id, "extend", current)
    assert (stale.status_code, stale.json()["error"]["code"]) == (
        409,
        "PROPERTY_LEASE_REVISION_CONFLICT",
    )


async def test_registration_waits_for_competing_term_extension(
    enabled: Catalog, agreements: Agreements, manager_a: FakeUser, app_pool: RuntimePool
) -> None:
    document = (await agreements.create(file_id=await agreements.stored()))["document_id"]
    object_id = await unit(enabled)
    lease_id, contract = await registered(
        enabled, agreements, object_id, document, effective_until="2026-06-30"
    )
    extension = await amend(agreements, contract, document, effective_until="2026-08-31")
    competing = await signed(
        agreements, document, effective_from="2026-07-01", effective_until="2026-12-31"
    )
    async with asyncio.TaskGroup() as group, tenant_transaction(app_pool, enabled.tenant) as locked:
        await locked.execute(
            "insert into gba.property_lease_term_events "
            "(tenant_id, lease_id, revision, action, agreement_revision, recorded_by) "
            "values (%s,%s,2,'extend',%s,%s)",
            (enabled.tenant, lease_id, extension, manager_a.user_id),
        )
        pid = await (await locked.execute("select pg_backend_pid()")).fetchone()
        assert pid is not None
        contender = group.create_task(register(enabled, uuid7(), lease_body(object_id, competing)))
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
    refused = contender.result()
    assert (refused.status_code, refused.json()["error"]["code"]) == (409, "PROPERTY_LEASE_OVERLAP")
    result = await enabled.client.get(terms(enabled, lease_id), headers=enabled.headers)
    assert result.json()["items"][0]["ends_on"] == "2026-08-31"


async def test_term_history_and_projection_use_company_boundary(
    enabled: Catalog, agreements: Agreements, manager_b: FakeUser, app_pool: RuntimePool
) -> None:
    document = (await agreements.create(file_id=await agreements.stored()))["document_id"]
    lease_id, contract = await registered(enabled, agreements, await unit(enabled), document)
    revision = await amend(agreements, contract, document, effective_until="2027-01-31")
    assert (await change(enabled, lease_id, "extend", revision)).is_success

    branch = enabled.member("manager", enabled.world.a.location_id)
    foreign = enabled.idp.bearer(manager_b.subject, email=manager_b.email)
    assert (await enabled.client.get(terms(enabled, lease_id), headers=branch)).status_code == 403
    assert (await enabled.client.get(terms(enabled, lease_id), headers=foreign)).status_code == 403
    assert (await change(enabled, lease_id, "extend", revision, headers=branch)).status_code == 403
    async with tenant_transaction(app_pool, enabled.tenant) as conn:
        with pytest.raises(psycopg.errors.CheckViolation):
            async with conn.transaction():
                await conn.execute(
                    "update gba.property_leases set term_revision = 3, occupied_through = ends_on "
                    "where id = %s",
                    (lease_id,),
                )
        await conn.execute(
            "select set_config('gba.location_id', %s, true)", (str(enabled.world.a.location_id),)
        )
        result = await conn.execute("select revision from gba.property_lease_term_events")
        assert await result.fetchall() == []
    with (
        pytest.raises(psycopg.errors.CheckViolation),
        owner_tenant_transaction(enabled.owner_conn, enabled.tenant),
    ):
        enabled.owner_conn.execute(
            "delete from gba.property_lease_term_events where lease_id = %s", (lease_id,)
        )


async def test_term_event_trigger_is_required(test_database: ProvisionedDatabase) -> None:
    async with (
        await psycopg.AsyncConnection.connect(test_database.owner_dsn) as owner,
        owner.transaction(force_rollback=True),
    ):
        await assert_location_scope_ready(owner)
        await owner.execute(
            "alter table gba.property_lease_term_events "
            "disable trigger property_lease_term_events_apply"
        )
        with pytest.raises(DatabaseUnavailableError):
            await assert_location_scope_ready(owner)


async def test_term_change_requires_read_committed(
    enabled: Catalog,
    agreements: Agreements,
    manager_a: FakeUser,
    test_database: ProvisionedDatabase,
) -> None:
    document = (await agreements.create(file_id=await agreements.stored()))["document_id"]
    lease_id, contract = await registered(enabled, agreements, await unit(enabled), document)
    revision = await amend(agreements, contract, document, effective_until="2027-01-31")
    async with (
        await psycopg.AsyncConnection.connect(test_database.app_dsn) as runtime,
        runtime.transaction(),
    ):
        await runtime.execute("set transaction isolation level repeatable read")
        await runtime.execute(
            "select set_config('gba.tenant_id', %s, true)", (str(enabled.tenant),)
        )
        with pytest.raises(psycopg.errors.SerializationFailure, match="read committed"):
            await runtime.execute(
                "insert into gba.property_lease_term_events "
                "(tenant_id, lease_id, revision, action, agreement_revision, recorded_by) "
                "values (%s,%s,2,'extend',%s,%s)",
                (enabled.tenant, lease_id, revision, manager_a.user_id),
            )
