"""Contracts with counterparties against real disposable PostgreSQL (ADR-0020 E3)."""

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest
from psycopg import sql

from gorgona_booking.db.pool import RuntimePool, tenant_transaction, unscoped_transaction
from gorgona_booking.db.provisioning import (
    add_membership,
    grant_platform_admin,
    owner_tenant_transaction,
)
from tests.integration import test_management_api as shared
from tests.integration.booking_support import BookingWorld
from tests.integration.seed import FakeUser, seed_user
from tests.integration.test_counterparties import card
from tests.integration.test_delegations import Parties
from tests.integration.test_documents import ALL_MODULES, Documents
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
manager_b = shared.manager_b

TODAY = datetime.now(UTC).date()
ATTESTED = "signed_outside_platform"


def draft(counterparty: str, **changes: object) -> dict[str, object]:
    return {
        "schema_version": 1,
        "expected_revision": 0,
        "counterparty_id": counterparty,
        "title": "FAKE Supply contract",
        "number": "FAKE-2026-01",
        "summary": "FAKE terms\nsecond line",
        "effective_from": "2026-01-01",
        "effective_until": "2026-12-31",
        **changes,
    }


class Agreements(Documents):
    async def put(
        self, subject: UUID | str, body: Mapping[str, object], key: str | None = None
    ) -> httpx.Response:
        return await self.client.put(
            f"{self.base}/agreements/{subject}", json=dict(body), headers=self.headers(key)
        )

    async def act(
        self,
        subject: UUID | str,
        action: str,
        body: Mapping[str, object],
        key: str | None = None,
    ) -> httpx.Response:
        return await self.client.post(
            f"{self.base}/agreements/{subject}/{action}",
            json={"schema_version": 1, **body},
            headers=self.headers(key),
        )

    async def agree(
        self, subject: UUID | str, revision: int, key: str | None = None, **changes: object
    ) -> httpx.Response:
        body = {
            "expected_revision": revision,
            "signed_on": TODAY.isoformat(),
            "attestation": ATTESTED,
            **changes,
        }
        return await self.act(subject, "agree", body, key)

    async def drafted(self, counterparty: str, **changes: object) -> str:
        subject = uuid7()
        response = await self.put(subject, draft(counterparty, **changes))
        assert response.status_code == 200, response.text
        return str(subject)


@pytest.fixture
async def enabled(
    client: httpx.AsyncClient, world: BookingWorld, manager_a: FakeUser, idp: FakeIdp
) -> Agreements:
    agreements = Agreements(client, world.a.tenant_id, manager_a, idp)
    await agreements.enable()
    return agreements


