"""PROPERTY-01 condition evidence of a property move-in."""

import asyncio
from datetime import date, datetime, timedelta
from uuid import UUID, uuid7
from zoneinfo import ZoneInfo

import httpx
import psycopg
import pytest

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import owner_tenant_transaction
from tests.integration import test_property_leases as lease_tests
from tests.integration.configuration_support import Config
from tests.integration.seed import FakeUser
from tests.integration.test_agreements import Agreements
from tests.integration.test_documents import doc
from tests.integration.test_property_catalog import Catalog
from tests.integration.test_property_lease_terms import amend, change, terminate, terms
from tests.integration.test_property_leases import lease_body, leases, register
from tests.integration.test_property_listings import unit
from tests.unit.test_file_validation import jpeg, png

pytestmark = pytest.mark.anyio
agreements = lease_tests.agreements
catalog = lease_tests.catalog
client = lease_tests.client
enabled = lease_tests.enabled
idp = lease_tests.idp
manager_a = lease_tests.manager_a
manager_b = lease_tests.manager_b
__all__ = ["agreements", "catalog", "client", "enabled", "idp", "manager_a", "manager_b"]


def move_in(c: Catalog, lease_id: UUID) -> str:
    return f"{leases(c)}/{lease_id}/move-in"


def reference(id_: object, revision: int = 1) -> dict[str, object]:
    return {"document_id": id_, "revision": revision}


