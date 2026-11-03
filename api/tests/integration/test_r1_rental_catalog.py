"""R1: the rental module, item classes and units (package R, RENT-01; FAKE data only).

ADR-0036 and docs/plan/PACKAGE_R1_DESIGN_2026-11-03.md: a class has a typed attribute set per
revision; a unit has an identifier unique in the business, a branch, a state and values checked
against its class.
"""

from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.business import modules
from gorgona_booking.business.readiness_registry import Readiness
from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import add_membership
from tests.integration import test_management_api as shared
from tests.integration.booking_support import BookingWorld
from tests.integration.configuration_support import Config
from tests.integration.seed import FakeUser, seed_other_branch, seed_user
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
manager_b = shared.manager_b
__all__ = ["client", "idp", "manager_a", "manager_b"]
ENABLED = ["booking_resources", "counterparties", "finance", "finance_documents", "rental"]
ATTRIBUTES = [
    {"key": "seats", "label": "Seats", "type": "number", "required": True},
    {"key": "automatic", "label": "Automatic", "type": "boolean", "required": False},
    {"key": "color", "label": "Color", "type": "text", "required": False},
]


def error(response: httpx.Response) -> tuple[int, str]:
    return response.status_code, response.json()["error"]["code"]


@dataclass(frozen=True)
class Rental:
    client: httpx.AsyncClient
    world: BookingWorld
    owner_conn: psycopg.Connection
    idp: FakeIdp
    headers: dict[str, str]

    @property
    def tenant(self) -> UUID:
        return self.world.a.tenant_id

    @property
    def base(self) -> str:
        return f"/v1/businesses/{self.tenant}/rental"

    async def put(
        self,
        path: str,
        body: dict[str, Any],
        headers: dict[str, str] | None = None,
        key: str | None = None,
    ) -> httpx.Response:
        return await self.client.put(
            self.base + path,
            json={"schema_version": 1, **body},
            headers={**(headers or self.headers), "Idempotency-Key": key or str(uuid7())},
        )

    async def get(self, path: str, headers: dict[str, str] | None = None) -> httpx.Response:
        return await self.client.get(self.base + path, headers=headers or self.headers)

    async def klass(
        self,
        class_id: UUID,
        revision: int = 0,
        headers: dict[str, str] | None = None,
        **changes: Any,
    ) -> httpx.Response:
        body = {
            "expected_revision": revision,
            "code": f"CAR-{class_id.hex[-6:].upper()}",
            "name": "FAKE compact car",
            "meter_kind": "odometer",
            "attributes": ATTRIBUTES,
            **changes,
        }
        return await self.put(f"/classes/{class_id}", body, headers)

    async def unit(
        self,
        unit_id: UUID,
        class_id: UUID,
        revision: int = 0,
        headers: dict[str, str] | None = None,
        **changes: Any,
    ) -> httpx.Response:
        body = {
            "expected_revision": revision,
            "class_id": str(class_id),
            "identifier": f"FAKE-VIN-{unit_id.hex[-8:].upper()}",
            "location_id": str(self.world.a.location_id),
            "state": "active",
            "values": {"seats": "5", "automatic": "true"},
            **changes,
        }
        return await self.put(f"/units/{unit_id}", body, headers)

    def member(self, role: str, location: UUID | None) -> dict[str, str]:
        user = seed_user(self.owner_conn, f"rental-{role}-{uuid7()}")
        add_membership(
            self.owner_conn,
            tenant_id=self.tenant,
            user_id=user.user_id,
            role=role,
            location_id=location,
        )
        return self.idp.bearer(user.subject, email=user.email)