async def test_agreed_versions_stay_unchanged_through_amendment_and_termination(
    enabled: Agreements, owner_conn: psycopg.Connection, app_pool: RuntimePool
) -> None:
    partner = await enabled.counterparty()
    subject, key = uuid7(), str(uuid7())
    first = await enabled.put(subject, draft(partner), key)
    assert first.status_code == 200, first.text
    assert (first.json()["revision"], first.json()["state"]) == (1, "draft")
    assert (first.json()["signed_on"], first.json()["attestation"]) == (None, None)
    assert (await enabled.put(subject, draft(partner), key)).json() == first.json()
    second = await enabled.put(subject, draft(partner, expected_revision=1, title="FAKE v2"))
    assert second.json()["revision"] == 2
    agree_key = str(uuid7())
    agreed = await enabled.agree(subject, 2, agree_key)
    assert agreed.status_code == 200, agreed.text
    assert (agreed.json()["state"], agreed.json()["title"]) == ("agreed", "FAKE v2")
    assert (agreed.json()["attestation"], agreed.json()["signed_on"]) == (
        ATTESTED,
        TODAY.isoformat(),
    )
    assert (await enabled.agree(subject, 2, agree_key)).json() == agreed.json()

    def stored(revision: int) -> object:
        with owner_tenant_transaction(owner_conn, enabled.business):
            return owner_conn.execute(
                "select * from gba.agreement_versions where agreement_id = %s and revision = %s",
                (subject, revision),
            ).fetchone()

    original = stored(3)
    amendment = await enabled.put(
        subject, draft(partner, expected_revision=3, title="FAKE amended", summary=None)
    )
    assert (amendment.json()["revision"], amendment.json()["state"]) == (4, "draft")
    assert (await enabled.agree(subject, 4)).json()["revision"] == 5
    ended = await enabled.act(
        subject, "terminate", {"expected_revision": 5, "terminated_on": TODAY.isoformat()}
    )
    assert ended.status_code == 200, ended.text
    assert (ended.json()["state"], ended.json()["title"], ended.json()["summary"]) == (
        "terminated",
        "FAKE amended",
        None,
    )
    assert ended.json()["signed_on"] == TODAY.isoformat()
    assert stored(3) == original
    assert (await enabled.get(f"/agreements/{subject}", revision=3)).json() == agreed.json()
    history = (await enabled.get(f"/agreements/{subject}/versions")).json()["items"]
    assert [(r["revision"], r["state"]) for r in history] == [
        (6, "terminated"),
        (5, "agreed"),
        (4, "draft"),
        (3, "agreed"),
        (2, "draft"),
        (1, "draft"),
    ]
    for refused in (
        await enabled.put(subject, draft(partner, expected_revision=6)),
        await enabled.agree(subject, 6),
        await enabled.act(
            subject, "terminate", {"expected_revision": 6, "terminated_on": TODAY.isoformat()}
        ),
    ):
        assert (refused.status_code, refused.json()["error"]["code"]) == (
            409,
            "AGREEMENT_STATE_INVALID",
        )
    async with tenant_transaction(app_pool, enabled.business) as conn:
        audits = await (
            await conn.execute(
                "select action, details from gba.audit_events "
                "where action like 'agreement.%%' order by id"
            )
        ).fetchall()
        receipts = await (
            await conn.execute(
                "select response_body from gba.idempotency_keys "
                "where operation like 'business.agreement.%%'"
            )
        ).fetchall()
    assert [row[0] for row in audits] == [
        "agreement.drafted",
        "agreement.drafted",
        "agreement.agreed",
        "agreement.drafted",
        "agreement.agreed",
        "agreement.terminated",
    ]
    assert audits[3][1]["amendment"] is True
    for text in (str(audits), str(receipts)):
        assert "FAKE" not in text
    assert all(set(row[0]) == {"agreement_id", "revision"} for row in receipts)


