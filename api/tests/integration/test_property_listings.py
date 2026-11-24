"""PROPERTY-01 step 2a: versioned listings of catalog objects (synthetic data)."""

import asyncio
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import owner_tenant_transaction
from tests.integration import test_property_catalog as catalog_tests
from tests.integration.configuration_support import Config
from tests.integration.seed import FakeUser, seed_other_branch
from tests.integration.test_property_catalog import Catalog

pytestmark = pytest.mark.anyio
client = catalog_tests.client
idp = catalog_tests.idp
manager_a = catalog_tests.manager_a
manager_b = catalog_tests.manager_b
catalog = catalog_tests.catalog
enabled = catalog_tests.enabled
__all__ = ["catalog", "client", "enabled", "idp", "manager_a", "manager_b"]


def listings(c: Catalog) -> str:
    return f"/v1/businesses/{c.tenant}/property/listings"


def listing(**fields: object) -> dict[str, object]:
    return {
        "schema_version": 1,
        "expected_revision": 0,
        "state": "draft",
        "headline": "FAKE two rooms",
        "description": "FAKE bright\nquiet street",
        "monthly_rent": 125_000,
        "currency": "EUR",
        "available_from": "2031-07-01",
        **fields,
    }


async def put_listing(
    c: Catalog,
    object_id: UUID,
    body: dict[str, object],
    *,
    headers: dict[str, str] | None = None,
    key: str | None = None,
) -> httpx.Response:
    return await c.client.put(
        f"{listings(c)}/{object_id}",
        json=body,
        headers={**(headers or c.headers), "Idempotency-Key": key or str(uuid7())},
    )


async def unit(c: Catalog, location: UUID | None = None) -> UUID:
    place = str(location or c.world.a.location_id)
    building = uuid7()
    saved = await c.put(building, c.body("building", location_id=place))
    assert saved.is_success, saved.text
    object_id = uuid7()
    saved = await c.put(object_id, c.body("unit", parent_id=str(building), location_id=place))
    assert saved.is_success, saved.text
    return object_id


async def test_unaccepted_module_refuses_listing_writes(catalog: Catalog) -> None:
    response = await put_listing(catalog, uuid7(), listing())
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "MODULE_NOT_READY"


async def test_listing_revisions_follow_the_object(enabled: Catalog, manager_a: FakeUser) -> None:
    object_id = await unit(enabled)
    first = await put_listing(enabled, object_id, listing(), key="first-listing")
    assert first.status_code == 200, first.text
    saved = first.json()
    assert saved["revision"] == 1
    assert (saved["location_id"], saved["kind"], saved["state"]) == (
        str(enabled.world.a.location_id),
        "unit",
        "draft",
    )
    assert saved["description"] == "FAKE bright\nquiet street"

    published = await put_listing(
        enabled, object_id, listing(expected_revision=1, state="published", description=None)
    )
    assert published.status_code == 200, published.text
    assert (published.json()["revision"], published.json()["description"]) == (2, None)

    replay = await put_listing(enabled, object_id, listing(), key="first-listing")
    assert replay.json() == saved
    stale = await put_listing(enabled, object_id, listing(expected_revision=1))
    assert stale.status_code == 409, stale.text
    assert stale.json()["error"]["code"] == "PROPERTY_REVISION_CONFLICT"

    current = await enabled.client.get(f"{listings(enabled)}/{object_id}", headers=enabled.headers)
    assert current.is_success, current.text
    assert (current.json()["revision"], current.json()["state"]) == (2, "published")
    assert "recorded_by" not in current.json()
    page = await enabled.client.get(listings(enabled), headers=enabled.headers)
    assert [i["object_id"] for i in page.json()["items"]] == [str(object_id)]
    assert page.json()["next_cursor"] is None
    history = await enabled.client.get(
        f"{listings(enabled)}/{object_id}/history", headers=enabled.headers
    )
    items = history.json()["items"]
    assert [(i["revision"], i["state"]) for i in items] == [(1, "draft"), (2, "published")]
    assert {i["recorded_by"] for i in items} == {str(manager_a.user_id)}


