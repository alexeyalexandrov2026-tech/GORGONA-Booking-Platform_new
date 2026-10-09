"""Configuration publication in real PostgreSQL (ADR-0019, CORE-02).

Versions move draft -> validated -> published -> superseded; a disabled booking module
stops new bookings and reschedules everywhere while cancellations and reads continue.
"""

import asyncio
from datetime import datetime
from uuid import UUID, uuid7
from zoneinfo import ZoneInfo

import httpx
import psycopg
import pytest

from gorgona_booking.db.migrate import load_migrations
from gorgona_booking.db.pool import RuntimePool, tenant_transaction, unscoped_transaction
from gorgona_booking.db.provisioning import (
    add_membership,
    grant_platform_admin,
    owner_tenant_transaction,
)
from tests.integration import test_management_api as shared
from tests.integration.booking_support import BookingWorld
from tests.integration.configuration_support import Config
from tests.integration.customer_support import customer_day
from tests.integration.seed import FakeUser, seed_user
from tests.integration.test_delegations import Parties
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp

BOOKING = "booking_resources"
DETAILS = {
    "name": "FAKE Customer",
    "email": "fake@example.test",
    "phone": "+1 555 010 1234",
    "accept_policy": True,
}


def _member(
    owner_conn: psycopg.Connection,
    tenant_id: UUID,
    role: str,
    label: str,
    location_id: UUID | None = None,
) -> FakeUser:
    user = seed_user(owner_conn, f"configuration-{label}-{uuid7()}")
    add_membership(
        owner_conn, tenant_id=tenant_id, user_id=user.user_id, role=role, location_id=location_id
    )
    return user


@pytest.fixture
def config(client: httpx.AsyncClient, idp: FakeIdp) -> Config:
    return Config(client, idp)


@pytest.fixture
def owner_a(world: BookingWorld, owner_conn: psycopg.Connection) -> FakeUser:
    return _member(owner_conn, world.a.tenant_id, "owner", "owner-a")


def _start(hour: int) -> str:
    return (
        datetime.fromisoformat(f"{customer_day()}T{hour:02d}:00:00")
        .replace(tzinfo=ZoneInfo("America/New_York"))
        .isoformat()
    )


def _booking(world: BookingWorld, hour: int) -> dict[str, str]:
    return {
        "location_id": str(world.a.location_id),
        "resource_id": str(world.artist_a1),
        "variant_id": str(world.catalog_a.base_variant_id),
        "starts_at": _start(hour),
        "customer_name": "FAKE configuration guest",
        "customer_email": "configuration@example.com",
        "customer_phone": "+15551234571",
    }


def _selection(world: BookingWorld) -> dict[str, object]:
    return {
        "location_id": str(world.a.location_id),
        "variant_id": str(world.catalog_a.base_variant_id),
        "add_on_ids": [],
        "day": customer_day(),
        "resource_id": None,
    }


async def _customer_hold(
    client: httpx.AsyncClient, world: BookingWorld, slot: dict[str, str] | None = None
) -> httpx.Response:
    site = f"http://{world.a.host}/v1/customer"
    if slot is None:
        available = await client.post(f"{site}/availability", json=_selection(world))
        assert available.status_code == 200, available.text
        slot = available.json()["slots"][-1]
    body = _selection(world)
    body.pop("day")
    body.update({"resource_id": slot["resource_id"], "start_at": slot["start_at"]})
    return await client.post(
        f"{site}/holds",
        json=body,
        headers={"Booking-Token": "A" * 43, "Idempotency-Key": str(uuid7())},
    )