async def test_termination_ends_the_agreed_version_and_abandons_an_open_amendment(
    enabled: Agreements, owner_conn: psycopg.Connection, app_pool: RuntimePool
) -> None:
    partner = await enabled.counterparty()
    subject = await enabled.drafted(partner)
    agreed = await enabled.agree(subject, 1)
    assert agreed.status_code == 200, agreed.text
    assert (agreed.json()["in_force_revision"], agreed.json()["terminates_revision"]) == (2, None)
    amendment = await enabled.put(
        subject, draft(partner, expected_revision=2, title="FAKE amended", number=None)
    )
    assert amendment.status_code == 200, amendment.text
    # The unsigned amendment does not replace the agreed version in force.
    assert (amendment.json()["state"], amendment.json()["in_force_revision"]) == ("draft", 2)
    listed = (await enabled.get(f"/counterparties/{partner}/agreements")).json()["items"]
    assert [
        (r["revision"], r["state"], r["in_force"]["revision"], r["in_force"]["signed_on"])
        for r in listed
    ] == [(3, "draft", 2, TODAY.isoformat())]
    with owner_tenant_transaction(owner_conn, enabled.business):
        signed = owner_conn.execute(
            "select * from gba.agreement_versions where agreement_id = %s and revision = 2",
            (subject,),
        ).fetchone()

    # Termination is recorded in advance and acts on the agreed version, not the draft.
    effective = (TODAY + timedelta(days=30)).isoformat()
    key = str(uuid7())
    ended = await enabled.act(
        subject, "terminate", {"expected_revision": 3, "terminated_on": effective}, key
    )
    assert ended.status_code == 200, ended.text
    body = ended.json()
    assert (body["revision"], body["state"], body["terminated_on"]) == (4, "terminated", effective)
    assert (body["in_force_revision"], body["terminates_revision"]) == (2, 2)
    assert (body["title"], body["number"], body["signed_on"]) == (
        "FAKE Supply contract",
        "FAKE-2026-01",
        TODAY.isoformat(),
    )
    replay = await enabled.act(
        subject, "terminate", {"expected_revision": 3, "terminated_on": effective}, key
    )
    assert replay.json() == body
    with owner_tenant_transaction(owner_conn, enabled.business):
        assert (
            owner_conn.execute(
                "select * from gba.agreement_versions where agreement_id = %s and revision = 2",
                (subject,),
            ).fetchone()
            == signed
        )
    history = (await enabled.get(f"/agreements/{subject}/versions")).json()["items"]
    assert [(r["revision"], r["state"], r["abandoned"]) for r in history] == [
        (4, "terminated", False),
        (3, "draft", True),
        (2, "agreed", False),
        (1, "draft", False),
    ]
    async with tenant_transaction(app_pool, enabled.business) as conn:
        audit = await (
            await conn.execute(
                "select details from gba.audit_events where action = 'agreement.terminated'"
            )
        ).fetchone()
    assert audit is not None
    assert audit[0] == {
        "revision": 4,
        "counterparty_id": partner,
        "terminates_revision": 2,
        "abandoned_draft_revision": 3,
        "terminated_on": effective,
    }
    # A contract that was never agreed has nothing to terminate.
    never = await enabled.drafted(partner)
    refused = await enabled.act(
        never, "terminate", {"expected_revision": 1, "terminated_on": effective}
    )
    assert (refused.status_code, refused.json()["error"]["code"]) == (
        409,
        "AGREEMENT_STATE_INVALID",
    )


async def test_open_amendments_keep_describing_the_version_in_force(
    enabled: Agreements, app_pool: RuntimePool
) -> None:
    partner = await enabled.counterparty()
    subject = await enabled.drafted(partner)
    assert (await enabled.agree(subject, 1)).status_code == 200
    for revision, title in ((2, "FAKE amended"), (3, "FAKE amended twice")):
        saved = await enabled.put(
            subject,
            draft(
                partner,
                expected_revision=revision,
                title=title,
                number=None,
                effective_until="2027-12-31",
            ),
        )
        assert saved.status_code == 200, saved.text
    # The list row names the agreed version in force, not the unsigned draft.
    listed = (await enabled.get(f"/counterparties/{partner}/agreements")).json()["items"]
    assert [(r["revision"], r["state"], r["title"]) for r in listed] == [
        (4, "draft", "FAKE amended twice")
    ]
    assert listed[0]["in_force"] == {
        "revision": 2,
        "title": "FAKE Supply contract",
        "number": "FAKE-2026-01",
        "effective_from": "2026-01-01",
        "effective_until": "2026-12-31",
        "signed_on": TODAY.isoformat(),
    }
    # Every save of an open amendment is audited as an amendment.
    async with tenant_transaction(app_pool, enabled.business) as conn:
        flags = await (
            await conn.execute(
                "select details->>'amendment' from gba.audit_events "
                "where action = 'agreement.drafted' and target_id = %s order by id",
                (subject,),
            )
        ).fetchall()
    assert [row[0] for row in flags] == ["false", "true", "true"]
    # An archived card still lets the agreed contract end; only the open draft is
    # abandoned, the draft it replaced was superseded.
    archived = await enabled.client.put(
        f"{enabled.base}/counterparties/{partner}",
        json=card(expected_revision=1, archived=True),
        headers=enabled.headers(),
    )
    assert archived.status_code == 200, archived.text
    ended = await enabled.act(
        subject, "terminate", {"expected_revision": 4, "terminated_on": TODAY.isoformat()}
    )
    assert ended.status_code == 200, ended.text
    assert (ended.json()["terminates_revision"], ended.json()["title"]) == (
        2,
        "FAKE Supply contract",
    )
    history = (await enabled.get(f"/agreements/{subject}/versions")).json()["items"]
    assert [(r["revision"], r["abandoned"]) for r in history] == [
        (5, False),
        (4, True),
        (3, False),
        (2, False),
        (1, False),
    ]


