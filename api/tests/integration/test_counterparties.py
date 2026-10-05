"""Company-wide counterparty behavior against real disposable PostgreSQL."""

import asyncio
from collections.abc import AsyncIterator, Mapping
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
from tests.integration.module_support import verified_modules
from tests.integration.seed import FakeUser, seed_user
from tests.integration.test_delegations import Parties
from tests.integration.test_groups import Groups
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
manager_b = shared.manager_b


def card(**changes: object) -> dict[str, object]:
    return {
        "schema_version": 1,
        "expected_revision": 0,
        "kind": "person",
        "display_name": "FAKE Counterparty",
        "roles": ["customer", "supplier"],
        "email": "fake.counterparty@example.test",
        "phone": "+1 555 010 1234",
        "contacts": [],
        "archived": False,
        **changes,
    }


class Counterparties:
    def __init__(
        self, client: httpx.AsyncClient, world: BookingWorld, user: FakeUser, idp: FakeIdp
    ) -> None:
        self.client = client
        self.business = world.a.tenant_id
        self.user = user
        self.auth = idp.bearer(user.subject, email=user.email)
        self.base = f"/v1/businesses/{self.business}/counterparties"
        self.config = Config(client, idp)

    async def save(
        self, subject: UUID, body: dict[str, object], key: str | None = None
    ) -> httpx.Response:
        return await self.client.put(
            f"{self.base}/{subject}",
            json=body,
            headers={**self.auth, "Idempotency-Key": key or str(uuid7())},
        )

    async def create(self, **changes: object) -> dict[str, object]:
        result = await self.save(uuid7(), card(**changes))
        assert result.status_code == 200, result.text
        data: dict[str, object] = result.json()
        return data

    async def get(self, suffix: str = "", **params: str | int) -> httpx.Response:
        return await self.client.get(f"{self.base}{suffix}", headers=self.auth, params=params)

    async def command(
        self, subject: UUID | str, suffix: str, body: Mapping[str, object], key: str | None = None
    ) -> httpx.Response:
        return await self.client.post(
            f"{self.base}/{subject}/{suffix}",
            json=body,
            headers={**self.auth, "Idempotency-Key": key or str(uuid7())},
        )


@pytest.fixture
async def enabled(
    client: httpx.AsyncClient, world: BookingWorld, manager_a: FakeUser, idp: FakeIdp
) -> AsyncIterator[Counterparties]:
    cp = Counterparties(client, world, manager_a, idp)
    with verified_modules("counterparties"):
        await cp.config.profile(manager_a, cp.business, 0, [1, 6, 24])
        await cp.config.publish(manager_a, cp.business, 0, ["booking_resources", "counterparties"])
        yield cp


async def test_unverified_counterparties_cannot_be_published_without_a_registry_override(
    client: httpx.AsyncClient, world: BookingWorld, manager_a: FakeUser, idp: FakeIdp
) -> None:
    cp = Counterparties(client, world, manager_a, idp)
    await cp.config.profile(manager_a, cp.business, 0, [1, 24])
    drafted = await cp.config.draft(manager_a, cp.business, 0, ["counterparties"])
    assert drafted.status_code == 200, drafted.text
    validated = await cp.config.step(manager_a, cp.business, 1, "validate", 1)
    assert validated.status_code == 422, validated.text
    error = validated.json()["error"]
    assert error["code"] == "CONFIGURATION_INVALID"
    assert {(p["code"], p["module_id"]) for p in error["details"]["problems"]} == {
        ("MODULE_NOT_READY", "counterparties")
    }
    assert (await cp.config.get(manager_a, cp.business, "/versions/1")).json()["state"] == "draft"
    refused = await cp.config.step(manager_a, cp.business, 1, "publish", 1)
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"]["code"] == "CONFIGURATION_STATE_INVALID"
    assert (await cp.save(uuid7(), card())).json()["error"]["code"] == "MODULE_DISABLED"


