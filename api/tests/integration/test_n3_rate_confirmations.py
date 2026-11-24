"""N3: rate confirmations of accepted tenders (package N; FAKE data only).

docs/plan/PACKAGE_N3_DESIGN_2026-10-27.md: accepting a tender writes version 1 with the tender's
rate and terms; a change is a new version that is in force only once the carrier agrees;
nothing is edited.
"""

from typing import Any
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from tests.integration import test_management_api as shared
from tests.integration.configuration_support import Config
from tests.integration.seed import FakeUser
from tests.integration.test_delegations import owner_a, owner_b, parties
from tests.integration.test_m1_transport_planning import Transport, accepted, error, transport
from tests.integration.test_n1_broker_carriers import carrier, profile
from tests.integration.test_n2_tenders import _broker, _trip, answer, offer
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
manager_b = shared.manager_b
__all__ = [
    "accepted",
    "client",
    "idp",
    "manager_a",
    "manager_b",
    "owner_a",
    "owner_b",
    "parties",
    "transport",
]


def proposal(revision: int, **changes: Any) -> dict[str, Any]:
    return {
        "expected_revision": revision,
        "basis": "fixed",
        "amount": "1100.00",
        "terms": "FAKE terms: detention after 1 hour",
        "document_id": None,
        "proposed_at": "2026-10-26T21:00:00+00:00",
        **changes,
    }


async def agree(
    t: Transport, tender: UUID, revision: int, kind: str = "agreed", **changes: Any
) -> httpx.Response:
    return await t.client.post(
        f"{t.base}/tenders/{tender}/rate-confirmation/{revision}/answers",
        json={
            "schema_version": 1,
            "kind": kind,
            "source": "email",
            "occurred_at": "2026-10-26T22:00:00+00:00",
            **changes,
        },
        headers={**t.headers, "Idempotency-Key": str(uuid7())},
    )


async def accepted_tender(t: Transport) -> UUID:
    trip = await _trip(t)
    party = await _broker(t)
    tender = uuid7()
    assert (await t.put(f"/tenders/{tender}", offer(trip, party, [1]))).status_code == 200
    took = await answer(t, tender, "accepted")
    assert took.status_code == 200, took.text
    return tender


# N3-01 ------------------------------------------------------------------------------


async def test_accepting_a_tender_writes_version_one(transport: Transport) -> None:
    t = transport
    tender = await accepted_tender(t)
    seen = await t.get(f"/tenders/{tender}/rate-confirmation")
    assert seen.status_code == 200, seen.text
    body = seen.json()
    assert body["in_force"]["revision"] == 1
    first = body["versions"][0]
    assert (first["revision"], first["basis"], first["amount"], first["state"]) == (
        1,
        "fixed",
        "900.00",
        "agreed",
    )
    assert first["terms"].startswith("FAKE terms: pickup on time")
    assert first["answer"]["source"] == "email"
    trip = await _trip(t)
    party = await carrier(t, "FAKE Second Carrier")
    assert (await t.put(f"/carriers/{party}/profile", profile(0))).status_code == 200
    declined = uuid7()
    assert (await t.put(f"/tenders/{declined}", offer(trip, party, [1]))).status_code == 200
    assert (await answer(t, declined, "declined")).status_code == 200
    assert (await t.get(f"/tenders/{declined}/rate-confirmation")).status_code == 404


# N3-02 ------------------------------------------------------------------------------


async def test_a_change_is_in_force_only_once_the_carrier_agrees(transport: Transport) -> None:
    t = transport
    tender = await accepted_tender(t)
    path = f"/tenders/{tender}/rate-confirmation"
    proposed = await t.put(path, proposal(1))
    assert proposed.status_code == 200, proposed.text
    body = proposed.json()
    assert body["in_force"]["revision"] == 1
    assert [(v["revision"], v["state"]) for v in body["versions"]] == [
        (1, "agreed"),
        (2, "proposed"),
    ]
    agreed = await agree(t, tender, 2)
    assert agreed.status_code == 200, agreed.text
    assert agreed.json()["in_force"]["amount"] == "1100.00"
    third = await t.put(
        path, proposal(2, amount="1500.00", proposed_at="2026-10-26T22:30:00+00:00")
    )
    assert third.status_code == 200, third.text
    refused = await agree(t, tender, 3, "declined", occurred_at="2026-10-26T23:00:00+00:00")
    assert refused.status_code == 200, refused.text
    view = refused.json()
    assert (view["in_force"]["revision"], view["in_force"]["amount"]) == (2, "1100.00")
    assert [v["state"] for v in view["versions"]] == ["agreed", "agreed", "declined"]
    assert [v["amount"] for v in view["versions"]] == ["900.00", "1100.00", "1500.00"]