async def test_rejected_input_and_orphan_contracts(
    enabled: Agreements, app_pool: RuntimePool
) -> None:
    partner = await enabled.counterparty()
    # C1 control characters are refused as input, never reported as a conflict.
    for title in ("FAKE\u0085line", "FAKE\u009fline"):
        refused = await enabled.put(uuid7(), draft(partner, title=title))
        assert refused.status_code == 422, refused.text
    # The runtime role cannot keep a contract without its first version.
    with pytest.raises(psycopg.errors.CheckViolation, match="first version"):
        async with tenant_transaction(app_pool, enabled.business) as conn:
            await conn.execute(
                "insert into gba.agreements (tenant_id, id, counterparty_id, created_by) "
                "values (%s, %s, %s, %s)",
                (enabled.business, uuid7(), partner, enabled.user.user_id),
            )
    async with tenant_transaction(app_pool, enabled.business) as conn:
        assert (await (await conn.execute("select * from gba.agreements")).fetchall()) == []


async def test_commands_refuse_invalid_attestation_dates_and_references(
    enabled: Agreements,
) -> None:
    partner = await enabled.counterparty()
    other = await enabled.counterparty(display_name="FAKE Other")
    subject = await enabled.drafted(partner)
    tomorrow = (TODAY + timedelta(days=2)).isoformat()
    cases = [
        (await enabled.agree(subject, 1, attestation=None), 422, "ATTESTATION_REQUIRED"),
        (await enabled.agree(subject, 1, attestation="signed"), 422, "ATTESTATION_REQUIRED"),
        (await enabled.agree(subject, 1, signed_on=tomorrow), 422, "AGREEMENT_DATE_INVALID"),
        (await enabled.agree(subject, 2), 409, "CONFLICT"),
        (
            await enabled.act(
                subject, "terminate", {"expected_revision": 1, "terminated_on": "2026-01-01"}
            ),
            409,
            "AGREEMENT_STATE_INVALID",
        ),
        (
            await enabled.put(subject, draft(other, expected_revision=1)),
            422,
            "INVALID_REFERENCE",
        ),
        (await enabled.put(uuid7(), draft(str(uuid7()))), 422, "INVALID_REFERENCE"),
        (
            await enabled.put(uuid7(), draft(partner, legal_entity_id=str(uuid7()))),
            422,
            "INVALID_REFERENCE",
        ),
        (
            await enabled.put(
                uuid7(), draft(partner, document={"document_id": str(uuid7()), "revision": 1})
            ),
            422,
            "INVALID_REFERENCE",
        ),
        (await enabled.agree(uuid7(), 1), 404, "NOT_FOUND"),
    ]
    assert [(r.status_code, r.json()["error"]["code"]) for r, _, _ in cases] == [
        (status, code) for _, status, code in cases
    ]
    for invalid in (
        draft(partner, effective_from="2026-02-01", effective_until="2026-01-01"),
        draft(partner, title=" "),
        draft(partner, number="FAKE\x07"),
        draft(partner, summary="x" * 2001),
        draft(partner, expected_revision=True),
        draft(partner, state="agreed"),
    ):
        assert (await enabled.put(uuid7(), invalid)).status_code == 422
    agreed = await enabled.agree(subject, 1)
    early = await enabled.act(
        subject,
        "terminate",
        {"expected_revision": 2, "terminated_on": (TODAY - timedelta(days=1)).isoformat()},
    )
    assert (early.status_code, early.json()["error"]["code"]) == (422, "AGREEMENT_DATE_INVALID")
    assert agreed.status_code == 200
    key = str(uuid7())
    assert (await enabled.put(uuid7(), draft(partner), key)).status_code == 200
    assert (await enabled.put(uuid7(), draft(partner), key)).status_code == 422