async def test_lifecycle_keeps_every_version_and_replays(
    config: Config, world: BookingWorld, owner_a: FakeUser, app_pool: RuntimePool
) -> None:
    a = world.a.tenant_id
    baseline = (await config.get(owner_a, a)).json()
    assert (baseline["baseline"], baseline["published"], baseline["latest"]) == (True, None, None)
    assert baseline["effective_module_ids"] == ["organization", "users_access", BOOKING]
    catalog = (
        await config.client.get(f"/v1/businesses/{a}/module-catalog", headers=config.auth(owner_a))
    ).json()
    assert [m["id"] for m in catalog["modules"] if m["enableable"]] == [
        "counterparties",
        BOOKING,
        "documents",
        "finance",
        "finance_documents",
    ]
    assert len(catalog["modules"]) == 19
    registry = (
        await config.client.get(
            f"/v1/businesses/{a}/readiness-registry", headers=config.auth(owner_a)
        )
    ).json()
    assert (len(registry["scenarios"]), len(registry["profiles"])) == (28, 39)

    # A draft pins an existing profile revision.
    missing = await config.draft(owner_a, a, 0, [BOOKING])
    assert missing.json()["error"]["code"] == "INVALID_REFERENCE"
    await config.profile(owner_a, a, 0, [1, 24])
    key = str(uuid7())
    drafted = await config.draft(owner_a, a, 0, [BOOKING], key=key)
    assert drafted.status_code == 200, drafted.text
    first = drafted.json()
    assert (first["version"], first["state"], first["revision"]) == (1, "draft", 1)
    assert (first["profile_revision"], first["module_ids"]) == (1, [BOOKING])
    assert (await config.draft(owner_a, a, 0, [BOOKING], key=key)).json() == first
    reused = await config.draft(owner_a, a, 0, [], key=key)
    assert reused.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"

    validated = (await config.step(owner_a, a, 1, "validate", 1)).json()
    assert (validated["state"], validated["revision"]) == ("validated", 2)
    assert validated["validation"] == {"registry_version": 2, "problems": [], "warnings": []}
    publish_key = str(uuid7())
    published = (await config.step(owner_a, a, 1, "publish", 2, key=publish_key)).json()
    assert (published["state"], published["revision"]) == ("published", 3)
    replay = await config.step(owner_a, a, 1, "publish", 2, key=publish_key)
    assert replay.json() == published
    current = (await config.get(owner_a, a)).json()
    assert (current["baseline"], current["published"]["version"]) == (False, 1)

    # A newer profile is a warning; turning booking off is previewed before publication.
    await config.profile(owner_a, a, 1, [1])
    second = (await config.draft(owner_a, a, 1, [])).json()
    assert second["version"] == 2
    preview = (await config.get(owner_a, a, "/versions/2/preview")).json()
    assert (preview["compared_to_version"], preview["enabling"]) == (1, [])
    assert preview["disabling"] == [BOOKING]
    assert "New bookings and reschedules" in preview["stopping"][0]["stops"]
    assert (preview["profile_revision"], preview["latest_profile_revision"]) == (1, 2)
    assert (preview["industries_added"], preview["industries_removed"]) == ([], [])
    assert [w["code"] for w in preview["warnings"]] == ["PROFILE_OUTDATED"]
    validated = (await config.step(owner_a, a, 2, "validate", 1)).json()
    assert [w["code"] for w in validated["validation"]["warnings"]] == ["PROFILE_OUTDATED"]
    assert (await config.step(owner_a, a, 2, "publish", 2)).status_code == 200
    old = (await config.get(owner_a, a, "/versions/1")).json()
    assert (old["state"], old["superseded_by_version"], old["revision"]) == ("superseded", 2, 4)
    assert old["superseded_at"] is not None

    page = (await config.get(owner_a, a, "/versions?limit=1")).json()
    assert ([item["version"] for item in page["items"]], page["next_cursor"]) == ([2], 2)
    rest = (await config.get(owner_a, a, "/versions?limit=1&before=2")).json()
    assert ([item["version"] for item in rest["items"]], rest["next_cursor"]) == ([1], None)
    assert (await config.get(owner_a, a, "/versions/9")).status_code == 404

    async with tenant_transaction(app_pool, a) as conn:
        actions = await (
            await conn.execute(
                "select action, count(*) from gba.audit_events "
                "where target_type = 'business_configuration' group by action order by action"
            )
        ).fetchall()
        published_audit = await (
            await conn.execute(
                "select details from gba.audit_events "
                "where action = 'business_configuration.published' order by occurred_at"
            )
        ).fetchall()
        states = await (
            await conn.execute(
                "select module_id, enabled, configuration_version from gba.business_module_states "
                "where module_id in (%s, 'finance') order by module_id",
                (BOOKING,),
            )
        ).fetchall()
    assert actions == [
        ("business_configuration.drafted", 2),
        ("business_configuration.published", 2),
        ("business_configuration.validated", 2),
    ]
    assert [
        (d[0]["previous_version"], d[0]["enabled"], d[0]["disabled"]) for d in published_audit
    ] == [
        (None, [], []),
        (1, [], [BOOKING]),
    ]
    assert states == [(BOOKING, False, 2), ("finance", False, 2)]


