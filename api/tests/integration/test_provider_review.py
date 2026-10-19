"""K4b: why a provider operation needs review, what waits for attention, and acknowledgements.

Synthetic only: events are signed in memory and decided by the receipt worker. No provider
account, real key, network call or real money. An acknowledgement never changes money or a
decision (owner decisions 2026-10-18).
"""

from typing import Any
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking import observability
from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import add_membership, owner_tenant_transaction
from tests.integration import test_provider_payments as shared
from tests.integration import test_provider_receipt_attestations as attested
from tests.integration import test_provider_receipt_decisions as decided
from tests.integration.booking_support import BookingWorld
from tests.integration.configuration_support import Config
from tests.integration.seed import FakeUser, seed_user
from tests.integration.test_provider_payments import Money, event
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
manager_b = shared.manager_b
enabled = shared.enabled
invoices = shared.invoices
payments = shared.payments
credits = shared.credits
inbox = shared.inbox
writer_pool = shared.writer_pool
routed = shared.routed
worker_pool = shared.worker_pool
backend = shared.backend
money = shared.money
NOTE = "FAKE checked with the provider dashboard; no money expected"


async def detail(
    money: Money, operation: UUID, auth: dict[str, str] | None = None
) -> httpx.Response:
    return await money.http.get(
        f"{money.root}/provider-operations/{operation}", headers=auth or money.credits.ledger.auth
    )


async def attention(money: Money, auth: dict[str, str] | None = None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    after: str | None = None
    for _ in range(50):
        params: dict[str, str | int] = {"limit": 1}
        if after is not None:
            params["after"] = after
        response = await money.http.get(
            f"{money.root}/provider-attention",
            params=params,
            headers=auth or money.credits.ledger.auth,
        )
        assert response.status_code == 200, response.text
        page = response.json()
        items.extend(page["items"])
        after = page["next_cursor"]
        if after is None:
            return items
    raise AssertionError("the cursor never ended")


async def acknowledge(
    money: Money, event_id: str, note: object = NOTE, auth: dict[str, str] | None = None
) -> httpx.Response:
    return await money.http.put(
        f"{money.root}/provider-attention/{event_id}/acknowledgement",
        json={"schema_version": 1, "note": note},
        headers=auth or money.credits.ledger.headers(),
    )


# R-01 -----------------------------------------------------------------------


async def test_the_detail_lists_every_event_decision_and_delivery(money: Money) -> None:
    await money.observe(
        event("payment_intent.succeeded"),
        event("charge.succeeded", object_id="ch_FAKEcharge1"),
    )
    response = await detail(money, await money.operation())
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["business_id"], body["book_id"]) == (
        str(money.credits.ledger.business),
        str(money.credits.ledger.book),
    )
    assert body["operation"]["state"] == "observed"
    assert [x["event_type"] for x in body["events"]] == [
        "payment_intent.succeeded",
        "charge.succeeded",
    ]
    for item in body["events"]:
        assert set(item) == {"event_id", "event_type", "created", "decision", "deliveries"}
        assert item["decision"]["outcome"] == "observed"
        assert item["decision"]["reason"] == "success"
        (delivery,) = item["deliveries"]
        assert set(delivery) == {"received_at", "digest", "matches_original", "differences"}
        assert delivery["matches_original"] is True
        assert delivery["differences"] == []
        assert len(delivery["digest"]) == 12


async def test_an_unknown_or_foreign_operation_is_not_found(
    money: Money, manager_b: FakeUser, idp: FakeIdp
) -> None:
    assert (await detail(money, uuid7())).status_code == 404
    await money.observe(event("payment_intent.succeeded"))
    foreign = await detail(money, await money.operation(), Config(money.http, idp).auth(manager_b))
    assert foreign.status_code in (403, 404), foreign.text


# R-02, R-03 -----------------------------------------------------------------