async def test_signed_document_reference_and_counterparty_family(
    enabled: Agreements,
) -> None:
    partner = await enabled.counterparty(display_name="FAKE Duplicate")
    survivor = await enabled.counterparty(display_name="FAKE Survivor")
    document = str((await enabled.create(title="FAKE signed copy"))["document_id"])
    subject = await enabled.drafted(partner)
    reference = {"document_id": document, "revision": 1}
    agreed = await enabled.agree(subject, 1, document=reference)
    assert agreed.json()["document"] == reference
    merge = await enabled.client.post(
        f"{enabled.base}/counterparties/{partner}/match-decisions",
        json={
            "decision": "merge",
            "into_id": survivor,
            "expected_revision": 1,
            "into_expected_revision": 1,
        },
        headers=enabled.headers(),
    )
    assert merge.status_code == 200, merge.text
    family = (await enabled.get(f"/counterparties/{survivor}/agreements")).json()["items"]
    assert [(r["agreement_id"], r["counterparty_id"], r["state"]) for r in family] == [
        (subject, partner, "agreed")
    ]
    refused = await enabled.put(subject, draft(partner, expected_revision=2))
    assert (refused.status_code, refused.json()["error"]["code"]) == (
        409,
        "COUNTERPARTY_STATE_INVALID",
    )
    assert (await enabled.put(uuid7(), draft(partner))).status_code == 409
    # Ending an existing contract stays possible after the card was merged.
    ended = await enabled.act(
        subject, "terminate", {"expected_revision": 2, "terminated_on": TODAY.isoformat()}
    )
    assert ended.status_code == 200, ended.text
    assert ended.json()["document"] == reference
    for _ in range(2):
        await enabled.drafted(survivor)
    page = (await enabled.get(f"/counterparties/{survivor}/agreements", limit=2)).json()
    rest = (
        await enabled.get(
            f"/counterparties/{survivor}/agreements", limit=2, after=page["next_cursor"]
        )
    ).json()
    assert len({r["agreement_id"] for r in page["items"] + rest["items"]}) == 3
    assert rest["next_cursor"] is None
    assert (await enabled.get(f"/counterparties/{uuid7()}/agreements")).status_code == 404


async def test_module_disable_keeps_reads_and_replays_but_stops_new_versions(
    enabled: Agreements, app_pool: RuntimePool
) -> None:
    partner = await enabled.counterparty()
    subject, key = uuid7(), str(uuid7())
    first = await enabled.put(subject, draft(partner), key)
    assert first.status_code == 200
    await enabled.config.publish(enabled.user, enabled.business, 1, ["booking_resources"])
    assert (await enabled.get(f"/agreements/{subject}")).json() == first.json()
    assert (await enabled.get(f"/agreements/{subject}/versions")).status_code == 200
    assert (await enabled.get(f"/counterparties/{partner}/agreements")).status_code == 200
    assert (await enabled.put(subject, draft(partner), key)).json() == first.json()
    for refused in (
        await enabled.put(uuid7(), draft(partner)),
        await enabled.put(subject, draft(partner, expected_revision=1)),
        await enabled.agree(subject, 1),
    ):
        assert (refused.status_code, refused.json()["error"]["code"]) == (409, "MODULE_DISABLED")
    async with tenant_transaction(app_pool, enabled.business) as conn:
        with pytest.raises(psycopg.Error, match="counterparties module is disabled"):
            async with conn.transaction():
                await conn.execute(
                    "insert into gba.agreements (tenant_id, id, counterparty_id, created_by) "
                    "values (%s, %s, %s, %s)",
                    (enabled.business, uuid7(), partner, enabled.user.user_id),
                )


