"""L3: visit completion and material consumption (package L, BEAUTY-01; FAKE data only).

Design docs/plan/PACKAGE_L3_DESIGN_2026-10-22.md: recipes per variant and add-on; completing a
started confirmed visit records planned and actual quantities; posting the consumption is one
write-off through STOCK-01 with the rights of any write-off.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.booking.models import ReservationRequest
from gorgona_booking.booking.service import BookingService
from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from tests.integration import test_stock as shared
from tests.integration.test_inventory import error
from tests.integration.test_stock import DAY, Stock
from tests.integration.test_stock_write_offs import received

pytestmark = pytest.mark.anyio
stock = shared.stock
inventory = shared.inventory
accepted = shared.accepted
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
__all__ = ["accepted", "client", "idp", "inventory", "manager_a", "stock"]


def salon(stock: Stock) -> str:
    return f"/v1/salons/{stock.tenant}"


def keyed(stock: Stock, key: str | None = None) -> dict[str, str]:
    return {**stock.inventory.headers, "Idempotency-Key": key or str(uuid7())}


async def revision_of(stock: Stock, variant: UUID) -> int:
    listed = await stock.inventory.client.get(
        f"{salon(stock)}/services", headers=stock.inventory.headers
    )
    (row,) = [s for s in listed.json() if s["id"] == str(variant)]
    return int(row["revision"])


async def recipe(
    stock: Stock, owner: str, owner_id: UUID, lines: list[dict[str, object]], revision: int
) -> httpx.Response:
    return await stock.inventory.client.put(
        f"{salon(stock)}/{owner}/{owner_id}/materials",
        json={"expected_revision": revision, "lines": lines},
        headers=keyed(stock),
    )


async def started_visit(
    stock: Stock, pool: RuntimePool, *, add_ons: tuple[UUID, ...] = (), hours_ago: int = 3
) -> UUID:
    world = stock.inventory.world
    start = datetime.now(UTC).replace(second=0, microsecond=0) - timedelta(hours=hours_ago)
    result = await BookingService(pool).create_confirmed_booking(
        stock.tenant,
        ReservationRequest(
            resource_id=world.artist_a1,
            variant_id=world.catalog_a.base_variant_id,
            starts_at=start,
            add_on_ids=add_ons,
        ),
        actor="test:l3",
        idempotency_key=None,
    )
    return result.booking_id


@pytest.fixture
async def kit(stock: Stock, app_pool: RuntimePool) -> dict[str, UUID]:
    world = stock.inventory.world
    dye = await stock.inventory.item(name="FAKE dye", unit="ml", quantity_scale=1)
    foil = await stock.inventory.item(name="FAKE foil", unit="pc", quantity_scale=0)
    assert (await stock.set_rules()).status_code == 200
    await received(stock, dye["item_id"], "100.0", "50.00")
    await received(stock, foil["item_id"], "40", "20.00")
    base = world.catalog_a.base_variant_id
    saved = await recipe(
        stock,
        "services",
        base,
        [{"item_id": dye["item_id"], "quantity": "2.5"}],
        await revision_of(stock, base),
    )
    assert saved.status_code == 200, saved.text
    massage = world.catalog_a.massage_add_on_id
    added = await recipe(
        stock,
        "add-ons",
        massage,
        [
            {"item_id": dye["item_id"], "quantity": "1.0"},
            {"item_id": foil["item_id"], "quantity": "3"},
        ],
        int(str(stock.rows("select revision from gba.add_ons where id=%s", massage)[0][0])),
    )
    assert added.status_code == 200, added.text
    return {"dye": UUID(str(dye["item_id"])), "foil": UUID(str(foil["item_id"]))}


# L3-01 ------------------------------------------------------------------------------


async def test_a_recipe_is_replaced_whole_with_its_revision(stock: Stock) -> None:
    dye = await stock.inventory.item(name="FAKE dye", unit="ml", quantity_scale=1)
    base = stock.inventory.world.catalog_a.base_variant_id
    revision = await revision_of(stock, base)
    saved = await recipe(
        stock, "services", base, [{"item_id": dye["item_id"], "quantity": "2.5"}], revision
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["owner_revision"] == revision + 1
    assert body["lines"] == [{"item_id": dye["item_id"], "quantity": "2.5"}]
    stale = await recipe(stock, "services", base, [], revision)
    assert error(stale) == (409, "SERVICE_REVISION_CONFLICT")
    finer = await recipe(
        stock, "services", base, [{"item_id": dye["item_id"], "quantity": "2.55"}], revision + 1
    )
    assert finer.status_code == 422, finer.text
    unknown = await recipe(
        stock, "services", base, [{"item_id": str(uuid7()), "quantity": "1"}], revision + 1
    )
    assert unknown.status_code == 422, unknown.text
    cleared = await recipe(stock, "services", base, [], revision + 1)
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["lines"] == []


# L3-02 / L3-03 ----------------------------------------------------------------------


async def test_completion_records_planned_and_actual_quantities(
    stock: Stock, kit: dict[str, UUID], app_pool: RuntimePool
) -> None:
    massage = stock.inventory.world.catalog_a.massage_add_on_id
    booking = await started_visit(stock, app_pool, add_ons=(massage,))
    path = f"{salon(stock)}/bookings/{booking}/complete"
    body = {"quantities": [{"item_id": str(kit["foil"]), "quantity": "4"}]}
    done = await stock.inventory.client.post(path, json=body, headers=keyed(stock, "l3-done-1"))
    assert done.status_code == 200, done.text
    view = done.json()
    assert view["booking_id"] == str(booking)
    assert view["stock_document_id"] is None
    assert {(m["item_id"], m["planned"], m["actual"]) for m in view["materials"]} == {
        (str(kit["dye"]), "3.5", "3.5"),
        (str(kit["foil"]), "3", "4"),
    }
    again = await stock.inventory.client.post(path, json=body, headers=keyed(stock, "l3-done-1"))
    assert again.status_code == 200, again.text
    assert again.json() == view
    other = await stock.inventory.client.post(path, json={}, headers=keyed(stock, "l3-done-2"))
    assert error(other) == (409, "VISIT_ALREADY_COMPLETED")


async def test_only_a_started_confirmed_visit_completes(
    stock: Stock, kit: dict[str, UUID], app_pool: RuntimePool
) -> None:
    future = await started_visit(stock, app_pool, hours_ago=-30)
    early = await stock.inventory.client.post(
        f"{salon(stock)}/bookings/{future}/complete", json={}, headers=keyed(stock)
    )
    assert error(early) == (409, "VISIT_NOT_COMPLETABLE")
    past = await started_visit(stock, app_pool, hours_ago=6)
    await BookingService(app_pool).cancel(stock.tenant, past, actor="test:l3")
    cancelled = await stock.inventory.client.post(
        f"{salon(stock)}/bookings/{past}/complete", json={}, headers=keyed(stock)
    )
    assert error(cancelled) == (409, "VISIT_NOT_COMPLETABLE")


# L3-04 ------------------------------------------------------------------------------


async def test_the_consumption_is_written_off_once_at_average_cost(
    stock: Stock, kit: dict[str, UUID], app_pool: RuntimePool
) -> None:
    massage = stock.inventory.world.catalog_a.massage_add_on_id
    booking = await started_visit(stock, app_pool, add_ons=(massage,))
    done = await stock.inventory.client.post(
        f"{salon(stock)}/bookings/{booking}/complete", json={}, headers=keyed(stock)
    )
    assert done.status_code == 200, done.text
    before = stock.counts()
    path = f"{salon(stock)}/bookings/{booking}/consumption"
    body = {
        "legal_entity_id": str(stock.entity),
        "place_id": stock.place["place_id"],
        "document_date": DAY,
    }
    posted = await stock.inventory.client.post(path, json=body, headers=keyed(stock, "l3-use-1"))
    assert posted.status_code == 200, posted.text
    document = posted.json()["stock_document_id"]
    assert document is not None
    seen = await stock.inventory.get(f"/documents/{document}")
    assert seen.status_code == 200, seen.text
    head = seen.json()
    assert (head["kind"], head["reason"]) == ("write_off", "used")
    # 3.5 ml of 100 ml worth 50.00 and 3 of 40 pieces worth 20.00, at the moving average.
    assert sorted((line["item_id"], line["quantity"]) for line in head["lines"]) == sorted(
        [(str(kit["dye"]), "3.5"), (str(kit["foil"]), "3")]
    )
    assert head["money"]["total"] == "3.25"
    after = stock.counts()
    assert after["stock_entries"] == before["stock_entries"] + 1
    value, on_account = stock.reconciled()
    assert value == on_account
    # Once: the same key and another key answer the same document, nothing new is posted.
    for key in ("l3-use-1", "l3-use-2"):
        again = await stock.inventory.client.post(path, json=body, headers=keyed(stock, key))
        assert again.status_code == 200, again.text
        assert again.json()["stock_document_id"] == document
    assert stock.counts() == after


async def test_consumption_needs_a_completion(
    stock: Stock, kit: dict[str, UUID], app_pool: RuntimePool
) -> None:
    booking = await started_visit(stock, app_pool)
    refused = await stock.inventory.client.post(
        f"{salon(stock)}/bookings/{booking}/consumption",
        json={
            "legal_entity_id": str(stock.entity),
            "place_id": stock.place["place_id"],
            "document_date": DAY,
        },
        headers=keyed(stock),
    )
    assert error(refused) == (409, "VISIT_NOT_COMPLETED")


# L3-05 ------------------------------------------------------------------------------


async def test_front_desk_completes_but_cannot_post_the_consumption(
    stock: Stock, kit: dict[str, UUID], app_pool: RuntimePool
) -> None:
    booking = await started_visit(stock, app_pool)
    _, desk = stock.inventory.member("front_desk")
    done = await stock.inventory.client.post(
        f"{salon(stock)}/bookings/{booking}/complete",
        json={},
        headers={**desk, "Idempotency-Key": str(uuid7())},
    )
    assert done.status_code == 200, done.text
    before = stock.counts()
    refused = await stock.inventory.client.post(
        f"{salon(stock)}/bookings/{booking}/consumption",
        json={
            "legal_entity_id": str(stock.entity),
            "place_id": stock.place["place_id"],
            "document_date": DAY,
        },
        headers={**desk, "Idempotency-Key": str(uuid7())},
    )
    assert refused.status_code == 403, refused.text
    assert stock.counts() == before


# L3-06 ------------------------------------------------------------------------------


async def test_completions_are_permanent_and_company_scoped(
    stock: Stock, kit: dict[str, UUID], app_pool: RuntimePool
) -> None:
    booking = await started_visit(stock, app_pool)
    done = await stock.inventory.client.post(
        f"{salon(stock)}/bookings/{booking}/complete", json={}, headers=keyed(stock)
    )
    assert done.status_code == 200, done.text
    for statement in (
        "update gba.visit_completions set completed_at = now() where booking_id = %s",
        "delete from gba.visit_completions where booking_id = %s",
        "delete from gba.visit_material_uses where booking_id = %s",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with tenant_transaction(app_pool, stock.tenant) as conn:
                await conn.execute(statement, (booking,))
    other = stock.inventory.world.b.tenant_id
    async with tenant_transaction(app_pool, other) as conn:
        seen = await (
            await conn.execute(
                "select count(*) from gba.visit_completions where booking_id = %s", (booking,)
            )
        ).fetchone()
    assert seen == (0,)