@pytest.fixture
def accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only fixtures stand in for the package R acceptance; the registry stays implemented."""
    current = modules.MODULES_BY_ID["rental"]
    monkeypatch.setitem(
        modules.MODULES_BY_ID,
        "rental",
        current.model_copy(
            update={"enableable": True, "readiness": Readiness.TECHNICALLY_VERIFIED}
        ),
    )


@pytest.fixture
async def rental(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager_a: FakeUser,
    idp: FakeIdp,
    owner_conn: psycopg.Connection,
    accepted: None,
) -> Rental:
    config = Config(client, idp)
    await config.profile(manager_a, world.a.tenant_id, 0, [23])
    await config.publish(manager_a, world.a.tenant_id, 0, ENABLED)
    headers = idp.bearer(manager_a.subject, email=manager_a.email)
    return Rental(client, world, owner_conn, idp, headers)


async def _counts(pool: RuntimePool, tenant: UUID) -> tuple[int, ...]:
    async with tenant_transaction(pool, tenant) as conn:
        row = await (
            await conn.execute(
                "select (select count(*) from gba.rental_classes), "
                "(select count(*) from gba.rental_class_attributes), "
                "(select count(*) from gba.rental_units), "
                "(select count(*) from gba.rental_unit_values)"
            )
        ).fetchone()
    assert row is not None
    return tuple(int(n) for n in row)


# R1-01 ------------------------------------------------------------------------------


async def test_the_module_is_registered_but_cannot_be_enabled(
    client: httpx.AsyncClient, world: BookingWorld, manager_a: FakeUser, idp: FakeIdp
) -> None:
    headers = idp.bearer(manager_a.subject, email=manager_a.email)
    catalog = await client.get(
        f"/v1/businesses/{world.a.tenant_id}/module-catalog", headers=headers
    )
    assert catalog.status_code == 200, catalog.text
    (entry,) = [m for m in catalog.json()["modules"] if m["id"] == "rental"]
    assert (entry["readiness"], entry["enableable"]) == ("implemented", False)
    assert entry["depends_on"] == ["counterparties", "finance_documents"]
    base = f"/v1/businesses/{world.a.tenant_id}/rental"
    refused = await client.put(
        f"{base}/classes/{uuid7()}",
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "code": "CAR",
            "name": "FAKE",
            "meter_kind": "none",
            "attributes": [],
        },
        headers={**headers, "Idempotency-Key": str(uuid7())},
    )
    assert error(refused) == (409, "MODULE_NOT_READY"), refused.text
    read = await client.get(f"{base}/classes", headers=headers)
    assert (read.status_code, read.json()["items"]) == (200, []), read.text


# R1-02 ------------------------------------------------------------------------------


async def test_a_class_is_replaced_with_its_revision_and_attributes(rental: Rental) -> None:
    car = uuid7()
    saved = await rental.klass(car)
    assert saved.status_code == 200, saved.text
    view = saved.json()
    assert (view["class_id"], view["revision"], view["meter_kind"]) == (str(car), 1, "odometer")
    assert [a["key"] for a in view["attributes"]] == ["seats", "automatic", "color"]
    stale = await rental.klass(car, revision=0, name="FAKE sedan")
    assert error(stale) == (409, "RENTAL_REVISION_CONFLICT")
    renamed = await rental.klass(car, revision=1, name="FAKE sedan", attributes=ATTRIBUTES[:1])
    assert renamed.status_code == 200, renamed.text
    assert (renamed.json()["revision"], renamed.json()["name"]) == (2, "FAKE sedan")
    assert [a["key"] for a in renamed.json()["attributes"]] == ["seats"]
    recoded = await rental.klass(car, revision=2, code="CAR-OTHER")
    assert error(recoded) == (409, "RENTAL_CODE_FIXED")
    taken = await rental.klass(uuid7(), code=view["code"])
    assert error(taken) == (409, "RENTAL_CODE_TAKEN")
    for bad in (
        {"attributes": [ATTRIBUTES[0], ATTRIBUTES[0]]},
        {"attributes": [{**ATTRIBUTES[0], "key": "Seats"}]},
        {"attributes": [{**ATTRIBUTES[0], "type": "date"}]},
        {"meter_kind": "fuel"},
        {"code": "car lower"},
    ):
        refused = await rental.klass(uuid7(), **bad)
        assert refused.status_code == 422, (bad, refused.text)
    listed = await rental.get("/classes")
    assert [c["class_id"] for c in listed.json()["items"]] == [str(car)]


# R1-03 ------------------------------------------------------------------------------


async def test_a_unit_has_typed_values_checked_against_its_class(rental: Rental) -> None:
    car, unit = uuid7(), uuid7()
    assert (await rental.klass(car)).status_code == 200
    saved = await rental.unit(unit, car)
    assert saved.status_code == 200, saved.text
    view = saved.json()
    assert (view["unit_id"], view["revision"], view["state"]) == (str(unit), 1, "active")
    assert view["values"] == {"seats": "5", "automatic": "true"}
    for values in (
        {"seats": "five"},
        {"seats": "5", "automatic": "yes"},
        {"automatic": "true"},
        {"seats": "5", "wheels": "4"},
    ):
        refused = await rental.unit(uuid7(), car, values=values)
        assert error(refused) == (422, "RENTAL_VALUE_INVALID"), (values, refused.text)
    moved = await rental.unit(unit, car, revision=1, values={"seats": "7", "color": "FAKE red"})
    assert (moved.status_code, moved.json()["revision"]) == (200, 2), moved.text
    assert moved.json()["values"] == {"seats": "7", "color": "FAKE red"}
    taken = await rental.unit(uuid7(), car, identifier=view["identifier"])
    assert error(taken) == (409, "RENTAL_IDENTIFIER_TAKEN")
    van = uuid7()
    assert (await rental.klass(van, meter_kind="hours")).status_code == 200
    reclassed = await rental.unit(unit, van, revision=2)
    assert error(reclassed) == (409, "RENTAL_UNIT_FIXED")
    renamed = await rental.unit(unit, car, revision=2, identifier="FAKE-OTHER")
    assert error(renamed) == (409, "RENTAL_UNIT_FIXED")
    unknown = await rental.unit(uuid7(), uuid7())
    assert error(unknown) == (422, "INVALID_REFERENCE")
    retired = await rental.unit(unit, car, revision=2, state="retired")
    assert (retired.status_code, retired.json()["state"]) == (200, "retired"), retired.text
    again = await rental.unit(unit, car, revision=3, state="active")
    assert error(again) == (409, "RENTAL_UNIT_RETIRED")
    listed = await rental.get(f"/units?class_id={car}")
    assert [u["unit_id"] for u in listed.json()["items"]] == [str(unit)]
    assert (await rental.get(f"/units?class_id={van}")).json()["items"] == []


async def test_a_unit_save_replays_by_its_key(rental: Rental) -> None:
    car, unit = uuid7(), uuid7()
    assert (await rental.klass(car)).status_code == 200
    key = str(uuid7())
    body = {
        "expected_revision": 0,
        "class_id": str(car),
        "identifier": "FAKE-VIN-REPLAY",
        "location_id": str(rental.world.a.location_id),
        "state": "active",
        "values": {"seats": "2"},
    }
    first = await rental.put(f"/units/{unit}", body, key=key)
    again = await rental.put(f"/units/{unit}", body, key=key)
    assert (first.status_code, again.status_code) == (200, 200), again.text
    assert again.json() == first.json()
    other = await rental.put(f"/units/{unit}", {**body, "values": {"seats": "3"}}, key=key)
    assert error(other) == (422, "IDEMPOTENCY_KEY_REUSED")


# R1-04 ------------------------------------------------------------------------------


async def test_rights_branch_scope_and_another_company(
    rental: Rental, app_pool: RuntimePool, idp: FakeIdp, manager_b: FakeUser
) -> None:
    world = rental.world
    home = world.a.location_id
    away, _ = seed_other_branch(rental.owner_conn, world.a)
    car, here, there = uuid7(), uuid7(), uuid7()
    assert (await rental.klass(car)).status_code == 200
    assert (await rental.unit(here, car)).status_code == 200
    assert (await rental.unit(there, car, location_id=str(away))).status_code == 200
    desk = rental.member("front_desk", None)
    assert (await rental.get("/classes", headers=desk)).status_code == 403
    assert (await rental.klass(uuid7(), headers=desk)).status_code == 403
    branch = rental.member("manager", home)
    seen = await rental.get("/units", headers=branch)
    assert [u["unit_id"] for u in seen.json()["items"]] == [str(here)]
    hidden = await rental.get(f"/units/{there}", headers=branch)
    assert error(hidden) == (404, "NOT_FOUND"), hidden.text
    outside = await rental.unit(uuid7(), car, headers=branch, location_id=str(away))
    assert error(outside) == (422, "INVALID_REFERENCE"), outside.text
    mine = await rental.unit(uuid7(), car, headers=branch)
    assert mine.status_code == 200, mine.text
    classes = await rental.get("/classes", headers=branch)
    assert [c["class_id"] for c in classes.json()["items"]] == [str(car)]
    company = await rental.klass(uuid7(), headers=branch)
    assert error(company) == (403, "PERMISSION_DENIED"), company.text
    other = idp.bearer(manager_b.subject, email=manager_b.email)
    foreign = await rental.get("/units", headers=other)
    assert foreign.status_code in (403, 404), foreign.text
    assert await _counts(app_pool, world.b.tenant_id) == (0, 0, 0, 0)


# R1-05 ------------------------------------------------------------------------------


async def test_sql_keeps_classes_and_units_whole(rental: Rental, app_pool: RuntimePool) -> None:
    car, unit = uuid7(), uuid7()
    assert (await rental.klass(car)).status_code == 200
    assert (await rental.unit(unit, car)).status_code == 200
    tenant = rental.tenant
    for statement in (
        "update gba.rental_class_attributes set required = false",
        "delete from gba.rental_class_attributes",
        "update gba.rental_unit_values set value = '9'",
        "delete from gba.rental_unit_values",
        "update gba.rental_units set class_id = class_id",
        "update gba.rental_classes set code = 'FAKE'",
        "delete from gba.rental_units",
        "delete from gba.rental_classes",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with tenant_transaction(app_pool, tenant) as conn:
                await conn.execute(statement)
    forged = (
        "insert into gba.rental_unit_values (tenant_id, unit_id, revision, key, value) "
        "values (%s, %s, 1, %s, %s)"
    )
    for key, value in (("color", "FAKE"), ("wheels", "4")):
        with pytest.raises(psycopg.errors.CheckViolation):
            async with tenant_transaction(app_pool, tenant) as conn:
                await conn.execute(forged, (tenant, unit, key, value))
    with pytest.raises(psycopg.errors.CheckViolation):
        async with tenant_transaction(app_pool, tenant) as conn:
            await conn.execute(
                "insert into gba.rental_class_attributes "
                "(tenant_id, class_id, revision, key, label, type, required) "
                "values (%s, %s, 1, 'doors', 'Doors', 'number', false)",
                (tenant, car),
            )
    with pytest.raises(psycopg.errors.CheckViolation):
        async with tenant_transaction(app_pool, tenant) as conn:
            await conn.execute(
                "update gba.rental_units set revision = 2, updated_at = now() where id = %s",
                (unit,),
            )
    assert await _counts(app_pool, tenant) == (1, 3, 1, 2)


async def test_without_the_module_writes_are_refused_and_reads_continue(
    rental: Rental, app_pool: RuntimePool, idp: FakeIdp, manager_a: FakeUser
) -> None:
    car, unit = uuid7(), uuid7()
    assert (await rental.klass(car)).status_code == 200
    assert (await rental.unit(unit, car)).status_code == 200
    tenant = rental.tenant
    before = await _counts(app_pool, tenant)
    await Config(rental.client, idp).publish(
        manager_a, tenant, 1, ["booking_resources", "counterparties"]
    )
    off_class = await rental.klass(uuid7())
    assert error(off_class) == (409, "MODULE_DISABLED"), off_class.text
    off_unit = await rental.unit(unit, car, revision=1, values={"seats": "9"})
    assert error(off_unit) == (409, "MODULE_DISABLED"), off_unit.text
    assert await _counts(app_pool, tenant) == before
    read = await rental.get(f"/units/{unit}")
    assert (read.status_code, read.json()["values"]["seats"]) == (200, "5"), read.text