_COPY = """
insert into gba.agreement_versions (tenant_id, agreement_id, revision, state, title, number,
    summary, effective_from, effective_until, signed_on, attestation, document_id,
    document_revision, terminated_on, created_by)
select tenant_id, agreement_id, revision + 1, %s, %s, number, summary, effective_from,
    effective_until, %s, %s, document_id, document_revision, %s, created_by
from gba.agreement_versions where agreement_id = %s order by revision desc limit 1
"""
# A termination row copied from one stored version, naming the agreed revision it ends.
_TERMINATE = """
insert into gba.agreement_versions (tenant_id, agreement_id, revision, state, title, number,
    summary, effective_from, effective_until, signed_on, attestation, document_id,
    document_revision, terminated_on, terminates_revision, created_by)
select tenant_id, agreement_id, %s, 'terminated', %s, number, summary, effective_from,
    effective_until, coalesce(signed_on, %s), 'signed_outside_platform', document_id,
    document_revision, %s, %s, created_by
from gba.agreement_versions where agreement_id = %s and revision = %s
"""


async def test_direct_sql_cannot_rewrite_or_forge_agreement_history(
    enabled: Agreements, owner_conn: psycopg.Connection
) -> None:
    partner = await enabled.counterparty()
    archived = await enabled.counterparty(display_name="FAKE Archived")
    assert (
        await enabled.client.put(
            f"{enabled.base}/counterparties/{archived}",
            json=card(display_name="FAKE Archived", expected_revision=1, archived=True),
            headers=enabled.headers(),
        )
    ).status_code == 200
    drafted = await enabled.drafted(partner)
    agreed = await enabled.drafted(partner)
    assert (await enabled.agree(agreed, 1)).status_code == 200
    # Agreed at 2 and 4 with an open amendment draft at 5.
    amended = await enabled.drafted(partner)
    assert (await enabled.agree(amended, 1)).status_code == 200
    changed = draft(partner, expected_revision=2, title="FAKE amended")
    assert (await enabled.put(amended, changed)).status_code == 200
    assert (await enabled.agree(amended, 3)).status_code == 200
    reopened = draft(partner, expected_revision=4, title="FAKE reopened")
    assert (await enabled.put(amended, reopened)).status_code == 200
    today, future = TODAY, TODAY + timedelta(days=3)
    title = "FAKE Supply contract"
    with owner_tenant_transaction(owner_conn, enabled.business):
        for statement, params in (
            ("update gba.agreement_versions set title = 'FAKE rewrite'", ()),
            ("delete from gba.agreement_versions", ()),
            ("update gba.agreements set counterparty_id = counterparty_id", ()),
            # Agreeing with changed content, terminating a draft, a future signature,
            # a draft with a signature and skipping a revision.
            (_COPY, ("agreed", "FAKE changed", today, ATTESTED, None, drafted)),
            (_COPY, ("terminated", title, today, ATTESTED, today, drafted)),
            (_COPY, ("agreed", title, future, ATTESTED, None, drafted)),
            (_COPY, ("draft", title, today, None, None, drafted)),
            (_COPY, ("terminated", "FAKE changed", today, ATTESTED, today, agreed)),
            # A termination must name the latest agreed revision and repeat it exactly:
            # not a draft, not an earlier agreement, not missing, not with other content,
            # and never for a contract that was not agreed.
            (_TERMINATE, (6, "FAKE reopened", today, future, 5, amended, 5)),
            (_TERMINATE, (6, title, today, future, 2, amended, 2)),
            (_TERMINATE, (6, "FAKE amended", today, future, None, amended, 4)),
            (_TERMINATE, (6, "FAKE changed", today, future, 4, amended, 4)),
            (_TERMINATE, (6, "FAKE amended", today, today - timedelta(days=1), 4, amended, 4)),
            (_TERMINATE, (2, title, today, future, 1, drafted, 1)),
            (
                "insert into gba.agreement_versions (tenant_id, agreement_id, revision, state, "
                "title, terminates_revision, created_by) "
                "values (%s, %s, 6, 'draft', 'FAKE', 4, %s)",
                (enabled.business, amended, enabled.user.user_id),
            ),
            (
                "insert into gba.agreement_versions (tenant_id, agreement_id, revision, state, "
                "title, created_by) values (%s, %s, 5, 'draft', 'FAKE', %s)",
                (enabled.business, drafted, enabled.user.user_id),
            ),
            (
                "insert into gba.agreements (tenant_id, id, counterparty_id, created_by) "
                "values (%s, %s, %s, %s)",
                (enabled.business, uuid7(), archived, enabled.user.user_id),
            ),
        ):
            with pytest.raises(psycopg.errors.CheckViolation), owner_conn.transaction():
                owner_conn.execute(statement, params)
        # The same statement is accepted for the latest agreed revision (then rolled back).
        with owner_conn.transaction(force_rollback=True):
            owner_conn.execute(_TERMINATE, (6, "FAKE amended", today, future, 4, amended, 4))