async def test_concurrent_commands_have_one_winner(
    config: Config, world: BookingWorld, owner_a: FakeUser, owner_conn: psycopg.Connection
) -> None:
    a = world.a.tenant_id
    manager = _member(owner_conn, a, "manager", "manager-a")
    await config.profile(owner_a, a, 0, [1])
    # CORE-02: two saves of the same version give one success and one conflict.
    results = await asyncio.gather(
        config.draft(owner_a, a, 0, [BOOKING]), config.draft(manager, a, 0, [])
    )
    assert sorted(r.status_code for r in results) == [200, 409]
    conflict = next(r for r in results if r.status_code == 409).json()["error"]
    assert (conflict["code"], conflict["details"]) == ("CONFLICT", {"version": 1})
    key = str(uuid7())
    same_key = await asyncio.gather(*(config.draft(owner_a, a, 1, [], key=key) for _ in range(2)))
    assert [r.status_code for r in same_key] == [200, 200]
    assert same_key[0].json() == same_key[1].json()
    assert same_key[0].json()["version"] == 2

    # Only the latest version moves forward, in order, at its current revision.
    stale = await config.step(owner_a, a, 1, "validate", 1)
    assert (stale.status_code, stale.json()["error"]["details"]) == (409, {"version": 2})
    early = await config.step(owner_a, a, 2, "publish", 1)
    assert early.json()["error"]["code"] == "CONFIGURATION_STATE_INVALID"
    assert (await config.step(owner_a, a, 2, "validate", 2)).status_code == 409
    assert (await config.step(owner_a, a, 2, "validate", 1)).status_code == 200
    again = await config.step(owner_a, a, 2, "validate", 2)
    assert again.json()["error"]["code"] == "CONFIGURATION_STATE_INVALID"
    publications = await asyncio.gather(
        config.step(owner_a, a, 2, "publish", 2), config.step(manager, a, 2, "publish", 2)
    )
    assert sorted(r.status_code for r in publications) == [200, 409]
    current = (await config.get(owner_a, a)).json()
    assert (current["published"]["version"], current["published"]["revision"]) == (2, 3)


async def test_invalid_configurations_are_explained(
    config: Config, world: BookingWorld, owner_a: FakeUser, owner_conn: psycopg.Connection
) -> None:
    a = world.a.tenant_id
    await config.profile(owner_a, a, 0, [1])
    unknown = await config.draft(owner_a, a, 0, ["organization"])
    assert unknown.json()["error"]["code"] == "INVALID_REQUEST"
    for version, modules, codes in (
        (1, ["workforce"], {("MODULE_NOT_READY", "workforce")}),
        (
            2,
            ["sales"],
            {("MODULE_NOT_READY", "sales"), ("DEPENDENCY_MISSING", "sales")},
        ),
    ):
        assert (await config.draft(owner_a, a, version - 1, modules)).status_code == 200
        refused = await config.step(owner_a, a, version, "validate", 1)
        error = refused.json()["error"]
        assert (refused.status_code, error["code"]) == (422, "CONFIGURATION_INVALID")
        assert {(p["code"], p["module_id"]) for p in error["details"]["problems"]} == codes
        # A refused validation changes nothing.
        assert (await config.get(owner_a, a, f"/versions/{version}")).json()["state"] == "draft"
    # A draft saved under another registry version must be saved again.
    with owner_tenant_transaction(owner_conn, a):
        owner_conn.execute(
            "insert into gba.business_configuration_versions "
            "(tenant_id, version, profile_revision, registry_version, created_by) "
            "values (%s, 3, 1, 1, %s)",
            (a, owner_a.user_id),
        )
    changed = await config.step(owner_a, a, 3, "validate", 1)
    assert [p["code"] for p in changed.json()["error"]["details"]["problems"]] == [
        "REGISTRY_CHANGED"
    ]
    preview = (await config.get(owner_a, a, "/versions/3/preview")).json()
    assert (preview["compared_to_version"], preview["disabling"]) == (None, [BOOKING])
    assert preview["industries_added"] == [1]