async def test_a_differing_delivery_names_its_fields_and_both_values(money: Money) -> None:
    raw = event("payment_intent.succeeded")
    await money.observe(raw)
    variant = raw.replace(b'"amount_received":1000', b'"amount_received":900')
    assert variant != raw
    received = await attested.receive(money.writer, money.routed, variant)
    assert received.disposition == "conflict"
    response = await detail(money, await money.operation())
    assert response.status_code == 200, response.text
    assert response.json()["operation"]["state"] == "needs_review"
    (item,) = response.json()["events"]
    original, later = item["deliveries"]
    assert (original["matches_original"], original["differences"]) == (True, [])
    assert later["matches_original"] is False
    assert later["differences"] == [
        {"field": "resource.amount_received_minor", "original": "1000", "delivered": "900"}
    ]
    text = response.text
    assert money.routed.secret_ref not in text
    assert str(money.routed.verification_config_id) not in text
    for forbidden in ("whsec_", "signature", "v1="):
        assert forbidden not in text


async def test_conflicting_events_show_their_decisions(money: Money) -> None:
    await money.observe(
        event("payment_intent.succeeded"),
        event("charge.succeeded", object_id="ch_FAKEcharge1", amount=900),
    )
    body = (await detail(money, await money.operation())).json()
    assert body["operation"]["state"] == "needs_review"
    assert [x["decision"]["reason"] for x in body["events"]] == ["success", "conflicting_facts"]
    assert body["events"][1]["decision"]["outcome"] == "needs_review"


# R-04 -----------------------------------------------------------------------


async def test_attention_lists_undecided_events_and_decisions_without_an_operation(
    money: Money,
) -> None:
    await money.observe(
        event("payment_intent.succeeded"),
        event("charge.succeeded", object_id="ch_FAKEnopayment", payment_intent=None),
        event(
            "refund.updated",
            object_id="re_FAKEorphan1",
            amount=500,
            payment_intent=None,
        ),
    )
    # Attested and never decided: the worker has not run since.
    waiting = await decided.receive_all(
        money.writer,
        money.routed,
        event("payment_intent.succeeded", object_id="pi_FAKEwaiting1"),
    )
    items = await attention(money)
    kinds = sorted((x["kind"], x["reason"] or "", x["event_type"]) for x in items)
    assert kinds == [
        ("no_operation", "refund_without_payment", "refund.updated"),
        ("no_operation", "unkeyed_operation", "charge.succeeded"),
        ("undecided", "", "payment_intent.succeeded"),
    ]
    assert [x["event_id"] for x in items if x["kind"] == "undecided"] == [str(waiting[0])]
    assert sorted(x["object_id"] for x in items) == [
        "ch_FAKEnopayment",
        "pi_FAKEwaiting1",
        "re_FAKEorphan1",
    ]
    assert all(x["acknowledgement"] is None for x in items)
    for item in items:
        assert set(item) == {
            "event_id",
            "connection_id",
            "kind",
            "event_type",
            "object_id",
            "created",
            "reason",
            "acknowledgement",
        }


# R-05 -----------------------------------------------------------------------


async def test_an_acknowledgement_needs_a_note_and_is_given_once(
    money: Money, app_pool: RuntimePool
) -> None:
    await money.observe(
        event("charge.succeeded", object_id="ch_FAKEnopayment", payment_intent=None)
    )
    (item,) = await attention(money)
    for note in ("", "   ", "FAKE\x00note", "x" * 501, 7):
        refused = await acknowledge(money, item["event_id"], note)
        assert refused.status_code == 422, (note, refused.text)
    journals = await money.count(app_pool, "journal_entries")
    given = await acknowledge(money, item["event_id"])
    assert given.status_code == 200, given.text
    result = given.json()
    assert result["item"]["acknowledgement"]["note"] == NOTE
    assert result["item"]["acknowledgement"]["acknowledged_by"] == str(
        money.credits.ledger.user.user_id
    )
    again = await acknowledge(money, item["event_id"])
    assert again.status_code == 200, again.text
    assert again.json() == result
    other = await acknowledge(money, item["event_id"], "FAKE a different note")
    assert other.status_code == 409, other.text
    assert other.json()["error"]["code"] == "PROVIDER_ATTENTION_ACKNOWLEDGED"
    (listed,) = await attention(money)
    assert listed["acknowledgement"] == result["item"]["acknowledgement"]
    assert listed["reason"] == "unkeyed_operation"
    assert await money.count(app_pool, "journal_entries") == journals
    assert await money.count(app_pool, "external_payments") == 0


