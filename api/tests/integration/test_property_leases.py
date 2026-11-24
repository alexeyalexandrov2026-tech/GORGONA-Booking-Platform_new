"""PROPERTY-01 exclusive unit leases with signed, stored terms."""

import asyncio
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import owner_tenant_transaction
from gorgona_booking.db.schema_guard import assert_location_scope_ready
from gorgona_booking.errors import DatabaseUnavailableError
from tests.integration import test_property_catalog as catalog_tests
from tests.integration.configuration_support import Config
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.seed import FakeUser
from tests.integration.test_agreements import TODAY, Agreements, draft
from tests.integration.test_property_catalog import Catalog
from tests.integration.test_property_listings import unit

pytestmark = pytest.mark.anyio
client = catalog_tests.client
idp = catalog_tests.idp
manager_a = catalog_tests.manager_a
manager_b = catalog_tests.manager_b
catalog = catalog_tests.catalog
enabled = catalog_tests.enabled
__all__ = ["catalog", "client", "enabled", "idp", "manager_a", "manager_b"]


@pytest.fixture
async def agreements(enabled: Catalog, manager_a: FakeUser) -> Agreements:
    await Config(enabled.client, enabled.idp).publish(
        manager_a,
        enabled.tenant,
        1,
        ["booking_resources", "counterparties", "documents", "property"],
    )
    return Agreements(enabled.client, enabled.tenant, manager_a, enabled.idp)


def leases(c: Catalog) -> str:
    return f"/v1/businesses/{c.tenant}/property/leases"


def lease_body(object_id: UUID, subject: str, revision: int = 2) -> dict[str, object]:
    return {
        "schema_version": 1,
        "object_id": str(object_id),
        "agreement_id": subject,
        "agreement_revision": revision,
    }