async def test_disabled_booking_stops_new_bookings_everywhere(
    client: httpx.AsyncClient,
    config: Config,
    world: BookingWorld,
    owner_a: FakeUser,
    owner_conn: psycopg.Connection,
) -> None:
    a, b = world.a.tenant_id, world.b.tenant_id
    salon = f"/v1/salons/{a}"
    owner_b = _member(owner_conn, b, "owner", "owner-b")
    dispatcher = _member(owner_conn, b, "front_desk", "dispatcher")
    branch = _member(owner_conn, a, "manager", "branch-a", world.a.location_id)
    parties = Parties(client, config.idp, world)
    await parties.active_grant(owner_a, owner_b, [dispatcher])
    headers = config.auth(owner_a)
    kept = await client.post(f"{salon}/bookings", json=_booking(world, 11), headers=headers)
    assert kept.status_code == 201, kept.text
    open_hold = await _customer_hold(client, world)
    assert open_hold.status_code == 201, open_hold.text
    workspace = (await client.get(f"{salon}/workspace", headers=headers)).json()
    assert workspace["booking_enabled"] is True

    await config.profile(owner_a, a, 0, [1])
    await config.publish(owner_a, a, 0, [])
    refusals = [
        await client.post(f"{salon}/bookings", json=_booking(world, 13), headers=headers),
        await client.post(
            f"{salon}/bookings/{kept.json()['booking_id']}/reschedule",
            json={"new_starts_at": _start(14)},
            headers=headers,
        ),
        await client.post(
            f"{salon}/bookings", json=_booking(world, 13), headers=config.auth(branch)
        ),
        await client.post(
            f"{salon}/bookings",
            json=_booking(world, 13),
            headers={**config.auth(dispatcher), "Idempotency-Key": str(uuid7())},
        ),
        await client.post(
            f"http://{world.a.host}/v1/customer/availability", json=_selection(world)
        ),
        await _customer_hold(
            client, world, {"resource_id": str(world.artist_a1), "start_at": _start(15)}
        ),
    ]
    for response in refusals:
        assert (response.status_code, response.json()["error"]["code"]) == (
            409,
            "MODULE_DISABLED",
        ), response.text
    # Open obligations, history and other businesses continue.
    hold_id = open_hold.json()["booking_id"]
    confirmed = await client.post(
        f"http://{world.a.host}/v1/customer/bookings/{hold_id}/confirm",
        json=DETAILS,
        headers={"Booking-Token": "A" * 43, "Idempotency-Key": str(uuid7())},
    )
    assert confirmed.status_code == 200, confirmed.text
    cancelled = await client.post(
        f"{salon}/bookings/{kept.json()['booking_id']}/cancel", json={}, headers=headers
    )
    assert cancelled.status_code == 200, cancelled.text
    listed = await client.get(f"{salon}/bookings", headers=headers)
    assert listed.status_code == 200
    assert {kept.json()["booking_id"], hold_id} <= {item["booking_id"] for item in listed.json()}
    for user in (owner_a, branch, dispatcher):
        view = await client.get(f"{salon}/workspace", headers=config.auth(user))
        assert view.json()["booking_enabled"] is False, view.text
    other = {**_booking(world, 13), "location_id": str(world.b.location_id)}
    other.update(resource_id=str(world.artist_b1), variant_id=str(world.catalog_b.base_variant_id))
    assert (
        await client.post(f"/v1/salons/{b}/bookings", json=other, headers=config.auth(owner_b))
    ).status_code == 201

    # Turning booking on again needs a new published version.
    await config.publish(owner_a, a, 1, [BOOKING])
    again = await client.post(f"{salon}/bookings", json=_booking(world, 13), headers=headers)
    assert again.status_code == 201, again.text
    assert (await client.get(f"{salon}/workspace", headers=headers)).json()["booking_enabled"]