async def test_an_event_of_an_operation_is_not_acknowledged(money: Money) -> None:
    raws = await money.observe(event("payment_intent.succeeded"))
    refused = await acknowledge(money, str(raws[0]))
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "PROVIDER_ATTENTION_NOT_NEEDED"
    assert (await acknowledge(money, str(uuid7()))).status_code == 404


async def test_sql_cannot_change_or_forge_an_acknowledgement(
    money: Money, app_pool: RuntimePool, owner_conn: psycopg.Connection
) -> None:
    raws = await money.observe(
        event("charge.succeeded", object_id="ch_FAKEnopayment", payment_intent=None),
        event("payment_intent.succeeded"),
    )
    assert (await acknowledge(money, str(raws[0]))).status_code == 200
    business = money.credits.ledger.business
    user = money.credits.ledger.user.user_id
    for statement in (
        "update gba.provider_event_acknowledgements set note='FAKE rewritten'",
        "delete from gba.provider_event_acknowledgements",
    ):
        with pytest.raises(psycopg.errors.Error):
            async with tenant_transaction(app_pool, business) as conn:
                await conn.execute(statement)
    with pytest.raises(psycopg.errors.Error):
        async with tenant_transaction(app_pool, business) as conn:
            # An event of an operation needs no acknowledgement: the database refuses it too.
            await conn.execute(
                "insert into gba.provider_event_acknowledgements (tenant_id,event_id,note,"
                "created_by) values (%s,%s,'FAKE forged',%s)",
                (business, raws[1], user),
            )
    with pytest.raises(psycopg.errors.Error), owner_tenant_transaction(owner_conn, business):
        owner_conn.execute("truncate gba.provider_event_acknowledgements")
    async with tenant_transaction(app_pool, business) as conn:
        rows = await (
            await conn.execute("select note from gba.provider_event_acknowledgements")
        ).fetchall()
    assert [r[0] for r in rows] == [NOTE]


# R-07 -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("role", "branch", "expected"),
    [
        ("owner", False, 200),
        ("front_desk", False, 403),
        ("artist", False, 403),
        ("manager", True, 403),
    ],
)
async def test_review_routes_keep_company_finance_permissions(
    money: Money,
    owner_conn: psycopg.Connection,
    world: BookingWorld,
    idp: FakeIdp,
    role: str,
    branch: bool,
    expected: int,
) -> None:
    raws = await money.observe(
        event("payment_intent.succeeded"),
        event("charge.succeeded", object_id="ch_FAKEnopayment", payment_intent=None),
    )
    member = seed_user(owner_conn, f"FAKE-K4b-{role}-{uuid7()}")
    add_membership(
        owner_conn,
        tenant_id=money.credits.ledger.business,
        user_id=member.user_id,
        role=role,
        location_id=world.a.location_id if branch else None,
    )
    auth = idp.bearer(member.subject, email=member.email)
    assert (await detail(money, await money.operation(), auth)).status_code == expected
    listed = await money.http.get(f"{money.root}/provider-attention", headers=auth)
    assert listed.status_code == expected, listed.text
    given = await acknowledge(money, str(raws[1]), auth=auth)
    assert given.status_code == expected, given.text


