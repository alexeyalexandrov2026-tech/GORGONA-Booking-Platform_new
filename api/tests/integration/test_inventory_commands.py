"""J5: an inventory command whose answer was lost is settled by its key, on real PostgreSQL 18.

Resolving tells whether the command took effect; cancelling an unresolved one makes sure a
late copy of it is refused. Both work only on the caller's own keys.
"""

from uuid import uuid7

import httpx
import pytest

from tests.integration import test_stock as shared
from tests.integration.configuration_support import Config
from tests.integration.test_inventory import error, material_input
from tests.integration.test_stock import Stock
from tests.integration.test_stock_write_offs import received, write_off

pytestmark = pytest.mark.anyio
stock = shared.stock
inventory = shared.inventory
accepted = shared.accepted
client = shared.client
idp = shared.idp
manager_a = shared.manager_a


def reference(operation: str, subject: object, revision: int = 0) -> dict[str, object]:
    return {
        "schema_version": 1,
        "operation": operation,
        "subject_id": str(subject),
        "revision": revision,
    }


async def settle(
    stock: Stock,
    key: str,
    body: dict[str, object],
    action: str = "resolve",
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    return await stock.inventory.client.post(
        stock.inventory.base + f"/commands/{key}/{action}",
        json=body,
        headers=headers or stock.inventory.headers,
    )


async def test_a_posted_document_resolves_as_committed_and_an_unknown_key_as_unresolved(
    stock: Stock,
) -> None:
    assert (await stock.set_rules()).status_code == 200
    item = (await stock.inventory.item(quantity_scale=0))["item_id"]
    await received(stock, item, "5", "10.00")
    document, key = uuid7(), f"stock-{uuid7()}"
    used = await stock.post(write_off(stock, [{"item_id": item, "quantity": "1"}]), document, key)
    assert used.status_code == 200, used.text
    found = await settle(stock, key, reference("document", document))
    assert found.status_code == 200, found.text
    assert found.json() == {
        "schema_version": 1,
        "business_id": str(stock.tenant),
        "key": key,
        "operation": "document",
        "state": "committed",
    }
    # The receipt names another document: the reference is refused, not guessed.
    other = await settle(stock, key, reference("document", uuid7()))
    assert error(other) == (422, "INVALID_REFERENCE"), other.text
    missing = await settle(stock, f"stock-{uuid7()}", reference("document", uuid7()))
    assert missing.json()["state"] == "unresolved"
    # Another person's key is not theirs to read: the scope is per author.
    _, colleague = stock.inventory.member("manager")
    foreign = await settle(stock, key, reference("document", document), headers=colleague)
    assert foreign.json()["state"] == "unresolved"


async def test_a_cancelled_key_refuses_its_late_command_and_leaves_nothing(stock: Stock) -> None:
    assert (await stock.set_rules()).status_code == 200
    item = (await stock.inventory.item(quantity_scale=0))["item_id"]
    await received(stock, item, "5", "10.00")
    baseline = stock.counts()
    document, key = uuid7(), f"stock-{uuid7()}"
    target = reference("document", document)
    cancelled = await settle(stock, key, target, "cancel")
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["state"] == "cancelled"
    # The command that was thought lost arrives late: it is refused, and nothing changes.
    late = await stock.post(write_off(stock, [{"item_id": item, "quantity": "1"}]), document, key)
    assert error(late) == (422, "IDEMPOTENCY_KEY_REUSED"), late.text
    assert stock.counts() == baseline
    assert (await settle(stock, key, target)).json()["state"] == "cancelled"
    assert (await settle(stock, key, target, "cancel")).json()["state"] == "cancelled"
    # A committed command is never cancelled: cancelling reports it as committed.
    done = f"stock-{uuid7()}"
    posted = uuid7()
    used = await stock.post(write_off(stock, [{"item_id": item, "quantity": "1"}]), posted, done)
    assert used.status_code == 200, used.text
    kept = await settle(stock, done, reference("document", posted), "cancel")
    assert kept.json()["state"] == "committed"
    assert stock.counts()["stock_documents"] == baseline["stock_documents"] + 1


async def test_materials_places_and_rules_resolve_by_their_revision(stock: Stock) -> None:
    item_id, key = uuid7(), f"stock-{uuid7()}"
    body: dict[str, object] = {
        "expected_revision": 0,
        "code": "DYE",
        "name": "FAKE dye",
        "unit": "ml",
        "quantity_scale": 1,
        "archived": False,
    }
    created = await stock.inventory.put(f"/items/{item_id}", body, key)
    assert created.status_code == 200, created.text
    assert (await settle(stock, key, reference("item", item_id, 1))).json()["state"] == "committed"
    wrong = await settle(stock, key, reference("item", item_id, 2))
    assert error(wrong) == (422, "INVALID_REFERENCE"), wrong.text
    renamed_key = f"stock-{uuid7()}"
    renamed = await stock.inventory.put(
        f"/items/{item_id}", {**material_input(created.json()), "name": "FAKE red dye"}, renamed_key
    )
    assert renamed.status_code == 200, renamed.text
    item_state = await settle(stock, renamed_key, reference("item", item_id, 2))
    assert item_state.json()["state"] == "committed"
    place = stock.place
    assert (
        await settle(stock, f"stock-{uuid7()}", reference("place", place["place_id"], 1))
    ).json()["state"] == "unresolved"
    rules_key = f"stock-{uuid7()}"
    rules = await stock.inventory.put(f"/posting-rules/{stock.book}", stock.rules(), rules_key)
    assert rules.status_code == 200, rules.text
    rules_state = await settle(stock, rules_key, reference("posting_rules", stock.book, 1))
    assert rules_state.json()["state"] == "committed"


@pytest.mark.parametrize(
    "body",
    [
        reference("document", uuid7(), 1),
        reference("item", uuid7(), 0),
        reference("anything", uuid7(), 1),
        {**reference("document", uuid7()), "amount": "1.00"},
        {k: v for k, v in reference("document", uuid7()).items() if k != "subject_id"},
    ],
)
async def test_a_reference_names_identifiers_only(stock: Stock, body: dict[str, object]) -> None:
    refused = await settle(stock, f"stock-{uuid7()}", body)
    assert error(refused) == (422, "INVALID_REQUEST"), refused.text
    short = await settle(stock, "short", reference("document", uuid7()))
    assert short.status_code == 422, short.text


async def test_discards_are_limited_and_settling_works_with_the_module_off(stock: Stock) -> None:
    for _ in range(20):
        gone = await settle(stock, f"stock-{uuid7()}", reference("document", uuid7()), "cancel")
        assert gone.json()["state"] == "cancelled", gone.text
    many = await settle(stock, f"stock-{uuid7()}", reference("document", uuid7()), "cancel")
    assert error(many) == (422, "TOO_MANY_DISCARDED_COMMANDS"), many.text
    # Switched off, the module still lets a person find out what became of a command.
    await Config(stock.inventory.client, stock.inventory.idp).publish(
        stock.inventory.manager, stock.tenant, 1, ["booking_resources", "finance"]
    )
    state = await settle(stock, f"stock-{uuid7()}", reference("document", uuid7()))
    assert state.json()["state"] == "unresolved", state.text