async def test_publication_and_new_bookings_are_ordered(
    client: httpx.AsyncClient,
    config: Config,
    world: BookingWorld,
    owner_a: FakeUser,
    owner_conn: psycopg.Connection,
) -> None:
    a = world.a.tenant_id
    lock = "select pg_catalog.{}(pg_catalog.hashtextextended(%s, 0))"
    name = f"gba:business-configuration:{a}"
    # Holding the publication lock makes a new booking wait for it.
    owner_conn.execute(lock.format("pg_advisory_lock"), (name,))
    try:
        pending = asyncio.create_task(
            client.post(
                f"/v1/salons/{a}/bookings", json=_booking(world, 11), headers=config.auth(owner_a)
            )
        )
        await asyncio.sleep(1)
        assert not pending.done()
    finally:
        owner_conn.execute(lock.format("pg_advisory_unlock"), (name,))
    assert (await pending).status_code == 201
    # A publication racing new bookings: none is created after the disabling commit.
    await config.profile(owner_a, a, 0, [1])
    drafted = (await config.draft(owner_a, a, 0, [])).json()
    assert (await config.step(owner_a, a, drafted["version"], "validate", 1)).status_code == 200
    results = await asyncio.gather(
        config.step(owner_a, a, drafted["version"], "publish", 2),
        *(
            client.post(
                f"/v1/salons/{a}/bookings", json=_booking(world, hour), headers=config.auth(owner_a)
            )
            for hour in (12, 13, 14)
        ),
    )
    assert results[0].status_code == 200
    created = [r.json()["booking_id"] for r in results[1:] if r.status_code == 201]
    refused = [r.json()["error"]["code"] for r in results[1:] if r.status_code != 201]
    assert set(refused) <= {"MODULE_DISABLED"}
    with owner_tenant_transaction(owner_conn, a):
        stored = owner_conn.execute(
            "select count(*) from gba.bookings where id = any(%s)", (created,)
        ).fetchone()
    assert stored == (len(created),)
    after = await client.post(
        f"/v1/salons/{a}/bookings", json=_booking(world, 15), headers=config.auth(owner_a)
    )
    assert after.json()["error"]["code"] == "MODULE_DISABLED"