async def record_move_in(
    c: Catalog,
    lease_id: UUID,
    body: dict[str, object],
    *,
    key: str | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    return await c.client.put(
        move_in(c, lease_id),
        json=body,
        headers={**(headers or c.headers), "Idempotency-Key": key or str(uuid7())},
    )


async def lease_with_evidence(c: Catalog, a: Agreements) -> tuple[UUID, str, dict[str, object]]:
    day = datetime.now(ZoneInfo("America/New_York")).date()
    signed_copy = (await a.create(file_id=await a.stored()))["document_id"]
    contract = await a.drafted(
        await a.counterparty(),
        effective_from=(day - timedelta(days=30)).isoformat(),
        effective_until=(day + timedelta(days=30)).isoformat(),
    )
    attested = await a.agree(
        contract,
        1,
        signed_on=(day - timedelta(days=45)).isoformat(),
        document=reference(signed_copy),
    )
    assert attested.is_success, attested.text
    lease_id = uuid7()
    recorded = await register(c, lease_id, lease_body(await unit(c), contract))
    assert recorded.is_success, recorded.text

    report = (await a.create(category="report", file_id=await a.stored()))["document_id"]
    photo_file = await a.stored(png(), media="image/png", name="FAKE condition.png")
    photo = (await a.create(category="report", title="FAKE condition photo", file_id=photo_file))[
        "document_id"
    ]
    body = {
        "schema_version": 1,
        "term_revision": 1,
        "moved_in_on": day.isoformat(),
        "report": reference(report),
        "photos": [reference(photo)],
    }
    return lease_id, contract, body


async def test_record_move_in_with_immutable_report_and_photo(
    enabled: Catalog, agreements: Agreements
) -> None:
    lease_id, _, body = await lease_with_evidence(enabled, agreements)
    result = await record_move_in(enabled, lease_id, body, key="record-move-in")
    assert result.status_code == 200, result.text
    response = result.json()
    assert response["lease_id"] == str(lease_id)
    assert response["term_revision"] == body["term_revision"]
    assert response["moved_in_on"] == body["moved_in_on"]
    assert (response["report"], response["photos"]) == (body["report"], body["photos"])
    replay = await record_move_in(enabled, lease_id, body, key="record-move-in")
    assert replay.json() == response
    saved = await enabled.client.get(move_in(enabled, lease_id), headers=enabled.headers)
    assert saved.json() == response


async def test_failed_photo_rolls_back_move_in_and_allows_corrected_retry(
    enabled: Catalog, agreements: Agreements
) -> None:
    lease_id, _, body = await lease_with_evidence(enabled, agreements)
    photos = body["photos"]
    assert isinstance(photos, list)
    bad = {**body, "photos": [*photos, body["report"]]}
    result = await record_move_in(enabled, lease_id, bad, key="try-move-in")
    assert (result.status_code, result.json()["error"]["code"]) == (422, "INVALID_REFERENCE")
    assert (
        await enabled.client.get(move_in(enabled, lease_id), headers=enabled.headers)
    ).status_code == 404

    jpeg_content = jpeg()
    image = await agreements.stored(jpeg_content, media="image/jpeg", name="FAKE second.jpg")
    second = (await agreements.create(file_id=image))["document_id"]
    assert isinstance(second, str)
    corrected = {**body, "photos": [*photos, reference(second)]}
    saved = await record_move_in(enabled, lease_id, corrected, key="try-move-in")
    assert saved.is_success, saved.text
    assert saved.json()["photos"] == corrected["photos"]

    revised_file = await agreements.stored(png(), media="image/png", name="FAKE revised.png")
    revision = await agreements.save(second, doc(expected_revision=1, file_id=revised_file))
    assert revision.is_success, revision.text
    frozen = await enabled.client.get(move_in(enabled, lease_id), headers=enabled.headers)
    assert frozen.json() == saved.json()
    original = await agreements.get(f"/documents/{second}/versions/1/file")
    assert original.content == jpeg_content
    assert original.headers["content-type"] == "image/jpeg"


async def test_move_in_respects_term_revision_and_local_calendar(
    enabled: Catalog, agreements: Agreements
) -> None:
    lease_id, contract, body = await lease_with_evidence(enabled, agreements)
    day = date.fromisoformat(str(body["moved_in_on"]))
    for invalid in (day + timedelta(days=1), day - timedelta(days=31)):
        result = await record_move_in(
            enabled, lease_id, {**body, "moved_in_on": invalid.isoformat()}
        )
        assert (result.status_code, result.json()["error"]["code"]) == (422, "INVALID_REFERENCE")
    signed_copy = (await agreements.get(f"/agreements/{contract}")).json()["document"][
        "document_id"
    ]
    revision = await amend(
        agreements,
        contract,
        signed_copy,
        effective_from=(day - timedelta(days=30)).isoformat(),
        effective_until=(day + timedelta(days=60)).isoformat(),
    )
    assert (await change(enabled, lease_id, "extend", revision)).is_success
    stale = await record_move_in(enabled, lease_id, body)
    assert (stale.status_code, stale.json()["error"]["code"]) == (
        409,
        "PROPERTY_LEASE_REVISION_CONFLICT",
    )
    saved = await record_move_in(enabled, lease_id, {**body, "term_revision": 2})
    assert saved.is_success, saved.text
    assert saved.json()["term_revision"] == 2


async def test_release_cannot_erase_a_recorded_day_of_possession(
    enabled: Catalog, agreements: Agreements
) -> None:
    lease_id, contract, body = await lease_with_evidence(enabled, agreements)
    day = date.fromisoformat(str(body["moved_in_on"]))
    result = await record_move_in(enabled, lease_id, body)
    assert result.is_success, result.text
    closure = await terminate(agreements, contract, 2, (day - timedelta(days=1)).isoformat())
    refused = await change(enabled, lease_id, "release", closure)
    assert (refused.status_code, refused.json()["error"]["code"]) == (
        409,
        "PROPERTY_LEASE_MOVE_IN_CONFLICT",
    )
    history = await enabled.client.get(terms(enabled, lease_id), headers=enabled.headers)
    assert [record["revision"] for record in history.json()["items"]] == [1]

    other, other_contract, other_body = await lease_with_evidence(enabled, agreements)
    assert (await record_move_in(enabled, other, other_body)).is_success
    closed_on = str(other_body["moved_in_on"])
    same_day = await terminate(agreements, other_contract, 2, closed_on)
    released = await change(enabled, other, "release", same_day)
    assert (released.status_code, released.json()["ends_on"]) == (200, closed_on)
    report = await enabled.client.get(move_in(enabled, other), headers=enabled.headers)
    assert report.json()["term_revision"] == 1


async def test_move_in_is_private_and_survives_module_disablement(
    enabled: Catalog,
    agreements: Agreements,
    manager_a: FakeUser,
    manager_b: FakeUser,
    app_pool: RuntimePool,
) -> None:
    lease_id, _, body = await lease_with_evidence(enabled, agreements)
    next_lease, _, next_body = await lease_with_evidence(enabled, agreements)
    result = await record_move_in(enabled, lease_id, body, key="keep-move-in")
    assert result.is_success, result.text

    branch = enabled.member("manager", enabled.world.a.location_id)
    foreign = enabled.idp.bearer(manager_b.subject, email=manager_b.email)
    assert (await enabled.client.get(move_in(enabled, lease_id), headers=branch)).status_code == 403
    assert (
        await enabled.client.get(move_in(enabled, lease_id), headers=foreign)
    ).status_code == 403
    assert (await record_move_in(enabled, next_lease, next_body, headers=branch)).status_code == 403
    async with tenant_transaction(app_pool, enabled.tenant) as conn:
        await conn.execute(
            "select set_config('gba.location_id', %s, true)", (str(enabled.world.a.location_id),)
        )
        reports = await conn.execute("select lease_id from gba.property_move_ins")
        photos = await conn.execute("select lease_id from gba.property_move_in_photos")
        assert await reports.fetchall() == await photos.fetchall() == []
    with (
        pytest.raises(psycopg.errors.CheckViolation),
        owner_tenant_transaction(enabled.owner_conn, enabled.tenant),
    ):
        enabled.owner_conn.execute(
            "delete from gba.property_move_in_photos where lease_id = %s", (lease_id,)
        )

    await Config(enabled.client, enabled.idp).publish(
        manager_a, enabled.tenant, 2, ["booking_resources", "counterparties", "documents"]
    )
    replay = await record_move_in(enabled, lease_id, body, key="keep-move-in")
    assert (replay.status_code, replay.json()) == (200, result.json())
    refused = await record_move_in(enabled, next_lease, next_body)
    assert (refused.status_code, refused.json()["error"]["code"]) == (409, "MODULE_DISABLED")


async def test_database_requires_all_move_in_photos(
    enabled: Catalog, agreements: Agreements, manager_a: FakeUser, app_pool: RuntimePool
) -> None:
    lease_id, _, body = await lease_with_evidence(enabled, agreements)
    report = body["report"]
    assert isinstance(report, dict)
    with pytest.raises(psycopg.errors.CheckViolation, match="keeps all of its photos"):
        async with tenant_transaction(app_pool, enabled.tenant) as conn:
            await conn.execute(
                "insert into gba.property_move_ins (tenant_id, lease_id, term_revision, "
                "moved_in_on, report_id, report_revision, photo_count, recorded_by) "
                "values (%s,%s,1,%s,%s,1,1,%s)",
                (
                    enabled.tenant,
                    lease_id,
                    body["moved_in_on"],
                    report["document_id"],
                    manager_a.user_id,
                ),
            )
    absent = await enabled.client.get(move_in(enabled, lease_id), headers=enabled.headers)
    assert absent.status_code == 404


async def test_move_in_waits_for_a_competing_early_release(
    enabled: Catalog, agreements: Agreements, manager_a: FakeUser, app_pool: RuntimePool
) -> None:
    lease_id, contract, body = await lease_with_evidence(enabled, agreements)
    day = date.fromisoformat(str(body["moved_in_on"]))
    closure = await terminate(agreements, contract, 2, (day - timedelta(days=1)).isoformat())
    async with asyncio.TaskGroup() as group, tenant_transaction(app_pool, enabled.tenant) as locked:
        await locked.execute(
            "insert into gba.property_lease_term_events "
            "(tenant_id, lease_id, revision, action, agreement_revision, recorded_by) "
            "values (%s,%s,2,'release',%s,%s)",
            (enabled.tenant, lease_id, closure, manager_a.user_id),
        )
        pid = await (await locked.execute("select pg_backend_pid()")).fetchone()
        assert pid is not None
        contender = group.create_task(record_move_in(enabled, lease_id, body))
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
    stale = contender.result()
    assert (stale.status_code, stale.json()["error"]["code"]) == (
        409,
        "PROPERTY_LEASE_REVISION_CONFLICT",
    )
    outside = await record_move_in(enabled, lease_id, {**body, "term_revision": 2})
    assert (outside.status_code, outside.json()["error"]["code"]) == (422, "INVALID_REFERENCE")
