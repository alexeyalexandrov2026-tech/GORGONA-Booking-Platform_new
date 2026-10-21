"""J1 materials and storage places against real PostgreSQL 18."""

from dataclasses import dataclass
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.auth.principal import set_user_context
from gorgona_booking.business import modules
from gorgona_booking.business.readiness_registry import Readiness
from gorgona_booking.db.inventory_guard import INVENTORY_TABLES, assert_inventory_ready
from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import (
    add_membership,
    grant_platform_admin,
    owner_tenant_transaction,
)
from tests.integration import test_management_api as shared
from tests.integration.booking_support import BookingWorld
from tests.integration.configuration_support import Config
from tests.integration.seed import FakeUser, seed_other_branch, seed_user
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
ENABLED = ["booking_resources", "finance", "inventory"]
J1_TABLES = ("stock_items", "stock_item_versions", "stock_places", "stock_place_versions")
ITEM_VERSION = (
    "insert into gba.stock_item_versions (tenant_id,item_id,revision,name,archived,created_by) "
    "values (%s,%s,%s,'FAKE direct',false,%s)"
)
PLACE_VERSION = (
    "insert into gba.stock_place_versions (tenant_id,place_id,revision,name,archived,created_by) "
    "values (%s,%s,%s,'FAKE direct',false,%s)"
)


def item_body(**changes: object) -> dict[str, object]:
    return {
        "expected_revision": 0,
        "code": f"M{uuid7().hex[-12:].upper()}",
        "name": "FAKE material",
        "unit": "ml",
        "quantity_scale": 1,
        **changes,
    }


def place_body(location: UUID, **changes: object) -> dict[str, object]:
    return {
        "expected_revision": 0,
        "location_id": str(location),
        "code": f"P{uuid7().hex[-12:].upper()}",
        "name": "FAKE place",
        **changes,
    }


def error(response: httpx.Response) -> tuple[int, str]:
    return response.status_code, response.json()["error"]["code"]