async def register(
    c: Catalog,
    lease_id: UUID,
    body: dict[str, object],
    *,
    key: str | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    return await c.client.put(
        f"{leases(c)}/{lease_id}",
        json=body,
        headers={**(headers or c.headers), "Idempotency-Key": key or str(uuid7())},
    )


async def signed(agreements: Agreements, document: object, **terms: object) -> str:
    partner = await agreements.counterparty()
    subject = await agreements.drafted(partner, **terms)
    result = await agreements.agree(subject, 1, document={"document_id": document, "revision": 1})
    assert result.status_code == 200, result.text
    return subject


async def test_register_signed_unit_lease(
    enabled: Catalog, agreements: Agreements, manager_a: FakeUser
) -> None:
    document = (await agreements.create(file_id=await agreements.stored()))["document_id"]
    object_id, lease_id = await unit(enabled), uuid7()
    subject = await signed(agreements, document)
    body = lease_body(object_id, subject)
    original = await register(enabled, lease_id, body, key="record-first-lease")
    assert original.status_code == 200, original.text
    result = original.json()
    assert result["lease_id"] == str(lease_id)
    assert (result["object_id"], result["agreement_id"], result["agreement_revision"]) == (
        str(object_id),
        subject,
        2,
    )
    assert (result["starts_on"], result["ends_on"]) == ("2026-01-01", "2026-12-31")
    assert (result["document_id"], result["document_revision"]) == (document, 1)
    assert (
        await enabled.client.get(f"{leases(enabled)}/{lease_id}", headers=enabled.headers)
    ).json() == result
    page = await enabled.client.get(leases(enabled), headers=enabled.headers)
    assert page.json()["items"] == [result]
    await Config(enabled.client, enabled.idp).publish(
        manager_a, enabled.tenant, 2, ["booking_resources", "counterparties", "documents"]
    )
    replay = await register(enabled, lease_id, body, key="record-first-lease")
    assert (replay.status_code, replay.json()) == (200, result)
    denied = await register(enabled, uuid7(), body)
    assert (denied.status_code, denied.json()["error"]["code"]) == (409, "MODULE_DISABLED")


async def test_unit_filter_keeps_the_company_list(enabled: Catalog, agreements: Agreements) -> None:
    document = (await agreements.create(file_id=await agreements.stored()))["document_id"]
    first_unit, second_unit = await unit(enabled), await unit(enabled)
    first_id, second_id = uuid7(), uuid7()
    first_contract = await signed(agreements, document)
    second_contract = await signed(agreements, document)
    assert (await register(enabled, first_id, lease_body(first_unit, first_contract))).is_success
    assert (await register(enabled, second_id, lease_body(second_unit, second_contract))).is_success

    selected = await enabled.client.get(
        leases(enabled), headers=enabled.headers, params={"object_id": str(first_unit)}
    )
    assert selected.status_code == 200, selected.text
    page = selected.json()
    assert [item["lease_id"] for item in page["items"]] == [str(first_id)]
    assert page["next_cursor"] is None
    later = await enabled.client.get(
        leases(enabled),
        headers=enabled.headers,
        params={"object_id": str(first_unit), "after": str(first_id)},
    )
    assert later.json() == {"schema_version": 1, "items": [], "next_cursor": None}
    missing = await enabled.client.get(
        leases(enabled), headers=enabled.headers, params={"object_id": str(uuid7())}
    )
    assert missing.json()["items"] == []
    everything = await enabled.client.get(leases(enabled), headers=enabled.headers)
    assert {item["lease_id"] for item in everything.json()["items"]} == {
        str(first_id),
        str(second_id),
    }
    branch = enabled.member("manager", enabled.world.a.location_id)
    denied = await enabled.client.get(
        leases(enabled), headers=branch, params={"object_id": str(first_unit)}
    )
    assert denied.status_code == 403


async def test_term_boundaries_and_one_registration_per_agreement(
    enabled: Catalog, agreements: Agreements
) -> None:
    document = (await agreements.create(file_id=await agreements.stored()))["document_id"]
    object_id, another_unit = await unit(enabled), await unit(enabled)
    occupied = await signed(agreements, document, effective_until="2026-06-30")
    last_day = await signed(
        agreements, document, effective_from="2026-06-30", effective_until="2026-06-30"
    )
    adjacent = await signed(agreements, document, effective_from="2026-07-01")

    assert (await register(enabled, uuid7(), lease_body(object_id, occupied))).is_success
    overlap = await register(enabled, uuid7(), lease_body(object_id, last_day))
    assert (overlap.status_code, overlap.json()["error"]["code"]) == (409, "PROPERTY_LEASE_OVERLAP")
    same_agreement = await register(enabled, uuid7(), lease_body(another_unit, occupied))
    assert (same_agreement.status_code, same_agreement.json()["error"]["code"]) == (409, "CONFLICT")
    assert (await register(enabled, uuid7(), lease_body(another_unit, last_day))).is_success
    assert (await register(enabled, uuid7(), lease_body(object_id, adjacent))).is_success


async def test_source_must_be_a_signed_bounded_term_with_stored_file(
    enabled: Catalog, agreements: Agreements
) -> None:
    document = (await agreements.create(file_id=await agreements.stored()))["document_id"]
    empty = (await agreements.create())["document_id"]
    object_id, building_id = await unit(enabled), uuid7()
    assert (await enabled.put(building_id, enabled.body("building"))).is_success

    pending = await agreements.drafted(await agreements.counterparty())
    without_file = await signed(agreements, empty)
    unbounded = await signed(agreements, document, effective_until=None)
    stale = await signed(agreements, document)
    partner = (await agreements.get(f"/agreements/{stale}")).json()["counterparty_id"]
    assert (await agreements.put(stale, draft(partner, expected_revision=2))).is_success
    assert (
        await agreements.agree(stale, 3, document={"document_id": document, "revision": 1})
    ).is_success
    ended = await signed(agreements, document)
    assert (
        await agreements.act(
            ended, "terminate", {"expected_revision": 2, "terminated_on": TODAY.isoformat()}
        )
    ).is_success

    for bad in (
        lease_body(object_id, pending, 1),
        lease_body(object_id, without_file),
        lease_body(object_id, unbounded),
        lease_body(object_id, stale),
        lease_body(object_id, ended),
        lease_body(building_id, stale, 4),
    ):
        refused = await register(enabled, uuid7(), bad)
        assert (refused.status_code, refused.json()["error"]["code"]) == (422, "INVALID_REFERENCE")
    assert (await enabled.client.get(leases(enabled), headers=enabled.headers)).json()[
        "items"
    ] == []


async def test_unsigned_amendment_preserves_the_signed_term(
    enabled: Catalog, agreements: Agreements
) -> None:
    document = (await agreements.create(file_id=await agreements.stored()))["document_id"]
    object_id, lease_id = await unit(enabled), uuid7()
    subject = await signed(agreements, document)
    partner = (await agreements.get(f"/agreements/{subject}")).json()["counterparty_id"]
    assert (
        await agreements.put(
            subject, draft(partner, expected_revision=2, effective_until="2030-12-31")
        )
    ).is_success
    initial = await register(enabled, lease_id, lease_body(object_id, subject))
    assert initial.status_code == 200, initial.text
    assert initial.json()["ends_on"] == "2026-12-31"

    amendment = await agreements.agree(subject, 3)
    assert amendment.status_code == 200, amendment.text
    assert amendment.json()["effective_until"] == "2030-12-31"
    result = await enabled.client.get(f"{leases(enabled)}/{lease_id}", headers=enabled.headers)
    assert result.json() == initial.json()


async def test_competing_lease_waits_and_has_one_committed_result(
    enabled: Catalog, agreements: Agreements, manager_a: FakeUser, app_pool: RuntimePool
) -> None:
    document = (await agreements.create(file_id=await agreements.stored()))["document_id"]
    object_id, winner = await unit(enabled), uuid7()
    occupied = await signed(agreements, document)
    competing = await signed(agreements, document)
    async with asyncio.TaskGroup() as group, tenant_transaction(app_pool, enabled.tenant) as locked:
        await locked.execute(
            "insert into gba.property_leases (tenant_id, id, object_id, agreement_id, "
            "agreement_revision, recorded_by) values (%s,%s,%s,%s,2,%s)",
            (enabled.tenant, winner, object_id, occupied, manager_a.user_id),
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
    rejected = contender.result()
    assert (rejected.status_code, rejected.json()["error"]["code"]) == (
        409,
        "PROPERTY_LEASE_OVERLAP",
    )
    response = await enabled.client.get(leases(enabled), headers=enabled.headers)
    assert [record["lease_id"] for record in response.json()["items"]] == [str(winner)]


async def test_company_scope_and_immutable_terms(
    enabled: Catalog, agreements: Agreements, manager_b: FakeUser, app_pool: RuntimePool
) -> None:
    document = (await agreements.create(file_id=await agreements.stored()))["document_id"]
    object_id, lease_id = await unit(enabled), uuid7()
    subject = await signed(agreements, document)
    assert (await register(enabled, lease_id, lease_body(object_id, subject))).is_success

    branch = enabled.member("manager", enabled.world.a.location_id)
    foreign = enabled.idp.bearer(manager_b.subject, email=manager_b.email)
    assert (
        await enabled.client.get(f"{leases(enabled)}/{lease_id}", headers=branch)
    ).status_code == 403
    assert (await enabled.client.get(leases(enabled), headers=foreign)).status_code == 403
    assert (
        await register(enabled, uuid7(), lease_body(object_id, subject), headers=branch)
    ).status_code == 403

    async with tenant_transaction(app_pool, enabled.tenant) as conn:
        await conn.execute(
            "select set_config('gba.location_id', %s, true)", (str(enabled.world.a.location_id),)
        )
        assert await (await conn.execute("select id from gba.property_leases")).fetchall() == []
    async with tenant_transaction(app_pool, enabled.world.b.tenant_id) as conn:
        assert await (await conn.execute("select id from gba.property_leases")).fetchall() == []

    with (
        pytest.raises(psycopg.errors.CheckViolation),
        owner_tenant_transaction(enabled.owner_conn, enabled.tenant),
    ):
        enabled.owner_conn.execute(
            "update gba.property_leases set ends_on = starts_on where tenant_id = %s and id = %s",
            (enabled.tenant, lease_id),
        )


async def test_registration_requires_read_committed(
    enabled: Catalog,
    agreements: Agreements,
    manager_a: FakeUser,
    test_database: ProvisionedDatabase,
) -> None:
    document = (await agreements.create(file_id=await agreements.stored()))["document_id"]
    object_id = await unit(enabled)
    subject = await signed(agreements, document)
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
                "insert into gba.property_leases (tenant_id, id, object_id, agreement_id, "
                "agreement_revision, recorded_by) values (%s,%s,%s,%s,2,%s)",
                (enabled.tenant, uuid7(), object_id, subject, manager_a.user_id),
            )


async def test_interval_constraint_is_required(test_database: ProvisionedDatabase) -> None:
    async with (
        await psycopg.AsyncConnection.connect(test_database.owner_dsn) as owner,
        owner.transaction(force_rollback=True),
    ):
        await assert_location_scope_ready(owner)
        await owner.execute(
            "alter table gba.property_leases drop constraint property_leases_no_overlap"
        )
        with pytest.raises(DatabaseUnavailableError):
            await assert_location_scope_ready(owner)


async def test_unaccepted_property_module_refuses_registration(catalog: Catalog) -> None:
    denied = await register(catalog, uuid7(), lease_body(uuid7(), str(uuid7())))
    assert (denied.status_code, denied.json()["error"]["code"]) == (409, "MODULE_NOT_READY")