# N3-03 ------------------------------------------------------------------------------


async def test_stale_open_closed_and_bad_changes_are_refused(transport: Transport) -> None:
    t = transport
    tender = await accepted_tender(t)
    path = f"/tenders/{tender}/rate-confirmation"
    stale = await t.put(path, proposal(0))
    assert error(stale) == (409, "TRANSPORT_RATE_CONFIRMATION_CONFLICT"), stale.text
    fine = await t.put(path, proposal(1, amount="1100.005"))
    assert fine.status_code == 422, fine.text
    before_acceptance = await t.put(path, proposal(1, proposed_at="2026-10-26T10:00:00+00:00"))
    assert before_acceptance.status_code == 422, before_acceptance.text
    assert (await t.put(path, proposal(1))).status_code == 200
    second = await t.put(path, proposal(2, amount="1200.00"))
    assert error(second) == (409, "TRANSPORT_RATE_CONFIRMATION_CONFLICT"), second.text
    early = await agree(t, tender, 2, occurred_at="2026-10-26T20:00:00+00:00")
    assert early.status_code == 422, early.text
    older = await agree(t, tender, 1)
    assert error(older) == (409, "TRANSPORT_RATE_CONFIRMATION_CONFLICT"), older.text
    assert (await agree(t, tender, 2)).status_code == 200
    again = await agree(t, tender, 2, "declined")
    assert error(again) == (409, "TRANSPORT_RATE_CONFIRMATION_CONFLICT"), again.text
    assert (await agree(t, tender, 7)).status_code == 404
    back = await answer(t, tender, "withdrawn", "2026-10-26T23:00:00+00:00")
    assert back.status_code == 200, back.text
    closed = await t.put(path, proposal(2, proposed_at="2026-10-26T23:30:00+00:00"))
    assert error(closed) == (409, "TRANSPORT_TENDER_CLOSED"), closed.text
    assert (await t.put(f"/tenders/{uuid7()}/rate-confirmation", proposal(1))).status_code == 404


# N3-04 ------------------------------------------------------------------------------


async def test_a_signed_copy_must_be_a_document_of_this_business(transport: Transport) -> None:
    t = transport
    tender = await accepted_tender(t)
    path = f"/tenders/{tender}/rate-confirmation"
    # The reference is (business, document): an id the business does not hold is refused, which is
    # what another business's document is from here. A signed copy of the business's own document
    # needs the documents module and is not exercised here (recorded in the N3 validation).
    unknown = await t.put(path, proposal(1, document_id=str(uuid7())))
    assert unknown.status_code == 422, unknown.text
    assert (await t.get(path)).json()["versions"][-1]["revision"] == 1


# N3-05 ------------------------------------------------------------------------------


async def _rows(pool: RuntimePool, tenant: UUID) -> tuple[int, int]:
    async with tenant_transaction(pool, tenant) as conn:
        a = await (
            await conn.execute("select count(*) from gba.transport_rate_confirmations")
        ).fetchone()
        b = await (
            await conn.execute("select count(*) from gba.transport_rate_confirmation_answers")
        ).fetchone()
    assert a is not None
    assert b is not None
    return int(a[0]), int(b[0])


async def test_only_brokers_read_or_change_rate_confirmations(
    transport: Transport,
    app_pool: RuntimePool,
    idp: FakeIdp,
    manager_a: FakeUser,
    manager_b: FakeUser,
) -> None:
    t = transport
    tender = await accepted_tender(t)
    path = f"/tenders/{tender}/rate-confirmation"
    before = await _rows(app_pool, t.tenant)
    other = idp.bearer(manager_b.subject, email=manager_b.email)
    assert (await t.get(path, other)).status_code in (403, 404)
    assert (await t.put(path, proposal(1), other)).status_code in (403, 404)
    assert await _rows(app_pool, t.tenant) == before
    for statement in (
        "update gba.transport_rate_confirmations set amount = 1",
        "delete from gba.transport_rate_confirmation_answers",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with tenant_transaction(app_pool, t.tenant) as conn:
                await conn.execute(statement)
    await Config(t.client, idp).publish(
        manager_a, t.tenant, 1, ["booking_resources", "counterparties"]
    )
    off = await t.put(path, proposal(1))
    assert off.status_code in (403, 409), off.text
    assert await _rows(app_pool, t.tenant) == before