async def test_competing_commands_have_one_winner(enabled: Agreements) -> None:
    partner = await enabled.counterparty()
    subject = uuid7()
    results = await asyncio.gather(*(enabled.put(subject, draft(partner)) for _ in range(2)))
    assert sorted(r.status_code for r in results) == [200, 409]
    agreed = await asyncio.gather(*(enabled.agree(subject, 1) for _ in range(2)))
    assert sorted(r.status_code for r in agreed) == [200, 409]
    archive = enabled.client.put(
        f"{enabled.base}/counterparties/{partner}",
        json=card(expected_revision=1, archived=True),
        headers=enabled.headers(),
    )
    amend = enabled.put(subject, draft(partner, expected_revision=2))
    raced = await asyncio.gather(archive, amend)
    assert raced[0].status_code == 200
    # Either the amendment came first (saved) or it saw the archived card (refused);
    # the stored contract matches the answer either way.
    latest = (await enabled.get(f"/agreements/{subject}")).json()
    if raced[1].status_code == 200:
        assert (latest["revision"], latest["state"]) == (3, "draft")
    else:
        assert raced[1].json()["error"]["code"] == "COUNTERPARTY_STATE_INVALID"
        assert (latest["revision"], latest["state"]) == (2, "agreed")
    assert latest["in_force_revision"] == 2


async def test_isolation_branch_sessions_and_revocation(
    enabled: Agreements,
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager_b: FakeUser,
    idp: FakeIdp,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
) -> None:
    partner = await enabled.counterparty()
    subject, key = uuid7(), str(uuid7())
    assert (await enabled.put(subject, draft(partner), key)).status_code == 200
    foreign = Agreements(client, world.b.tenant_id, manager_b, idp)
    await foreign.enable(ALL_MODULES)
    assert (await foreign.get(f"/agreements/{subject}")).status_code == 404
    assert (await foreign.put(uuid7(), draft(partner))).status_code == 422
    async with unscoped_transaction(app_pool) as conn:
        assert (await (await conn.execute("select * from gba.agreements")).fetchall()) == []
    async with tenant_transaction(app_pool, enabled.business) as conn:
        await conn.execute(
            "select pg_catalog.set_config('gba.location_id', %s, true)", (str(world.a.location_id),)
        )
        for table in ("agreements", "agreement_versions"):
            query = sql.SQL("select * from {}").format(sql.Identifier("gba", table))
            assert (await (await conn.execute(query)).fetchall()) == []
    with owner_tenant_transaction(owner_conn, enabled.business):
        owner_conn.execute(
            "update gba.memberships set status = 'revoked' where user_id = %s",
            (enabled.user.user_id,),
        )
    assert (await enabled.put(subject, draft(partner), key)).status_code == 403