async def test_listing_input_is_strict(enabled: Catalog) -> None:
    object_id = await unit(enabled)
    for bad in (
        listing(currency="eur"),
        listing(monthly_rent=0),
        listing(monthly_rent=1_000_000_000_001),
        listing(headline=" "),
        listing(headline="x" * 121),
        listing(description="x" * 4001),
        listing(headline="FAKE\x07"),
        listing(state="sold"),
        {**listing(), "location_id": str(enabled.world.a.location_id)},
    ):
        response = await put_listing(enabled, object_id, bad)
        assert response.status_code == 422, (bad, response.text)
    missing = await put_listing(enabled, uuid7(), listing())
    assert missing.status_code == 404, missing.text
    absent = await enabled.client.get(f"{listings(enabled)}/{object_id}", headers=enabled.headers)
    assert absent.status_code == 404, absent.text


async def test_branch_reads_its_listings_only(
    enabled: Catalog, manager_b: FakeUser, app_pool: RuntimePool
) -> None:
    other, _ = seed_other_branch(enabled.owner_conn, enabled.world.a)
    visible, hidden = await unit(enabled), await unit(enabled, other)
    for object_id in (visible, hidden):
        result = await put_listing(enabled, object_id, listing())
        assert result.is_success, result.text
    branch = enabled.member("manager", enabled.world.a.location_id)
    page = await enabled.client.get(listings(enabled), headers=branch)
    assert page.is_success, page.text
    assert [i["object_id"] for i in page.json()["items"]] == [str(visible)]
    hidden_read = await enabled.client.get(f"{listings(enabled)}/{hidden}", headers=branch)
    assert hidden_read.status_code == 404, hidden_read.text
    history = await enabled.client.get(f"{listings(enabled)}/{visible}/history", headers=branch)
    assert history.status_code == 403, history.text
    write = await put_listing(enabled, visible, listing(expected_revision=1), headers=branch)
    assert write.status_code == 403, write.text
    foreign = await enabled.client.get(
        listings(enabled), headers=enabled.idp.bearer(manager_b.subject, email=manager_b.email)
    )
    assert foreign.status_code == 403, foreign.text

    async with tenant_transaction(app_pool, enabled.tenant) as conn:
        await conn.execute(
            "select set_config('gba.location_id', %s, true)", (str(enabled.world.a.location_id),)
        )
        rows = await (await conn.execute("select object_id from gba.property_listings")).fetchall()
        assert rows == [(visible,)]
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with conn.transaction():
                await conn.execute(
                    "insert into gba.property_listings (tenant_id, object_id, location_id, kind) "
                    "values (%s, %s, %s, 'unit')",
                    (enabled.tenant, uuid7(), enabled.world.a.location_id),
                )


async def test_competing_listing_revisions_commit_once(enabled: Catalog) -> None:
    object_id = await unit(enabled)
    outcomes = await asyncio.gather(
        put_listing(enabled, object_id, listing(headline="FAKE first")),
        put_listing(enabled, object_id, listing(headline="FAKE second")),
    )
    assert sorted(o.status_code for o in outcomes) == [200, 409]
    rejected = next(o for o in outcomes if o.status_code == 409)
    assert rejected.json()["error"]["code"] == "PROPERTY_REVISION_CONFLICT"


async def test_listing_replay_survives_disablement(enabled: Catalog, manager_a: FakeUser) -> None:
    object_id = await unit(enabled)
    body = listing()
    original = await put_listing(enabled, object_id, body, key="keep-listing")
    assert original.is_success, original.text
    await Config(enabled.client, enabled.idp).publish(
        manager_a, enabled.tenant, 1, ["booking_resources", "counterparties"]
    )
    replay = await put_listing(enabled, object_id, body, key="keep-listing")
    assert (replay.status_code, replay.json()) == (200, original.json())
    denied = await put_listing(enabled, object_id, listing(expected_revision=1))
    assert (denied.status_code, denied.json()["error"]["code"]) == (409, "MODULE_DISABLED")


async def test_listing_rows_keep_the_object_branch(enabled: Catalog) -> None:
    object_id = await unit(enabled)
    assert (await put_listing(enabled, object_id, listing())).is_success
    other, _ = seed_other_branch(enabled.owner_conn, enabled.world.a)
    with (
        pytest.raises(psycopg.errors.ForeignKeyViolation),
        owner_tenant_transaction(enabled.owner_conn, enabled.tenant),
    ):
        enabled.owner_conn.execute(
            "insert into gba.property_listing_revisions (tenant_id, object_id, revision, "
            "location_id, state, headline, monthly_rent, currency, available_from, recorded_by) "
            "select tenant_id, object_id, 2, %s, state, headline, monthly_rent, currency, "
            "available_from, recorded_by from gba.property_listing_revisions "
            "where object_id = %s",
            (other, object_id),
        )