async def test_another_company_cannot_read_or_acknowledge(
    money: Money, manager_b: FakeUser, idp: FakeIdp
) -> None:
    raws = await money.observe(
        event("charge.succeeded", object_id="ch_FAKEnopayment", payment_intent=None)
    )
    config = Config(money.http, idp)
    listed = await money.http.get(
        f"{money.root}/provider-attention", headers=config.auth(manager_b)
    )
    assert listed.status_code in (403, 404), listed.text
    refused = await acknowledge(money, str(raws[0]), auth=config.headers(manager_b))
    assert refused.status_code in (403, 404), refused.text


# R-06 -----------------------------------------------------------------------


class Recorder:
    def __init__(self) -> None:
        self.points: list[tuple[int, dict[str, str]]] = []

    def add(self, amount: int, attributes: dict[str, str]) -> None:
        self.points.append((amount, dict(attributes)))


async def test_decisions_and_applications_are_counted_with_the_company(
    money: Money, monkeypatch: pytest.MonkeyPatch
) -> None:
    decisions, applications = Recorder(), Recorder()
    monkeypatch.setattr(observability, "_provider_decisions", decisions)
    monkeypatch.setattr(observability, "_provider_applications", applications)
    obligation, settlement = await money.reserved()
    await money.observe(
        event("payment_intent.succeeded"),
        event("charge.succeeded", object_id="ch_FAKEnopayment", payment_intent=None),
    )
    tenant = str(money.routed.tenant_id)
    assert sorted((a, p["outcome"], p["reason"], p["tenant_id"]) for a, p in decisions.points) == [
        (1, "needs_review", "unkeyed_operation", tenant),
        (1, "observed", "success", tenant),
    ]
    operation = await money.operation()
    assert (await money.apply(settlement, operation, [(obligation, "10.00")])).status_code == 200
    # Another reserved settlement: the operation already moved money, so it is refused.
    second, other = await money.reserved()
    repeated = await money.apply(other, operation, [(second, "10.00")])
    assert repeated.status_code == 409, repeated.text
    assert applications.points == [
        (1, {"result": "applied", "tenant_id": tenant}),
        (1, {"result": "PROVIDER_OPERATION_APPLIED", "tenant_id": tenant}),
    ]
    for _, attributes in decisions.points + applications.points:
        assert set(attributes) <= {"outcome", "reason", "result", "tenant_id"}


# Guard ----------------------------------------------------------------------

_DRIFT = [
    (
        "alter table gba.provider_event_acknowledgements "
        "disable trigger provider_event_acknowledgements_check",
        "alter table gba.provider_event_acknowledgements "
        "enable trigger provider_event_acknowledgements_check",
    ),
    (
        "grant update (note) on gba.provider_event_acknowledgements to gba_runtime",
        "revoke update (note) on gba.provider_event_acknowledgements from gba_runtime",
    ),
    (
        "alter policy provider_event_acknowledgements_company "
        "on gba.provider_event_acknowledgements using (true) with check (true)",
        "alter policy provider_event_acknowledgements_company "
        "on gba.provider_event_acknowledgements using (gba.current_location_id() is null) "
        "with check (gba.current_location_id() is null)",
    ),
]


@pytest.mark.parametrize(("change", "restore"), _DRIFT, ids=["trigger", "grant", "policy"])
async def test_damaged_acknowledgement_controls_fail_with_503(
    money: Money, owner_conn: psycopg.Connection, change: str, restore: str
) -> None:
    raws = await money.observe(
        event("charge.succeeded", object_id="ch_FAKEnopayment", payment_intent=None)
    )
    owner_conn.execute(change)
    try:
        refused = await acknowledge(money, str(raws[0]))
        assert refused.status_code == 503, refused.text
        listed = await money.http.get(
            f"{money.root}/provider-attention", headers=money.credits.ledger.auth
        )
        assert listed.status_code == 503, listed.text
    finally:
        owner_conn.execute(restore)
    assert (await acknowledge(money, str(raws[0]))).status_code == 200