async def test_cards_keep_immutable_versions_and_reference_only_receipts(
    enabled: Counterparties, app_pool: RuntimePool
) -> None:
    subject, key = uuid7(), str(uuid7())
    original = card(
        kind="organization",
        contacts=[
            {"name": "FAKE Contact", "email": " CONTACT@EXAMPLE.TEST ", "phone": "+15550105678"}
        ],
        email=" FAKE.COUNTERPARTY@EXAMPLE.TEST ",
    )
    first = await enabled.save(subject, original, key)
    assert first.status_code == 200, first.text
    assert first.json()["contacts"][0]["email"] == "contact@example.test"
    changed = await enabled.save(
        subject, card(kind="organization", expected_revision=1, display_name="FAKE Updated")
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["revision"] == 2
    assert (await enabled.save(subject, original, key)).json() == first.json()
    assert (await enabled.get(f"/{subject}", revision=1)).json() == first.json()
    conflict = await enabled.save(subject, original)
    assert conflict.status_code == 409
    assert (await enabled.save(uuid7(), original, key)).status_code == 422
    identity_change = await enabled.save(subject, card(expected_revision=2, kind="person"))
    assert identity_change.status_code == 422
    history = (await enabled.get(f"/{subject}/versions", limit=1)).json()
    assert [row["revision"] for row in history["items"]] == [2]
    assert history["next_cursor"] == 2
    assert [
        row["revision"]
        for row in (await enabled.get(f"/{subject}/versions", before=2)).json()["items"]
    ] == [1]
    async with tenant_transaction(app_pool, enabled.business) as conn:
        assert (
            await (await conn.execute("select count(*) from gba.counterparties")).fetchone()
        ) == (1,)
        audits = await (
            await conn.execute(
                "select details from gba.audit_events where action = 'counterparty.saved'"
            )
        ).fetchall()
        assert len(audits) == 2
        assert "example.test" not in str(audits)
        assert "FAKE Contact" not in str(audits)
        receipts = await (
            await conn.execute(
                "select response_body from gba.idempotency_keys "
                "where operation = 'business.counterparty.save'"
            )
        ).fetchall()
        assert all(set(row[0]) == {"counterparty_id", "revision"} for row in receipts)


async def test_merge_separation_and_replays_never_change_saved_responses(
    enabled: Counterparties,
) -> None:
    source, target = await enabled.create(), await enabled.create(display_name="FAKE Target")
    a, b = str(source["counterparty_id"]), str(target["counterparty_id"])
    save_key, merge_key = str(uuid7()), str(uuid7())
    saved = await enabled.save(
        UUID(b), card(expected_revision=1, display_name="FAKE Target"), save_key
    )
    body = {"decision": "merge", "into_id": b, "expected_revision": 1, "into_expected_revision": 2}
    merged = await enabled.command(a, "match-decisions", body, merge_key)
    assert merged.status_code == 200, merged.text
    assert merged.json()["counterparty_revision"] == 2
    assert (
        await enabled.save(UUID(b), card(expected_revision=1, display_name="FAKE Target"), save_key)
    ).json() == saved.json()
    assert (await enabled.get(f"/{b}", revision=2)).json() == saved.json()
    assert [
        item["counterparty_id"] for item in (await enabled.get(f"/{b}/merged-from")).json()["items"]
    ] == [a]
    assert (await enabled.get(f"/{a}")).json()["state"] == "merged"
    assert (await enabled.save(UUID(a), card(expected_revision=2))).status_code == 409
    third = await enabled.create(display_name="FAKE Third")
    chain = await enabled.command(
        b,
        "match-decisions",
        {
            "decision": "merge",
            "into_id": third["counterparty_id"],
            "expected_revision": 2,
            "into_expected_revision": 1,
        },
    )
    assert chain.status_code == 409
    separated = await enabled.command(
        a,
        "match-decisions",
        {
            "decision": "separate",
            "decision_id": merged.json()["decision_id"],
            "expected_revision": 2,
        },
    )
    assert separated.status_code == 200, separated.text
    assert separated.json()["counterparty_revision"] == 3
    assert (await enabled.get(f"/{a}")).json()["state"] == "active"
    assert (await enabled.get(f"/{b}/merged-from")).json()["items"] == []
    assert (await enabled.command(a, "match-decisions", body, merge_key)).json() == merged.json()
    decisions = (await enabled.get(f"/{a}/match-decisions")).json()["items"]
    assert [(item["kind"], item["counterparty_revision"]) for item in decisions] == [
        ("separated", 3),
        ("merged", 2),
    ]
    assert decisions[1]["reversed"] is True


async def test_matches_are_suggestions_and_distinct_is_pair_symmetric(
    enabled: Counterparties,
) -> None:
    first = await enabled.create(display_name="FAKE Common Name")
    strong = await enabled.create(display_name="FAKE Other", phone="(1555) 010-1234")
    weak = await enabled.create(display_name="  FAKE  Common Name  ", phone=None, email=None)
    a, b, c = (str(row["counterparty_id"]) for row in (first, strong, weak))
    duplicates = (await enabled.get(f"/{a}/duplicates")).json()["items"]
    assert {row["counterparty_id"]: row["strength"] for row in duplicates} == {
        b: "strong",
        c: "weak",
    }
    assert (await enabled.get()).json()["items"][0]["state"] == "active"
    decision = await enabled.command(a, "match-decisions", {"decision": "distinct", "other_id": b})
    assert decision.status_code == 200, decision.text
    reverse = await enabled.command(b, "match-decisions", {"decision": "distinct", "other_id": a})
    assert reverse.status_code == 409
    assert [
        row["counterparty_id"] for row in (await enabled.get(f"/{a}/duplicates")).json()["items"]
    ] == [c]
    probe = await enabled.client.post(
        f"{enabled.base}/match-check",
        json={"emails": [" FAKE.COUNTERPARTY@EXAMPLE.TEST "]},
        headers=enabled.auth,
    )
    assert probe.status_code == 200
    assert {row["counterparty_id"] for row in probe.json()["items"]} == {a, b}


async def test_concurrent_edit_and_identical_retries_have_one_version(
    enabled: Counterparties,
) -> None:
    subject = uuid7()
    results = await asyncio.gather(*(enabled.save(subject, card()) for _ in range(2)))
    assert sorted(response.status_code for response in results) == [200, 409]
    key = str(uuid7())
    results = await asyncio.gather(
        *(enabled.save(subject, card(expected_revision=1), key) for _ in range(2))
    )
    assert [response.status_code for response in results] == [200, 200]
    assert results[0].json() == results[1].json()
    assert results[0].json()["revision"] == 2


async def test_competing_merges_and_booking_links_have_one_winner(
    enabled: Counterparties, world: BookingWorld
) -> None:
    a, b = [str((await enabled.create())["counterparty_id"]) for _ in range(2)]
    mergers = await asyncio.gather(
        *(
            enabled.command(
                source,
                "match-decisions",
                {
                    "decision": "merge",
                    "into_id": target,
                    "expected_revision": 1,
                    "into_expected_revision": 1,
                },
            )
            for source, target in [(a, b), (b, a)]
        )
    )
    assert sorted(r.status_code for r in mergers) == [200, 409]
    c, d = [str((await enabled.create())["counterparty_id"]) for _ in range(2)]
    booking = await confirmed_booking(
        enabled, world, 11, "fake.counterparty@example.test", "+15550101234"
    )
    body = {"action": "link", "booking_ids": [booking]}
    linked = await asyncio.gather(
        *(enabled.command(subject, "booking-links", body) for subject in [c, d])
    )
    assert sorted(r.status_code for r in linked) == [200, 409]


async def test_disabling_publication_and_new_card_writes_are_ordered(
    enabled: Counterparties, app_pool: RuntimePool
) -> None:
    subjects = [uuid7() for _ in range(5)]
    results = await asyncio.gather(
        enabled.config.publish(enabled.user, enabled.business, 1, ["booking_resources"]),
        *(enabled.save(subject, card()) for subject in subjects),
    )
    writes = results[1:]
    assert all(isinstance(r, httpx.Response) for r in writes)
    created = [
        r.json()["counterparty_id"]
        for r in writes
        if isinstance(r, httpx.Response) and r.status_code == 200
    ]
    refused = [
        r.json()["error"]["code"]
        for r in writes
        if isinstance(r, httpx.Response) and r.status_code != 200
    ]
    assert set(refused) <= {"MODULE_DISABLED"}
    async with tenant_transaction(app_pool, enabled.business) as conn:
        assert (
            await (await conn.execute("select count(*) from gba.counterparties")).fetchone()
        ) == (len(created),)
        with pytest.raises(psycopg.Error, match="module is disabled"):
            async with conn.transaction():
                await conn.execute(
                    "insert into gba.counterparties (tenant_id, id, kind, created_by) "
                    "values (%s, %s, 'person', %s)",
                    (enabled.business, uuid7(), enabled.user.user_id),
                )
    assert (await enabled.save(uuid7(), card())).json()["error"]["code"] == "MODULE_DISABLED"


async def test_active_delegation_does_not_admit_counterparty_reads_or_commands(
    enabled: Counterparties, world: BookingWorld, owner_conn: psycopg.Connection, idp: FakeIdp
) -> None:
    owners = [seed_user(owner_conn, f"FAKE-cp-grant-owner-{uuid7()}") for _ in range(2)]
    for salon, user in zip((world.a, world.b), owners, strict=True):
        add_membership(owner_conn, tenant_id=salon.tenant_id, user_id=user.user_id, role="owner")
    parties = Parties(enabled.client, idp, world)
    await parties.active_grant(owners[0], owners[1], [owners[1]])
    auth = idp.bearer(owners[1].subject, email=owners[1].email)
    subject = str((await enabled.create())["counterparty_id"])
    for suffix in [
        "",
        f"/{subject}",
        *[
            f"/{subject}/{s}"
            for s in [
                "versions",
                "merged-from",
                "duplicates",
                "match-decisions",
                "booking-candidates",
                "bookings",
                "booking-links",
            ]
        ],
    ]:
        result = await enabled.client.get(enabled.base + suffix, headers=auth)
        assert result.status_code == 403
    write = await enabled.client.put(
        f"{enabled.base}/{subject}",
        json=card(expected_revision=1),
        headers={**auth, "Idempotency-Key": str(uuid7())},
    )
    assert write.status_code == 403


async def test_group_consent_does_not_share_counterparty_rows(
    enabled: Counterparties, world: BookingWorld, owner_conn: psycopg.Connection, idp: FakeIdp
) -> None:
    owner_b = seed_user(owner_conn, f"FAKE-cp-group-owner-{uuid7()}")
    add_membership(owner_conn, tenant_id=world.b.tenant_id, user_id=owner_b.user_id, role="owner")
    groups = Groups(enabled.client, idp)
    group = uuid7()
    assert (await groups.create(enabled.user, enabled.business, group)).status_code == 200
    assert (
        await groups.invite(enabled.user, enabled.business, group, world.b.tenant_id)
    ).status_code == 200
    assert (await groups.decide(owner_b, world.b.tenant_id, group, "accept", 1)).status_code == 200
    subject = str((await enabled.create())["counterparty_id"])
    foreign = await enabled.client.get(
        f"{enabled.base}/{subject}", headers=idp.bearer(owner_b.subject, email=owner_b.email)
    )
    assert foreign.status_code == 403
    own = await enabled.client.get(
        f"/v1/businesses/{world.b.tenant_id}/counterparties",
        headers=idp.bearer(owner_b.subject, email=owner_b.email),
    )
    assert own.status_code == 200
    assert own.json()["items"] == []


async def test_search_escapes_wildcards_and_paginates_without_duplicate_identities(
    enabled: Counterparties,
) -> None:
    await enabled.create(display_name="FAKE 100% Partner")
    await enabled.create(display_name="FAKE Alpha")
    await enabled.create(display_name="FAKE Beta")
    assert [r["display_name"] for r in (await enabled.get(q="%")).json()["items"]] == [
        "FAKE 100% Partner"
    ]
    first = (await enabled.get(limit=1)).json()
    next_page = (await enabled.get(limit=2, after=first["next_cursor"])).json()
    assert len({r["counterparty_id"] for r in first["items"] + next_page["items"]}) == 3
    assert next_page["next_cursor"] is None


async def test_module_disable_keeps_history_and_replays_but_stops_all_new_writes(
    enabled: Counterparties,
) -> None:
    a, b, key = uuid7(), uuid7(), str(uuid7())
    first = await enabled.save(a, card(), key)
    assert first.status_code == 200, first.text
    assert (await enabled.save(b, card())).status_code == 200
    await enabled.config.publish(enabled.user, enabled.business, 1, ["booking_resources"])
    assert (await enabled.get(f"/{a}")).json() == first.json()
    assert (await enabled.save(a, card(), key)).json() == first.json()
    attempts = [
        await enabled.save(uuid7(), card()),
        await enabled.save(a, card(expected_revision=1)),
        await enabled.command(a, "match-decisions", {"decision": "distinct", "other_id": str(b)}),
        await enabled.command(
            a, "booking-links", {"action": "link", "booking_ids": [str(uuid7())]}
        ),
    ]
    assert [(r.status_code, r.json()["error"]["code"]) for r in attempts] == [
        (409, "MODULE_DISABLED")
    ] * 4


async def test_isolation_revoked_replay_and_branch_sql_visibility(
    enabled: Counterparties,
    world: BookingWorld,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
) -> None:
    subject, key = uuid7(), str(uuid7())
    assert (await enabled.save(subject, card(), key)).status_code == 200
    assert (await enabled.get(f"/{uuid7()}")).status_code == 404
    async with unscoped_transaction(app_pool) as conn:
        assert (await (await conn.execute("select * from gba.counterparties")).fetchall()) == []
    async with tenant_transaction(app_pool, world.b.tenant_id) as conn:
        assert (
            await (await conn.execute("select * from gba.counterparty_versions")).fetchall()
        ) == []
    async with tenant_transaction(app_pool, enabled.business) as conn:
        await conn.execute(
            "select pg_catalog.set_config('gba.location_id', %s, true)", (str(world.a.location_id),)
        )
        assert (
            await (await conn.execute("select * from gba.counterparty_versions")).fetchall()
        ) == []
    with owner_tenant_transaction(owner_conn, enabled.business):
        owner_conn.execute(
            "update gba.memberships set status = 'revoked' where user_id = %s",
            (enabled.user.user_id,),
        )
    assert (await enabled.save(subject, card(), key)).status_code == 403


async def confirmed_booking(
    enabled: Counterparties, world: BookingWorld, hour: int, email: str, phone: str
) -> str:
    starts = datetime.fromisoformat(f"{customer_day()}T{hour:02d}:00:00").replace(
        tzinfo=ZoneInfo("America/New_York")
    )
    response = await enabled.client.post(
        f"/v1/salons/{enabled.business}/bookings",
        headers=enabled.auth,
        json={
            "location_id": str(world.a.location_id),
            "resource_id": str(world.artist_a1),
            "variant_id": str(world.catalog_a.base_variant_id),
            "starts_at": starts.isoformat(),
            "customer_name": "FAKE Counterparty Guest",
            "customer_email": email,
            "customer_phone": phone,
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["booking_id"])


async def test_manual_booking_links_aggregate_after_merge_and_undo_without_moving_data(
    enabled: Counterparties, world: BookingWorld, owner_conn: psycopg.Connection
) -> None:
    a = str((await enabled.create())["counterparty_id"])
    b = str((await enabled.create(display_name="FAKE Survivor"))["counterparty_id"])
    booking = await confirmed_booking(
        enabled, world, 11, "FAKE.COUNTERPARTY@example.test", "+15550101234"
    )
    before = None
    with owner_tenant_transaction(owner_conn, enabled.business):
        before = owner_conn.execute(
            "select * from gba.booking_customers where booking_id = %s", (booking,)
        ).fetchone()
    candidates = (await enabled.get(f"/{a}/booking-candidates")).json()["items"]
    assert [(row["booking"]["booking_id"], row["basis"]) for row in candidates] == [
        (booking, ["email", "phone"])
    ]
    body, key = {"action": "link", "booking_ids": [booking]}, str(uuid7())
    linked = await enabled.command(a, "booking-links", body, key)
    assert linked.status_code == 200, linked.text
    assert linked.json()["links"][0]["sequence"] == 1
    assert (await enabled.get(f"/{b}/booking-candidates")).json()["items"] == []
    duplicate = await enabled.command(b, "booking-links", body)
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "BOOKING_ALREADY_LINKED"
    merge = await enabled.command(
        a,
        "match-decisions",
        {"decision": "merge", "into_id": b, "expected_revision": 1, "into_expected_revision": 1},
    )
    assert merge.status_code == 200
    aggregate = (await enabled.get(f"/{b}/bookings")).json()["items"]
    assert [(row["booking"]["booking_id"], row["counterparty_id"]) for row in aggregate] == [
        (booking, a)
    ]
    assert (
        await enabled.command(
            a,
            "match-decisions",
            {
                "decision": "separate",
                "decision_id": merge.json()["decision_id"],
                "expected_revision": 2,
            },
        )
    ).status_code == 200
    assert (await enabled.get(f"/{b}/bookings")).json()["items"] == []
    assert (
        await enabled.save(
            UUID(a), card(expected_revision=3, email="changed@example.test", phone=None)
        )
    ).status_code == 200
    assert (await enabled.get(f"/{a}/bookings")).json()["items"][0]["still_matches"] is False
    wrong = await enabled.command(
        a, "booking-links", {"action": "unlink", "booking_id": booking, "expected_sequence": 2}
    )
    assert wrong.status_code == 409
    unlinked = await enabled.command(
        a, "booking-links", {"action": "unlink", "booking_id": booking, "expected_sequence": 1}
    )
    assert unlinked.status_code == 200
    assert (await enabled.command(a, "booking-links", body, key)).json() == linked.json()
    assert (await enabled.get(f"/{a}/bookings")).json()["items"] == []
    history = (await enabled.get(f"/{a}/booking-links")).json()["items"]
    assert [(row["action"], row["sequence"]) for row in history] == [("unlinked", 2), ("linked", 1)]
    with owner_tenant_transaction(owner_conn, enabled.business):
        assert (
            owner_conn.execute(
                "select * from gba.booking_customers where booking_id = %s", (booking,)
            ).fetchone()
            == before
        )


async def test_stale_or_foreign_booking_selection_rolls_back_the_entire_command(
    enabled: Counterparties, world: BookingWorld, app_pool: RuntimePool
) -> None:
    a = str((await enabled.create())["counterparty_id"])
    booking = await confirmed_booking(
        enabled, world, 11, "fake.counterparty@example.test", "+15550101234"
    )
    key = str(uuid7())
    result = await enabled.command(
        a, "booking-links", {"action": "link", "booking_ids": [booking, str(uuid7())]}, key
    )
    assert result.status_code == 409, result.text
    assert (await enabled.get(f"/{a}/bookings")).json()["items"] == []
    async with tenant_transaction(app_pool, enabled.business) as conn:
        assert (
            await (
                await conn.execute("select count(*) from gba.counterparty_booking_links")
            ).fetchone()
        ) == (0,)
        assert (
            await (
                await conn.execute(
                    "select count(*) from gba.idempotency_keys where idempotency_key = %s", (key,)
                )
            ).fetchone()
        ) == (0,)
    # Contact changes between preview and confirmation require a new match.
    assert (
        await enabled.save(
            UUID(a), card(expected_revision=1, email="different@example.test", phone=None)
        )
    ).status_code == 200
    stale = await enabled.command(a, "booking-links", {"action": "link", "booking_ids": [booking]})
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "BOOKING_NOT_A_CANDIDATE"


_COPY_VERSION = """
insert into gba.counterparty_versions
    (tenant_id, counterparty_id, revision, display_name, legal_name, tax_id,
     registration_number, email, phone, roles, state, merged_into, created_by)
select tenant_id, counterparty_id, revision + 1, display_name, legal_name, tax_id,
       registration_number, email, phone, roles, %s, %s, created_by
from gba.counterparty_versions where tenant_id = %s and counterparty_id = %s
order by revision desc limit 1
"""


@pytest.mark.parametrize("cycle", [True, False])
async def test_runtime_sql_cannot_stage_a_merge_cycle_or_chain_in_one_transaction(
    enabled: Counterparties, app_pool: RuntimePool, cycle: bool
) -> None:
    a, b, c = [str((await enabled.create())["counterparty_id"]) for _ in range(3)]

    async def stage() -> None:
        async with tenant_transaction(app_pool, enabled.business) as conn:
            for source, target in [(a, b), (b, a if cycle else c)]:
                await conn.execute(
                    "insert into gba.counterparty_match_decisions (tenant_id, kind, "
                    "counterparty_id, other_counterparty_id, counterparty_revision, decided_by) "
                    "values (%s, 'merged', %s, %s, 2, %s)",
                    (enabled.business, source, target, enabled.user.user_id),
                )
            await conn.execute(_COPY_VERSION, ("merged", b, enabled.business, a))
            await conn.execute(_COPY_VERSION, ("merged", a if cycle else c, enabled.business, b))

    with pytest.raises(psycopg.errors.CheckViolation):
        await stage()


async def test_one_merge_version_cannot_have_multiple_decisions(
    enabled: Counterparties, app_pool: RuntimePool
) -> None:
    a, b = [str((await enabled.create())["counterparty_id"]) for _ in range(2)]

    async def stage() -> None:
        async with tenant_transaction(app_pool, enabled.business) as conn:
            for _ in range(2):
                await conn.execute(
                    "insert into gba.counterparty_match_decisions (tenant_id, kind, "
                    "counterparty_id, other_counterparty_id, counterparty_revision, decided_by) "
                    "values (%s, 'merged', %s, %s, 2, %s)",
                    (enabled.business, a, b, enabled.user.user_id),
                )
            await conn.execute(_COPY_VERSION, ("merged", b, enabled.business, a))

    with pytest.raises(psycopg.errors.UniqueViolation):
        await stage()


async def test_direct_sql_cannot_forge_merge_separation_or_edit_saved_contacts(
    enabled: Counterparties, owner_conn: psycopg.Connection
) -> None:
    a = str((await enabled.create(contacts=[{"name": "FAKE Contact"}]))["counterparty_id"])
    b = str((await enabled.create(display_name="FAKE Target"))["counterparty_id"])
    c = str((await enabled.create(display_name="FAKE Unrelated"))["counterparty_id"])
    with owner_tenant_transaction(owner_conn, enabled.business):
        with pytest.raises(psycopg.errors.CheckViolation), owner_conn.transaction():
            owner_conn.execute(_COPY_VERSION, ("merged", b, enabled.business, a))
        with pytest.raises(psycopg.errors.CheckViolation), owner_conn.transaction():
            owner_conn.execute(
                "insert into gba.counterparty_version_contacts "
                "(tenant_id, counterparty_id, revision, position, name) "
                "values (%s, %s, 1, 2, 'FAKE Late Contact')",
                (enabled.business, a),
            )
        with pytest.raises(psycopg.errors.CheckViolation), owner_conn.transaction():
            owner_conn.execute(
                "update gba.counterparty_versions set display_name = 'FAKE Rewrite' "
                "where counterparty_id = %s",
                (a,),
            )
    merge = await enabled.command(
        a,
        "match-decisions",
        {"decision": "merge", "into_id": b, "expected_revision": 1, "into_expected_revision": 1},
    )
    assert merge.status_code == 200, merge.text
    with owner_tenant_transaction(owner_conn, enabled.business):
        for statement, params in (
            (_COPY_VERSION, ("active", None, enabled.business, a)),
            (
                "insert into gba.counterparty_match_decisions "
                "(tenant_id, kind, counterparty_id, other_counterparty_id, "
                "counterparty_revision, decided_by) values (%s, 'merged', %s, %s, 2, %s)",
                (enabled.business, b, a, enabled.user.user_id),
            ),
            (
                "insert into gba.counterparty_match_decisions (tenant_id, kind, counterparty_id, "
                "other_counterparty_id, reverses_decision_id, counterparty_revision, decided_by) "
                "values (%s, 'separated', %s, %s, %s, 2, %s)",
                (enabled.business, c, b, merge.json()["decision_id"], enabled.user.user_id),
            ),
        ):
            with pytest.raises(psycopg.errors.CheckViolation), owner_conn.transaction():
                owner_conn.execute(statement, params)
        # A valid-looking decision without its new version must fail at commit.
        with (  # noqa: PT012 - enforce the deferred constraint within the fixture transaction
            pytest.raises((psycopg.errors.CheckViolation, psycopg.errors.ForeignKeyViolation)),
            owner_conn.transaction(),
        ):
            owner_conn.execute(
                "insert into gba.counterparty_match_decisions (tenant_id, kind, counterparty_id, "
                "other_counterparty_id, counterparty_revision, decided_by) "
                "values (%s, 'merged', %s, %s, 2, %s)",
                (enabled.business, c, b, enabled.user.user_id),
            )
            owner_conn.execute("set constraints all immediate")


async def test_direct_sql_rejects_wrong_booking_basis_and_archived_card(
    enabled: Counterparties, world: BookingWorld, owner_conn: psycopg.Connection
) -> None:
    a = str((await enabled.create())["counterparty_id"])
    booking = await confirmed_booking(enabled, world, 11, "different@example.test", "+15559991234")
    statement = (
        "insert into gba.counterparty_booking_links (tenant_id, booking_id, sequence, action, "
        "counterparty_id, basis, decided_by) values (%s, %s, 1, 'linked', %s, array['email'], %s)"
    )
    with (
        owner_tenant_transaction(owner_conn, enabled.business),
        pytest.raises(psycopg.errors.CheckViolation),
        owner_conn.transaction(),
    ):
        owner_conn.execute(statement, (enabled.business, booking, a, enabled.user.user_id))
    assert (
        await enabled.save(
            UUID(a), card(expected_revision=1, email="different@example.test", archived=True)
        )
    ).status_code == 200
    with (
        owner_tenant_transaction(owner_conn, enabled.business),
        pytest.raises(psycopg.errors.CheckViolation),
        owner_conn.transaction(),
    ):
        owner_conn.execute(statement, (enabled.business, booking, a, enabled.user.user_id))


@pytest.mark.parametrize(
    "table",
    [
        "counterparties",
        "counterparty_versions",
        "counterparty_version_contacts",
        "counterparty_match_decisions",
        "counterparty_booking_links",
    ],
)
async def test_guard_rejects_weakened_counterparty_scope(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager_a: FakeUser,
    idp: FakeIdp,
    owner_conn: psycopg.Connection,
    table: str,
) -> None:
    from psycopg import sql

    policy, relation = sql.Identifier(f"{table}_unrestricted_scope"), sql.Identifier("gba", table)
    try:
        owner_conn.execute(
            sql.SQL("alter policy {} on {} using (true) with check (true)").format(policy, relation)
        )
        response = await client.get(
            f"/v1/businesses/{world.a.tenant_id}/counterparties",
            headers=idp.bearer(manager_a.subject, email=manager_a.email),
        )
        assert response.status_code == 503, response.text
        assert (await client.get("/health/ready")).status_code == 503
    finally:
        owner_conn.execute(
            sql.SQL(
                "alter policy {} on {} using (gba.current_location_id() is null) "
                "with check (gba.current_location_id() is null)"
            ).format(policy, relation)
        )
    assert (await client.get("/health/ready")).status_code == 200


@pytest.mark.parametrize(
    "damage",
    [
        "disabled",
        "wrong_argument",
        "wrong_timing",
        "wrong_function",
        "stable_function",
        "stable_booking",
    ],
)
async def test_guard_rejects_changed_module_gate(
    client: httpx.AsyncClient, owner_conn: psycopg.Connection, damage: str
) -> None:
    trigger = "counterparties_require_module"
    original = (
        f"create trigger {trigger} before insert on gba.counterparties "
        "for each row execute function gba.require_enabled_module('counterparties')"
    )
    migration = next(m.sql for m in load_migrations() if m.version == 15)
    start = migration.index("create function gba.require_enabled_module()")
    end = migration.index("revoke all on function gba.require_enabled_module()")
    try:
        if damage == "disabled":
            owner_conn.execute(f"alter table gba.counterparties disable trigger {trigger}")
        elif damage.startswith("stable_"):
            name = (
                "require_enabled_module"
                if damage == "stable_function"
                else "enforce_booking_module"
            )
            owner_conn.execute(f"alter function gba.{name}() stable")
        elif damage == "wrong_function":
            owner_conn.execute(
                "create or replace function gba.require_enabled_module() returns trigger "
                "language plpgsql as $$ begin return new; end; $$"
            )
        else:
            owner_conn.execute(f"drop trigger {trigger} on gba.counterparties")
            owner_conn.execute(
                original.replace("'counterparties'", "'booking_resources'")
                if damage == "wrong_argument"
                else original.replace("before insert", "after insert")
            )
        assert (await client.get("/health/ready")).status_code == 503
    finally:
        owner_conn.execute("alter function gba.enforce_booking_module() volatile")
        owner_conn.execute("alter function gba.require_enabled_module() volatile")
        owner_conn.execute(
            migration[start:end]
            .replace("create function", "create or replace function", 1)
            .encode("utf-8")
        )
        owner_conn.execute(f"drop trigger if exists {trigger} on gba.counterparties")
        owner_conn.execute(original)
    assert (await client.get("/health/ready")).status_code == 200


async def test_unpublished_module_is_readable_but_refuses_new_cards(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager_a: FakeUser,
    idp: FakeIdp,
) -> None:
    headers = idp.bearer(manager_a.subject, email=manager_a.email)
    base = f"/v1/businesses/{world.a.tenant_id}/counterparties"
    read = await client.get(base, headers=headers)
    assert read.status_code == 200, read.text
    assert read.json() == {
        "schema_version": 1,
        "business_id": str(world.a.tenant_id),
        "items": [],
        "next_cursor": None,
    }
    write = await client.put(
        f"{base}/{uuid7()}",
        json=card(),
        headers={**headers, "Idempotency-Key": str(uuid7())},
    )
    assert write.status_code == 409, write.text
    assert write.json()["error"]["code"] == "MODULE_DISABLED"


@pytest.mark.parametrize(
    ("role", "scoped"), [("artist", False), ("front_desk", False), ("manager", True)]
)
async def test_counterparties_deny_unapproved_members(
    client: httpx.AsyncClient,
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    idp: FakeIdp,
    role: str,
    scoped: bool,
) -> None:
    user = seed_user(owner_conn, f"FAKE-counterparty-role-{uuid7()}")
    add_membership(
        owner_conn,
        tenant_id=world.a.tenant_id,
        user_id=user.user_id,
        role=role,
        location_id=world.a.location_id if scoped else None,
    )
    response = await client.get(
        f"/v1/businesses/{world.a.tenant_id}/counterparties",
        headers=idp.bearer(user.subject, email=user.email),
    )
    assert response.status_code == 403, response.text


async def test_counterparties_deny_foreign_company(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager_b: FakeUser,
    idp: FakeIdp,
) -> None:
    response = await client.get(
        f"/v1/businesses/{world.a.tenant_id}/counterparties",
        headers=idp.bearer(manager_b.subject, email=manager_b.email),
    )
    assert response.status_code == 403, response.text


async def test_counterparties_deny_platform_support(
    client: httpx.AsyncClient,
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    idp: FakeIdp,
) -> None:
    user = seed_user(owner_conn, f"FAKE-counterparty-support-{uuid7()}")
    grant_platform_admin(owner_conn, user_id=user.user_id, granted_by="FAKE-test")
    response = await client.get(
        f"/v1/businesses/{world.a.tenant_id}/counterparties",
        headers=idp.bearer(user.subject, email=user.email),
    )
    assert response.status_code == 403, response.text