async def test_database_rules_hold_for_direct_sql(
    config: Config,
    world: BookingWorld,
    owner_a: FakeUser,
    owner_conn: psycopg.Connection,
    app_pool: RuntimePool,
) -> None:
    a = world.a.tenant_id
    await config.profile(owner_a, a, 0, [1])
    await config.publish(owner_a, a, 0, [BOOKING])
    assert (await config.draft(owner_a, a, 1, [])).status_code == 200
    versions = "update gba.business_configuration_versions set "
    for statement, error in (
        (
            versions + "registry_version = 3, revision = revision + 1 where version = 1",
            psycopg.errors.CheckViolation,
        ),
        (
            versions + "state = 'published', revision = revision + 1, validated_by = created_by, "
            "validated_at = now(), validation = '{}', published_by = created_by, "
            "published_at = now() where version = 2",
            psycopg.errors.CheckViolation,
        ),
        (
            versions + "state = 'superseded', revision = revision + 1, superseded_by_version = 2, "
            "superseded_at = now() where version = 1",
            psycopg.errors.CheckViolation,
        ),
        (
            "delete from gba.business_configuration_versions where version = 1",
            psycopg.errors.CheckViolation,
        ),
        (
            "insert into gba.business_configuration_versions "
            "(tenant_id, version, profile_revision, registry_version, created_by) "
            "select tenant_id, 9, 1, 1, created_by from gba.business_configuration_versions "
            "where version = 1",
            psycopg.errors.CheckViolation,
        ),
        (
            "insert into gba.business_configuration_modules (tenant_id, version, module_id) "
            "select tenant_id, 1, 'finance' from gba.business_configuration_versions "
            "where version = 1",
            psycopg.errors.CheckViolation,
        ),
        (
            "update gba.business_module_states set enabled = not enabled, revision = revision + 1 "
            f"where module_id = '{BOOKING}'",
            psycopg.errors.CheckViolation,
        ),
        ("delete from gba.business_module_states", psycopg.errors.CheckViolation),
    ):
        with (
            owner_tenant_transaction(owner_conn, a),
            pytest.raises(error),
            owner_conn.transaction(),
        ):
            owner_conn.execute(statement)
    # Two published versions cannot exist even when the transition itself is allowed.
    assert (await config.step(owner_a, a, 2, "validate", 1)).status_code == 200
    with (
        owner_tenant_transaction(owner_conn, a),
        pytest.raises(psycopg.errors.UniqueViolation),
        owner_conn.transaction(),
    ):
        owner_conn.execute(
            versions + "state = 'published', revision = revision + 1, published_by = created_by, "
            "published_at = now() where version = 2"
        )

    async with tenant_transaction(app_pool, a) as conn:
        for statement, params in (
            (
                "insert into gba.business_configuration_versions "
                "(tenant_id, version, state, profile_revision, registry_version, created_by) "
                "values (%s, 3, 'published', 1, 1, %s)",
                (a, owner_a.user_id),
            ),
            ("delete from gba.business_configuration_modules where tenant_id = %s", (a,)),
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                async with conn.transaction():
                    await conn.execute(statement, params)
        await conn.execute(
            "select pg_catalog.set_config('gba.location_id', %s, true)", (str(world.a.location_id),)
        )
        # Branch sessions see the effective module state, never the version history.
        assert (
            await (
                await conn.execute("select * from gba.business_configuration_versions")
            ).fetchall()
        ) == []
        states = await (
            await conn.execute("select module_id from gba.business_module_states")
        ).fetchall()
        assert (BOOKING,) in states
        updated = await conn.execute(
            "update gba.business_module_states set revision = revision + 1"
        )
        assert updated.rowcount == 0
        # The trigger cannot see the version history here either; both refuse the row.
        refused = (psycopg.errors.InsufficientPrivilege, psycopg.errors.CheckViolation)
        with pytest.raises(refused):
            async with conn.transaction():
                await conn.execute(
                    "insert into gba.business_module_states "
                    "(tenant_id, module_id, enabled, configuration_version, updated_by) "
                    "values (%s, 'branch_forged', false, 1, %s)",
                    (a, owner_a.user_id),
                )
    async with unscoped_transaction(app_pool) as conn:
        for table in ("business_configuration_versions", "business_module_states"):
            assert (await (await conn.execute(f"select * from gba.{table}")).fetchall()) == []


def _restore_booking_trigger_function(owner_conn: psycopg.Connection) -> None:
    sql = next(m.sql for m in load_migrations() if m.version == 14)
    start = sql.index("create function gba.enforce_booking_module()")
    end = sql.index("revoke all on function gba.enforce_booking_module()")
    definition = sql[start:end].replace("create function", "create or replace function", 1)
    owner_conn.execute(definition.encode("utf-8"))


@pytest.mark.parametrize(
    ("damage", "restore"),
    [
        (
            "alter policy business_configuration_versions_unrestricted_scope "
            "on gba.business_configuration_versions using (true) with check (true)",
            "alter policy business_configuration_versions_unrestricted_scope "
            "on gba.business_configuration_versions using (gba.current_location_id() is null) "
            "with check (gba.current_location_id() is null)",
        ),
        (
            "alter policy business_configuration_modules_unrestricted_scope "
            "on gba.business_configuration_modules using (true) with check (true)",
            "alter policy business_configuration_modules_unrestricted_scope "
            "on gba.business_configuration_modules using (gba.current_location_id() is null) "
            "with check (gba.current_location_id() is null)",
        ),
        (
            "alter policy business_module_states_unrestricted_insert "
            "on gba.business_module_states with check (true)",
            "alter policy business_module_states_unrestricted_insert "
            "on gba.business_module_states with check (gba.current_location_id() is null)",
        ),
        (
            "alter policy business_module_states_unrestricted_update "
            "on gba.business_module_states using (true) with check (true)",
            "alter policy business_module_states_unrestricted_update "
            "on gba.business_module_states using (gba.current_location_id() is null) "
            "with check (gba.current_location_id() is null)",
        ),
        (
            "alter table gba.bookings disable trigger bookings_require_booking_module",
            "alter table gba.bookings enable trigger bookings_require_booking_module",
        ),
        (
            "create or replace function gba.enforce_booking_module() returns trigger "
            "language plpgsql as $$ begin return new; end; $$",
            None,
        ),
    ],
)
async def test_damaged_configuration_controls_fail_readiness(
    client: httpx.AsyncClient, owner_conn: psycopg.Connection, damage: str, restore: str | None
) -> None:
    # Fixed test parameters; privileged schema damage is confined to the disposable database.
    assert (await client.get("/health/ready")).status_code == 200
    try:
        owner_conn.execute(damage.encode("utf-8"))
        assert (await client.get("/health/ready")).status_code == 503
    finally:
        if restore is None:
            _restore_booking_trigger_function(owner_conn)
        else:
            owner_conn.execute(restore.encode("utf-8"))
    assert (await client.get("/health/ready")).status_code == 200


async def test_configuration_is_company_wide_and_not_delegated(
    client: httpx.AsyncClient,
    config: Config,
    world: BookingWorld,
    owner_a: FakeUser,
    owner_conn: psycopg.Connection,
    app_pool: RuntimePool,
) -> None:
    a, b = world.a.tenant_id, world.b.tenant_id
    owner_b = _member(owner_conn, b, "owner", "owner-b")
    artist = _member(owner_conn, a, "artist", "artist-a")
    branch = _member(owner_conn, a, "manager", "branch-a", world.a.location_id)
    dispatcher = _member(owner_conn, b, "front_desk", "dispatcher")
    await Parties(client, config.idp, world).active_grant(owner_a, owner_b, [dispatcher])
    await config.profile(owner_a, a, 0, [1])
    for user, read, write in (
        (owner_b, 403, 403),
        (artist, 200, 403),
        (branch, 403, 403),
        (dispatcher, 403, 403),
    ):
        assert (await config.get(user, a)).status_code == read, user.subject
        assert (await config.draft(user, a, 0, [BOOKING])).status_code == write, user.subject
    support = seed_user(owner_conn, f"configuration-support-{uuid7()}")
    grant_platform_admin(owner_conn, user_id=support.user_id, granted_by="test")
    assert (await config.get(support, a)).status_code == 200
    assert (await config.draft(support, a, 0, [BOOKING])).status_code == 403
    async with tenant_transaction(app_pool, a) as conn:
        audited = await (
            await conn.execute(
                "select count(*) from gba.audit_events where action = 'platform.tenant_access' "
                "and actor = %s",
                (f"user:{support.user_id}",),
            )
        ).fetchone()
    assert audited is not None
    assert audited[0] >= 1


async def test_registry_v2_preserves_published_v1_finance_and_admits_h_only_when_accepted(
    config: Config, world: BookingWorld, owner_a: FakeUser
) -> None:
    from gorgona_booking.business import configurations as config_service
    from gorgona_booking.business import modules
    from gorgona_booking.business.readiness_registry import Readiness

    a = world.a.tenant_id
    await config.profile(owner_a, a, 0, [1])
    # Simulate the previous server registry at publication time. All SQL, auth,
    # configuration transitions and module states are real disposable fixtures.
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(config_service, "MODULE_REGISTRY_VERSION", 1)
        await config.publish(owner_a, a, 0, [BOOKING, "finance", "counterparties"])
    current = (await config.get(owner_a, a)).json()
    assert current["registry_version"] == 2
    assert current["published"]["registry_version"] == 1
    assert "finance" in current["effective_module_ids"]
    assert "finance_documents" not in current["effective_module_ids"]

    drafted = await config.draft(owner_a, a, 1, ["finance", "counterparties", "finance_documents"])
    assert drafted.status_code == 200, drafted.text
    accepted = modules.MODULES_BY_ID["finance_documents"]
    assert (accepted.readiness, accepted.enableable) == (Readiness.TECHNICALLY_VERIFIED, True)
    # Without technical acceptance the same selection is refused and nothing changes.
    with pytest.MonkeyPatch.context() as patch:
        patch.setitem(
            modules.MODULES_BY_ID,
            "finance_documents",
            accepted.model_copy(update={"enableable": False, "readiness": Readiness.PLANNED}),
        )
        refused = await config.step(owner_a, a, 2, "validate", 1)
        assert (refused.status_code, refused.json()["error"]["code"]) == (
            422,
            "CONFIGURATION_INVALID",
        )
        assert {
            (p["code"], p["module_id"]) for p in refused.json()["error"]["details"]["problems"]
        } == {("MODULE_NOT_READY", "finance_documents")}
        after = (await config.get(owner_a, a)).json()
        assert after["published"] == current["published"]
        assert after["effective_module_ids"] == current["effective_module_ids"]
    # The accepted workflow is enabled only by this explicit publication.
    validated = await config.step(owner_a, a, 2, "validate", 1)
    assert validated.status_code == 200, validated.text
    published = await config.step(owner_a, a, 2, "publish", 2)
    assert published.status_code == 200, published.text
    final = (await config.get(owner_a, a)).json()
    assert final["published"]["registry_version"] == 2
    assert "finance_documents" in final["effective_module_ids"]