@dataclass(frozen=True)
class Inventory:
    client: httpx.AsyncClient
    world: BookingWorld
    idp: FakeIdp
    owner_conn: psycopg.Connection
    manager: FakeUser
    headers: dict[str, str]

    @property
    def tenant(self) -> UUID:
        return self.world.a.tenant_id

    @property
    def base(self) -> str:
        return f"/v1/businesses/{self.tenant}/inventory"

    async def put(
        self,
        path: str,
        body: dict[str, object],
        key: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        return await self.client.put(
            self.base + path,
            json={"schema_version": 1, **body},
            headers={**(headers or self.headers), "Idempotency-Key": key or str(uuid7())},
        )

    async def get(
        self, path: str, headers: dict[str, str] | None = None, **params: str | int
    ) -> httpx.Response:
        return await self.client.get(
            self.base + path, headers=headers or self.headers, params=params
        )

    def member(self, role: str, location: UUID | None = None) -> tuple[FakeUser, dict[str, str]]:
        user = seed_user(self.owner_conn, f"inventory-{role}-{uuid7()}")
        add_membership(
            self.owner_conn,
            tenant_id=self.tenant,
            user_id=user.user_id,
            role=role,
            location_id=location,
        )
        return user, self.idp.bearer(user.subject, email=user.email)

    async def item(self, **changes: object) -> dict[str, object]:
        response = await self.put(f"/items/{uuid7()}", item_body(**changes))
        assert response.status_code == 200, response.text
        return dict(response.json())

    async def place(self, location: UUID, **changes: object) -> dict[str, object]:
        response = await self.put(f"/places/{uuid7()}", place_body(location, **changes))
        assert response.status_code == 200, response.text
        return dict(response.json())


@pytest.fixture
def accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only fixtures stand in for the STOCK-01 acceptance; the registry stays planned."""
    current = modules.MODULES_BY_ID["inventory"]
    monkeypatch.setitem(
        modules.MODULES_BY_ID,
        "inventory",
        current.model_copy(
            update={"enableable": True, "readiness": Readiness.TECHNICALLY_VERIFIED}
        ),
    )


@pytest.fixture
async def inventory(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager_a: FakeUser,
    idp: FakeIdp,
    owner_conn: psycopg.Connection,
    accepted: None,
) -> Inventory:
    config = Config(client, idp)
    await config.profile(manager_a, world.a.tenant_id, 0, [1])
    await config.publish(manager_a, world.a.tenant_id, 0, ENABLED)
    return Inventory(
        client,
        world,
        idp,
        owner_conn,
        manager_a,
        idp.bearer(manager_a.subject, email=manager_a.email),
    )


async def run_sql(
    pool: RuntimePool,
    tenant: UUID,
    session: UUID,
    statement: str,
    values: tuple[object, ...],
    branch: UUID | None = None,
) -> None:
    """One statement as the runtime role, for this person and optional branch scope."""
    async with tenant_transaction(pool, tenant) as conn:
        await set_user_context(conn, session)
        if branch is not None:
            await conn.execute("select set_config('gba.location_id',%s,true)", (str(branch),))
        await conn.execute(statement.encode("utf-8"), values)


async def refused_sql(
    pool: RuntimePool,
    tenant: UUID,
    session: UUID,
    statement: str,
    values: tuple[object, ...],
    branch: UUID | None = None,
) -> str:
    with pytest.raises(psycopg.DatabaseError) as caught:
        await run_sql(pool, tenant, session, statement, values, branch)
    return str(caught.value.sqlstate)


async def test_packaged_inventory_schema_passes_guard(
    app_pool: RuntimePool, world: BookingWorld
) -> None:
    assert INVENTORY_TABLES[:4] == J1_TABLES
    assert INVENTORY_TABLES[4:] == (
        "stock_posting_rules",
        "stock_documents",
        "stock_document_lines",
        "stock_movements",
        "stock_balances",
        "stock_document_postings",
        "stock_valuations",
        "stock_costs",
    )
    async with tenant_transaction(app_pool, world.a.tenant_id) as conn:
        await assert_inventory_ready(conn)


async def test_unaccepted_inventory_refuses_writes_and_still_reads(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager_a: FakeUser,
    idp: FakeIdp,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # STOCK-01 is technically verified now; a module that is not accepted still refuses writes.
    current = modules.MODULES_BY_ID["inventory"]
    monkeypatch.setitem(
        modules.MODULES_BY_ID,
        "inventory",
        current.model_copy(update={"enableable": False, "readiness": Readiness.PLANNED}),
    )
    base = f"/v1/businesses/{world.a.tenant_id}/inventory"
    auth = idp.bearer(manager_a.subject, email=manager_a.email)
    for path, body in (
        (f"/items/{uuid7()}", item_body()),
        (f"/places/{uuid7()}", place_body(world.a.location_id)),
    ):
        response = await client.put(
            base + path,
            json={"schema_version": 1, **body},
            headers={**auth, "Idempotency-Key": str(uuid7())},
        )
        assert error(response) == (409, "MODULE_NOT_READY"), response.text
    for path in ("/items", "/places"):
        read = await client.get(base + path, headers=auth)
        assert (read.status_code, read.json()["items"]) == (200, []), read.text


async def test_inventory_cannot_be_published_without_finance(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager_a: FakeUser,
    idp: FakeIdp,
    accepted: None,
) -> None:
    config, tenant = Config(client, idp), world.a.tenant_id
    await config.profile(manager_a, tenant, 0, [1])
    assert (
        await config.draft(manager_a, tenant, 0, ["booking_resources", "inventory"])
    ).status_code == 200
    refused = await config.step(manager_a, tenant, 1, "validate", 1)
    assert error(refused) == (422, "CONFIGURATION_INVALID"), refused.text
    assert {
        (p["code"], p["module_id"]) for p in refused.json()["error"]["details"]["problems"]
    } == {("DEPENDENCY_MISSING", "inventory")}


async def test_material_versions_are_idempotent_ordered_and_keep_their_identity(
    inventory: Inventory,
) -> None:
    item, key = uuid7(), str(uuid7())
    body = item_body(code="DYE-01", name="FAKE dye")
    created = await inventory.put(f"/items/{item}", body, key)
    assert created.status_code == 200, created.text
    assert created.json() == {
        "schema_version": 1,
        "business_id": str(inventory.tenant),
        "item_id": str(item),
        "code": "DYE-01",
        "unit": "ml",
        "quantity_scale": 1,
        "revision": 1,
        "name": "FAKE dye",
        "archived": False,
    }
    # The same key replays the stored result; another body under it is refused.
    assert (await inventory.put(f"/items/{item}", body, key)).json() == created.json()
    reused = await inventory.put(f"/items/{item}", {**body, "name": "FAKE other"}, key)
    assert error(reused) == (422, "IDEMPOTENCY_KEY_REUSED"), reused.text

    renamed = await inventory.put(
        f"/items/{item}", {**body, "expected_revision": 1, "name": "FAKE dye 2", "archived": True}
    )
    assert renamed.status_code == 200, renamed.text
    assert (renamed.json()["revision"], renamed.json()["archived"]) == (2, True)
    stale = await inventory.put(f"/items/{item}", {**body, "expected_revision": 1})
    assert error(stale) == (409, "INVENTORY_CONFLICT"), stale.text
    for change in ({"code": "DYE-02"}, {"unit": "g"}, {"quantity_scale": 2}):
        moved = await inventory.put(f"/items/{item}", {**body, "expected_revision": 2, **change})
        assert error(moved) == (422, "INVALID_REFERENCE"), moved.text
    duplicate = await inventory.put(f"/items/{uuid7()}", body)
    assert error(duplicate) == (409, "INVENTORY_CONFLICT"), duplicate.text

    latest = await inventory.get(f"/items/{item}")
    assert latest.json() == renamed.json()
    first = await inventory.get(f"/items/{item}", revision=1)
    assert first.json() == created.json()
    assert error(await inventory.get(f"/items/{uuid7()}")) == (404, "NOT_FOUND")

    other = await inventory.item()
    listed = await inventory.get("/items")
    assert {entry["item_id"] for entry in listed.json()["items"]} == {str(item), other["item_id"]}
    page = await inventory.get("/items", limit=1)
    assert len(page.json()["items"]) == 1
    rest = await inventory.get("/items", limit=1, after=page.json()["next_cursor"])
    assert rest.json()["next_cursor"] is None
    assert {page.json()["items"][0]["item_id"], rest.json()["items"][0]["item_id"]} == {
        str(item),
        other["item_id"],
    }

    with owner_tenant_transaction(inventory.owner_conn, inventory.tenant):
        versions = inventory.owner_conn.execute(
            "select revision,name,archived from gba.stock_item_versions where item_id=%s "
            "order by revision",
            (item,),
        ).fetchall()
        audit = inventory.owner_conn.execute(
            "select action,target_type,details from gba.audit_events where target_id=%s "
            "order by occurred_at,id",
            (str(item),),
        ).fetchall()
    assert versions == [(1, "FAKE dye", False), (2, "FAKE dye 2", True)]
    # One event per accepted command, with identifiers and the revision only.
    assert audit == [
        ("inventory.item", "item", {"revision": 1}),
        ("inventory.item", "item", {"revision": 2}),
    ]


async def test_places_stay_inside_their_branch(inventory: Inventory) -> None:
    home = inventory.world.a.location_id
    away, _ = seed_other_branch(inventory.owner_conn, inventory.world.a)
    _, branch = inventory.member("manager", home)

    place = uuid7()
    body = place_body(home, code="BACK", name="FAKE back room")
    created = await inventory.put(f"/places/{place}", body, headers=branch)
    assert created.status_code == 200, created.text
    assert created.json() == {
        "schema_version": 1,
        "business_id": str(inventory.tenant),
        "place_id": str(place),
        "location_id": str(home),
        "code": "BACK",
        "revision": 1,
        "name": "FAKE back room",
        "archived": False,
    }
    # A branch manager does not create or see a place of another branch.
    outside = await inventory.put(f"/places/{uuid7()}", place_body(away), headers=branch)
    assert error(outside) == (403, "PERMISSION_DENIED"), outside.text
    remote = await inventory.place(away, code="BACK")
    assert remote["location_id"] == str(away)
    seen = await inventory.get("/places", headers=branch)
    assert [entry["place_id"] for entry in seen.json()["items"]] == [str(place)]
    assert error(await inventory.get(f"/places/{remote['place_id']}", headers=branch)) == (
        404,
        "NOT_FOUND",
    )
    everything = await inventory.get("/places")
    assert {entry["place_id"] for entry in everything.json()["items"]} == {
        str(place),
        remote["place_id"],
    }

    # A code is unique inside its branch, and a place never moves.
    duplicate = await inventory.put(f"/places/{uuid7()}", place_body(home, code="BACK"))
    assert error(duplicate) == (409, "INVENTORY_CONFLICT"), duplicate.text
    moved = await inventory.put(
        f"/places/{place}", {**body, "expected_revision": 1, "location_id": str(away)}
    )
    assert error(moved) == (422, "INVALID_REFERENCE"), moved.text
    renamed = await inventory.put(
        f"/places/{place}", {**body, "expected_revision": 1, "name": "FAKE shelf"}, headers=branch
    )
    assert (renamed.status_code, renamed.json()["revision"]) == (200, 2), renamed.text
    assert (await inventory.get(f"/places/{place}", revision=1)).json() == created.json()

    # The material list is shared: a branch manager reads it and does not change it.
    material = await inventory.item()
    listed = await inventory.get("/items", headers=branch)
    assert [entry["item_id"] for entry in listed.json()["items"]] == [material["item_id"]]
    change = await inventory.put(f"/items/{uuid7()}", item_body(), headers=branch)
    assert error(change) == (403, "PERMISSION_DENIED"), change.text


async def test_staff_support_and_other_companies_are_refused(inventory: Inventory) -> None:
    home = inventory.world.a.location_id
    place = await inventory.place(home)
    foreign = seed_user(inventory.owner_conn, f"foreign-{uuid7()}")
    support = seed_user(inventory.owner_conn, f"support-{uuid7()}")
    add_membership(
        inventory.owner_conn,
        tenant_id=inventory.world.b.tenant_id,
        user_id=foreign.user_id,
        role="owner",
    )
    grant_platform_admin(inventory.owner_conn, user_id=support.user_id, granted_by="test:inventory")
    refused = [
        inventory.member("artist", home)[1],
        inventory.member("front_desk")[1],
        inventory.idp.bearer(foreign.subject, email=foreign.email),
        inventory.idp.bearer(support.subject, email=support.email),
    ]
    for headers in refused:
        for path in ("/items", "/places", f"/places/{place['place_id']}"):
            assert (await inventory.get(path, headers=headers)).status_code == 403
        for path, body in (
            (f"/items/{uuid7()}", item_body()),
            (f"/places/{uuid7()}", place_body(home)),
        ):
            assert (await inventory.put(path, body, headers=headers)).status_code == 403
    with owner_tenant_transaction(inventory.owner_conn, inventory.tenant):
        counts = inventory.owner_conn.execute(
            "select (select count(*) from gba.stock_items),(select count(*) from gba.stock_places)"
        ).fetchone()
    assert counts == (0, 1)


async def test_sql_keeps_versions_ordered_authored_and_immutable(
    inventory: Inventory, app_pool: RuntimePool
) -> None:
    tenant, home = inventory.tenant, inventory.world.a.location_id
    away, _ = seed_other_branch(inventory.owner_conn, inventory.world.a)
    user = inventory.manager.user_id
    artist = inventory.member("artist")[0].user_id
    local = inventory.member("manager", home)[0].user_id
    remote = inventory.member("manager", away)[0].user_id
    item = UUID(str((await inventory.item())["item_id"]))
    place = UUID(str((await inventory.place(home))["place_id"]))

    async def refused(
        statement: str,
        values: tuple[object, ...],
        session: UUID = user,
        branch: UUID | None = None,
    ) -> str:
        return await refused_sql(app_pool, tenant, session, statement, values, branch)

    # Versions never skip and never repeat.
    for revision in (0, 1, 3):
        assert await refused(ITEM_VERSION, (tenant, item, revision, user)) in ("GBS01", "23505")
        assert await refused(PLACE_VERSION, (tenant, place, revision, user)) in ("GBS01", "23505")
    # The author is the authenticated owner or manager with the needed scope.
    assert await refused(ITEM_VERSION, (tenant, item, 2, artist), session=artist) == "42501"
    assert await refused(ITEM_VERSION, (tenant, item, 2, user), session=artist) == "42501"
    assert await refused(ITEM_VERSION, (tenant, item, 2, local), session=local) == "42501"
    assert await refused(ITEM_VERSION, (tenant, item, 2, local), local, home) == "42501"
    assert await refused(PLACE_VERSION, (tenant, place, 2, artist), session=artist) == "42501"
    assert await refused(PLACE_VERSION, (tenant, place, 2, remote), session=remote) == "42501"
    assert await refused(PLACE_VERSION, (tenant, place, 2, remote), remote, away) == "42501"
    assert await refused(PLACE_VERSION, (tenant, place, 2, user), session=local) == "42501"
    await run_sql(app_pool, tenant, local, PLACE_VERSION, (tenant, place, 2, local), home)
    await run_sql(app_pool, tenant, user, ITEM_VERSION, (tenant, item, 2, user))

    # A head needs its first version, a place needs a branch of this company.
    columns = "insert into gba.stock_items (tenant_id,id,code,unit,quantity_scale) "
    head = columns + "values (%s,%s,%s,'g',0)"
    assert await refused(head, (tenant, uuid7(), "LONELY")) == "23514"
    foreign = (
        "insert into gba.stock_places (tenant_id,id,location_id,code) values (%s,%s,%s,'FOREIGN')"
    )
    assert await refused(foreign, (tenant, uuid7(), inventory.world.b.location_id)) == "23503"
    for scale in (-1, 4):
        bad = columns + f"values (%s,%s,'BAD','g',{scale})"
        assert await refused(bad, (tenant, uuid7())) == "23514"

    # Nothing recorded is rewritten or removed, by the runtime role or by the schema owner.
    for table in J1_TABLES:
        assert await refused(f"delete from gba.{table} where tenant_id=%s", (tenant,)) == "42501"
        assert (
            await refused(
                f"update gba.{table} set tenant_id=tenant_id where tenant_id=%s", (tenant,)
            )
            == "42501"
        )
        for statement in (
            f"delete from gba.{table}",
            f"update gba.{table} set tenant_id=tenant_id",
        ):
            with (
                pytest.raises(psycopg.errors.CheckViolation),
                owner_tenant_transaction(inventory.owner_conn, tenant),
            ):
                inventory.owner_conn.execute(statement.encode("utf-8"))
    for head_table in ("stock_items", "stock_places"):
        # The lock grant on the identifier does not open a way to change it.
        assert (
            await refused(f"update gba.{head_table} set id=id where tenant_id=%s", (tenant,))
            == "23514"
        )
    with owner_tenant_transaction(inventory.owner_conn, tenant):
        rows = inventory.owner_conn.execute(
            "select (select count(*) from gba.stock_items),"
            "(select count(*) from gba.stock_item_versions),"
            "(select count(*) from gba.stock_places),"
            "(select count(*) from gba.stock_place_versions)"
        ).fetchone()
    assert rows == (1, 2, 1, 2)


async def test_disabled_inventory_keeps_reads_and_refuses_writes(
    inventory: Inventory, app_pool: RuntimePool
) -> None:
    tenant, home = inventory.tenant, inventory.world.a.location_id
    user = inventory.manager.user_id
    material, place = await inventory.item(), await inventory.place(home)
    await Config(inventory.client, inventory.idp).publish(
        inventory.manager, tenant, 1, ["booking_resources", "finance"]
    )
    kept = await inventory.get(f"/items/{material['item_id']}")
    assert kept.json() == material
    assert (await inventory.get(f"/places/{place['place_id']}")).json() == place
    for path, body in (
        (f"/items/{uuid7()}", item_body()),
        (f"/places/{uuid7()}", place_body(home)),
        (f"/items/{material['item_id']}", {**material_input(material), "name": "FAKE later"}),
    ):
        assert error(await inventory.put(path, body)) == (409, "MODULE_DISABLED")
    item = UUID(str(material["item_id"]))
    assert (
        await refused_sql(app_pool, tenant, user, ITEM_VERSION, (tenant, item, 2, user)) == "GBM01"
    )


def material_input(view: dict[str, object]) -> dict[str, object]:
    return {
        "expected_revision": view["revision"],
        "code": view["code"],
        "name": view["name"],
        "unit": view["unit"],
        "quantity_scale": view["quantity_scale"],
        "archived": view["archived"],
    }