async def test_agreements_deny_delegates_branch_members_foreign_and_support(
    enabled: Agreements,
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    idp: FakeIdp,
    manager_b: FakeUser,
) -> None:
    partner = await enabled.counterparty()
    subject = await enabled.drafted(partner)
    owners = [seed_user(owner_conn, f"FAKE-agreement-owner-{uuid7()}") for _ in range(2)]
    for salon, user in zip((world.a, world.b), owners, strict=True):
        add_membership(owner_conn, tenant_id=salon.tenant_id, user_id=user.user_id, role="owner")
    await Parties(enabled.client, idp, world).active_grant(owners[0], owners[1], [owners[1]])
    support = seed_user(owner_conn, f"FAKE-agreement-support-{uuid7()}")
    grant_platform_admin(owner_conn, user_id=support.user_id, granted_by="FAKE-test")
    users = [owners[1], support, manager_b]
    for role, scoped in (("artist", False), ("front_desk", False), ("manager", True)):
        member = seed_user(owner_conn, f"FAKE-agreement-{role}-{uuid7()}")
        add_membership(
            owner_conn,
            tenant_id=world.a.tenant_id,
            user_id=member.user_id,
            role=role,
            location_id=world.a.location_id if scoped else None,
        )
        users.append(member)
    for user in users:
        other = Agreements(enabled.client, enabled.business, user, idp)
        for path in (
            f"/agreements/{subject}",
            f"/agreements/{subject}/versions",
            f"/counterparties/{partner}/agreements",
        ):
            assert (await other.get(path)).status_code == 403, (user.subject, path)
        assert (await other.agree(subject, 1)).status_code == 403
        assert (await other.put(uuid7(), draft(partner))).status_code == 403


@pytest.mark.parametrize("table", ["agreements", "agreement_versions"])
async def test_guard_rejects_weakened_agreement_scope(
    enabled: Agreements, owner_conn: psycopg.Connection, table: str
) -> None:
    policy, relation = sql.Identifier(f"{table}_unrestricted_scope"), sql.Identifier("gba", table)
    try:
        owner_conn.execute(
            sql.SQL("alter policy {} on {} using (true) with check (true)").format(policy, relation)
        )
        assert (await enabled.get(f"/agreements/{uuid7()}")).status_code == 503
        assert (await enabled.client.get("/health/ready")).status_code == 503
    finally:
        owner_conn.execute(
            sql.SQL(
                "alter policy {} on {} using (gba.current_location_id() is null) "
                "with check (gba.current_location_id() is null)"
            ).format(policy, relation)
        )
    assert (await enabled.client.get("/health/ready")).status_code == 200


@pytest.mark.parametrize(
    ("table", "damage"), [("agreements", "disabled"), ("agreement_versions", "wrong_argument")]
)
async def test_guard_rejects_changed_agreement_gates(
    client: httpx.AsyncClient, owner_conn: psycopg.Connection, table: str, damage: str
) -> None:
    trigger = f"{table}_require_module"
    original = (
        f"create trigger {trigger} before insert on gba.{table} "
        "for each row execute function gba.require_enabled_module('counterparties')"
    )
    try:
        if damage == "disabled":
            owner_conn.execute(f"alter table gba.{table} disable trigger {trigger}")
        else:
            owner_conn.execute(f"drop trigger {trigger} on gba.{table}")
            owner_conn.execute(original.replace("'counterparties'", "'documents'"))
        assert (await client.get("/health/ready")).status_code == 503
    finally:
        owner_conn.execute(f"drop trigger if exists {trigger} on gba.{table}")
        owner_conn.execute(original)
    assert (await client.get("/health/ready")).status_code == 200
