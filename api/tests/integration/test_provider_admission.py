"""H4 metadata history, SQL controls, recovery and company-only authorization.

Uses the real accepted finance registry; finance_documents is never enabled.
"""

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest
from psycopg import sql
from pydantic import ValidationError

from gorgona_booking.business.provider_admission_contracts import AdmissionDraftInput
from gorgona_booking.db.pool import RuntimeConnection, RuntimePool, tenant_transaction
from gorgona_booking.db.provider_admission_guard import ADMISSION_TABLES
from gorgona_booking.db.provisioning import (
    add_membership,
    grant_platform_admin,
    owner_tenant_transaction,
)
from tests.integration import test_ledger as shared
from tests.integration.booking_support import BookingWorld
from tests.integration.configuration_support import Config
from tests.integration.seed import FakeUser, seed_user
from tests.integration.test_delegations import Parties
from tests.integration.test_ledger import LedgerWorld
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
manager_b = shared.manager_b
enabled = shared.enabled


@dataclass(frozen=True)
class AdmissionWorld:
    ledger: LedgerWorld

    @property
    def base(self) -> str:
        return f"/v1/businesses/{self.ledger.business}/provider-admission"

    @property
    def collection(self) -> str:
        return f"{self.base}/books/{self.ledger.book}/requests"

    def draft(self, **changes: object) -> dict[str, object]:
        return {
            "schema_version": 1,
            "expected_revision": 0,
            "provider": "stripe_connect",
            "country": "US",
            "business_activity": "FAKE declared activity",
            "requested_operation": "charge",
            "assessment": "not_checked",
            "account_reference": "FAKE-private-account",
            "evidence_references": ["FAKE-private-evidence"],
            "notes": "FAKE private notes",
            **changes,
        }

    async def save(
        self, request: UUID, *, key: str | None = None, **changes: object
    ) -> httpx.Response:
        return await self.ledger.client.put(
            f"{self.collection}/{request}",
            json=self.draft(**changes),
            headers=self.ledger.headers(key),
        )

    async def act(
        self, request: UUID, action: str, revision: int, *, key: str | None = None
    ) -> httpx.Response:
        return await self.ledger.client.post(
            f"{self.collection}/{request}/{action}",
            json={"schema_version": 1, "expected_revision": revision},
            headers=self.ledger.headers(key),
        )

    def reference(self, request: UUID, operation: str, revision: int) -> dict[str, object]:
        return {
            "schema_version": 1,
            "operation": operation,
            "book_id": str(self.ledger.book),
            "subject_id": str(request),
            "revision": revision,
        }

    async def recover(
        self, key: str, request: UUID, operation: str, revision: int, action: str = "resolve"
    ) -> httpx.Response:
        return await self.ledger.client.post(
            f"{self.base}/commands/{key}/{action}",
            json=self.reference(request, operation, revision),
            headers=self.ledger.auth,
        )


@pytest.fixture
def admission(enabled: LedgerWorld) -> AdmissionWorld:
    return AdmissionWorld(enabled)


async def _counts(conn: RuntimeConnection, business: UUID, book: UUID) -> tuple[object, ...]:
    counts = []
    for table in (
        "journal_entries",
        "financial_documents",
        "financial_obligations",
        "external_payments",
    ):
        row = await (
            await conn.execute(
                sql.SQL("select count(*) from gba.{} where tenant_id=%s and book_id=%s").format(
                    sql.Identifier(table)
                ),
                (business, book),
            )
        ).fetchone()
        assert row is not None
        counts.append(row[0])
    return tuple(counts)


async def test_history_lifecycle_has_no_money_or_positive_capability(
    admission: AdmissionWorld, app_pool: RuntimePool
) -> None:
    request = uuid7()
    async with tenant_transaction(app_pool, admission.ledger.business) as conn:
        before = await _counts(conn, admission.ledger.business, admission.ledger.book)
    first = await admission.save(request)
    second = await admission.save(
        request, expected_revision=1, assessment="unsupported", notes="FAKE updated private notes"
    )
    assert first.status_code == second.status_code == 200, (first.text, second.text)
    submitted = await admission.act(request, "submit", 2)
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["state"] == "submitted"
    assert (await admission.save(request, expected_revision=3)).status_code == 409
    assert (await admission.act(request, "submit", 3)).status_code == 409
    withdrawn = await admission.act(request, "withdraw", 3)
    assert withdrawn.status_code == 200, withdrawn.text
    assert withdrawn.json()["state"] == "withdrawn"
    assert withdrawn.json()["operational_capabilities"] == dict.fromkeys(
        ("charge", "refund", "transfer", "payout"), False
    )
    assert withdrawn.json()["evidence_status"] == "manually_provided_unverified"
    assert withdrawn.json()["assessment"] == "unsupported"
    assert (await admission.act(request, "submit", 4)).status_code == 409
    for revision, expected in (
        (1, first.json()),
        (2, second.json()),
        (3, submitted.json()),
        (4, withdrawn.json()),
    ):
        read = await admission.ledger.client.get(
            f"{admission.collection}/{request}?revision={revision}", headers=admission.ledger.auth
        )
        assert read.status_code == 200, read.text
        assert read.json() == expected, read.text
    listed = await admission.ledger.client.get(admission.collection, headers=admission.ledger.auth)
    assert listed.status_code == 200, listed.text
    assert listed.json()["items"] == [withdrawn.json()], listed.text
    async with tenant_transaction(app_pool, admission.ledger.business) as conn:
        assert await _counts(conn, admission.ledger.business, admission.ledger.book) == before
        receipts = await (
            await conn.execute(
                "select response_body from gba.idempotency_keys where "
                "tenant_id=%s and operation like 'business.provider_admission.%%'",
                (admission.ledger.business,),
            )
        ).fetchall()
        assert len(receipts) == 4
        assert all(
            set(row[0]) == {"schema_version", "book_id", "request_id", "revision"}
            for row in receipts
        )
        audits = await (
            await conn.execute(
                "select details from gba.audit_events where tenant_id=%s and "
                "action like 'provider_admission.%%'",
                (admission.ledger.business,),
            )
        ).fetchall()
        assert all(set(row[0]) == {"book_id", "revision"} for row in audits)
        assert "FAKE-private" not in str(receipts) + str(audits)


async def test_empty_evidence_stays_a_draft(admission: AdmissionWorld) -> None:
    request = uuid7()
    assert (await admission.save(request, evidence_references=[])).status_code == 200
    refused = await admission.act(request, "submit", 1)
    assert (refused.status_code, refused.json()["error"]["code"]) == (
        409,
        "PROVIDER_ADMISSION_STATE_INVALID",
    )
    assert (await admission.act(request, "withdraw", 1)).status_code == 200


async def test_module_off_keeps_history_recovery_and_withdrawal(
    admission: AdmissionWorld, idp: FakeIdp
) -> None:
    request, key = uuid7(), str(uuid7())
    assert (await admission.save(request, key=key)).status_code == 200
    config = Config(admission.ledger.client, idp)
    await config.publish(admission.ledger.user, admission.ledger.business, 1, ["booking_resources"])
    assert (
        await admission.ledger.client.get(admission.collection, headers=admission.ledger.auth)
    ).status_code == 200
    assert (await admission.recover(key, request, "admission_draft", 1)).json()[
        "state"
    ] == "committed"
    assert (await admission.save(request, key=key)).status_code == 200
    assert (await admission.save(uuid7())).json()["error"]["code"] == "MODULE_DISABLED"
    assert (await admission.act(request, "submit", 1)).json()["error"]["code"] == "MODULE_DISABLED"
    assert (await admission.act(request, "withdraw", 1)).status_code == 200
    absent = uuid7()
    cancelled = await admission.recover(str(uuid7()), absent, "admission_draft", 1, "cancel")
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["state"] == "cancelled", cancelled.text


async def test_version_race_and_same_command_replay(admission: AdmissionWorld) -> None:
    request = uuid7()
    assert (await admission.save(request)).status_code == 200
    left, right = await asyncio.gather(
        admission.save(request, expected_revision=1, notes="FAKE left"),
        admission.save(request, expected_revision=1, notes="FAKE right"),
    )
    assert sorted((left.status_code, right.status_code)) == [200, 409], (left.text, right.text)
    key = str(uuid7())
    one, two = await asyncio.gather(
        admission.act(request, "submit", 2, key=key), admission.act(request, "submit", 2, key=key)
    )
    assert one.status_code == two.status_code == 200, (one.text, two.text)
    assert one.json() == two.json(), (one.text, two.text)


async def test_cancel_is_permanent_and_races_the_delayed_original(
    admission: AdmissionWorld,
) -> None:
    request, key = uuid7(), str(uuid7())
    cancelled = await admission.recover(key, request, "admission_draft", 1, "cancel")
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["state"] == "cancelled", cancelled.text
    late = await admission.save(request, key=key)
    assert (late.status_code, late.json()["error"]["code"]) == (
        409,
        "PROVIDER_ADMISSION_COMMAND_CANCELLED",
    )
    assert (await admission.recover(key, request, "admission_draft", 1)).json()[
        "state"
    ] == "cancelled"
    assert (
        await admission.ledger.client.get(
            f"{admission.collection}/{request}", headers=admission.ledger.auth
        )
    ).status_code == 404
    request, key = uuid7(), str(uuid7())
    save, cancel = await asyncio.gather(
        admission.save(request, key=key),
        admission.recover(key, request, "admission_draft", 1, "cancel"),
    )
    assert cancel.status_code == 200, cancel.text
    assert (save.status_code, cancel.json()["state"]) in ((200, "committed"), (409, "cancelled")), (
        save.text,
        cancel.text,
    )


async def test_recovery_after_ttl_replays_original_revision_and_rejects_other_body(
    admission: AdmissionWorld, owner_conn: psycopg.Connection
) -> None:
    request, key = uuid7(), str(uuid7())
    first = await admission.save(request, key=key)
    assert first.status_code == 200, first.text
    assert (
        await admission.save(request, expected_revision=1, notes="FAKE successor")
    ).status_code == 200
    with owner_tenant_transaction(owner_conn, admission.ledger.business):
        owner_conn.execute(
            "update gba.idempotency_keys set expires_at=now()-interval '1 "
            "second' where tenant_id=%s and idempotency_key=%s",
            (admission.ledger.business, key),
        )
    replay = await admission.save(request, key=key)
    assert replay.status_code == 200, replay.text
    assert replay.json() == first.json(), replay.text
    different = await admission.save(request, key=key, notes="FAKE different")
    assert different.status_code == 422, different.text
    assert different.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED", different.text
    assert (await admission.recover(key, uuid7(), "admission_draft", 1)).status_code == 422


@pytest.mark.parametrize("role", ["owner", "manager"])
async def test_company_roles_can_declare(
    admission: AdmissionWorld, owner_conn: psycopg.Connection, idp: FakeIdp, role: str
) -> None:
    user = seed_user(owner_conn, f"admission-company-{uuid7()}")
    add_membership(owner_conn, tenant_id=admission.ledger.business, user_id=user.user_id, role=role)
    headers = {**idp.bearer(user.subject, email=user.email), "Idempotency-Key": str(uuid7())}
    saved = await admission.ledger.client.put(
        f"{admission.collection}/{uuid7()}", json=admission.draft(), headers=headers
    )
    assert saved.status_code == 200, saved.text


@pytest.mark.parametrize(
    "role", ["artist", "front_desk", "branch_manager", "outsider", "support", "delegate"]
)
async def test_untrusted_roles_cannot_read_mutate_or_recover(
    admission: AdmissionWorld,
    owner_conn: psycopg.Connection,
    world: BookingWorld,
    idp: FakeIdp,
    role: str,
) -> None:
    user = seed_user(owner_conn, f"admission-denied-{uuid7()}")
    if role == "support":
        grant_platform_admin(owner_conn, user_id=user.user_id, granted_by="FAKE test operator")
    elif role == "delegate":
        add_membership(
            owner_conn, tenant_id=world.b.tenant_id, user_id=user.user_id, role="manager"
        )
        owner = seed_user(owner_conn, f"admission-owner-{uuid7()}")
        add_membership(owner_conn, tenant_id=world.a.tenant_id, user_id=owner.user_id, role="owner")
        await Parties(admission.ledger.client, idp, world).active_grant(owner, user, [user])
    elif role != "outsider":
        add_membership(
            owner_conn,
            tenant_id=admission.ledger.business,
            user_id=user.user_id,
            role="manager" if role == "branch_manager" else role,
            location_id=world.a.location_id if role == "branch_manager" else None,
        )
    headers = {**idp.bearer(user.subject, email=user.email), "Idempotency-Key": str(uuid7())}
    request = uuid7()
    responses = (
        await admission.ledger.client.get(admission.collection, headers=headers),
        await admission.ledger.client.put(
            f"{admission.collection}/{request}", json=admission.draft(), headers=headers
        ),
        await admission.ledger.client.post(
            f"{admission.base}/commands/{uuid7()}/resolve",
            json=admission.reference(request, "admission_draft", 1),
            headers=headers,
        ),
        await admission.ledger.client.post(
            f"{admission.base}/commands/{uuid7()}/cancel",
            json=admission.reference(request, "admission_draft", 1),
            headers=headers,
        ),
    )
    assert all(response.status_code == 403 for response in responses), [
        response.text for response in responses
    ]


async def test_other_tenant_and_book_cannot_reach_history(
    admission: AdmissionWorld,
    app_pool: RuntimePool,
    world: BookingWorld,
    manager_b: FakeUser,
    idp: FakeIdp,
) -> None:
    request = uuid7()
    assert (await admission.save(request)).status_code == 200
    other = (
        f"/v1/businesses/{world.b.tenant_id}/provider-admission"
        f"/books/{admission.ledger.book}/requests/{request}"
    )
    auth = idp.bearer(manager_b.subject, email=manager_b.email)
    assert (await admission.ledger.client.get(other, headers=auth)).status_code == 404
    # Enable G in B so the write reaches the book/tenant boundary instead of
    # correctly stopping earlier at B's disabled finance gate.
    config = Config(admission.ledger.client, idp)
    await config.profile(manager_b, world.b.tenant_id, 0, [1])
    await config.publish(manager_b, world.b.tenant_id, 0, ["booking_resources", "finance"])
    assert (
        await admission.ledger.client.put(
            other, json=admission.draft(), headers={**auth, "Idempotency-Key": str(uuid7())}
        )
    ).status_code == 404
    otherbook = f"{admission.base}/books/{uuid7()}/requests/{request}"
    assert (
        await admission.ledger.client.get(otherbook, headers=admission.ledger.auth)
    ).status_code == 404
    async with tenant_transaction(app_pool, world.b.tenant_id) as conn:
        for table in ADMISSION_TABLES:
            assert (
                await (
                    await conn.execute(
                        sql.SQL("select * from gba.{} where tenant_id=%s").format(
                            sql.Identifier(table)
                        ),
                        (admission.ledger.business,),
                    )
                ).fetchall()
                == []
            )
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        async with tenant_transaction(app_pool, world.b.tenant_id) as conn:
            await conn.execute(
                "insert into gba.provider_admission_cancellations "
                "(tenant_id,actor_key,operation,idempotency_key,book_id,reque"
                "st_id,revision,cancelled_by)"
                " values (%s,%s,'admission_draft',%s,%s,%s,1,%s)",
                (
                    world.b.tenant_id,
                    f"user:{manager_b.user_id}",
                    str(uuid7()),
                    admission.ledger.book,
                    uuid7(),
                    manager_b.user_id,
                ),
            )


@pytest.mark.parametrize("space", ["\u00a0", "\u2000", "\u202f", "\u3000"])
async def test_sql_and_api_reject_unicode_spaced_credential_material(
    admission: AdmissionWorld, app_pool: RuntimePool, space: str
) -> None:
    text = "Bearer" + space + "FAKE"
    with pytest.raises(ValidationError):
        AdmissionDraftInput.model_validate(admission.draft(notes=text))
    async with tenant_transaction(app_pool, admission.ledger.business) as conn:
        assert (
            await (await conn.execute("select gba.admission_safe_text(%s,256)", (text,))).fetchone()
        ) == (False,)


async def test_same_count_transition_cannot_replace_evidence(
    admission: AdmissionWorld, app_pool: RuntimePool
) -> None:
    request = uuid7()
    saved = await admission.save(request)
    assert saved.status_code == 200, saved.text

    async def replace_evidence() -> None:
        async with tenant_transaction(app_pool, admission.ledger.business) as conn:
            await conn.execute(
                "insert into gba.provider_admission_versions "
                "(tenant_id,book_id,request_id,revision,state,provider,country,business_activity,"
                "requested_operation,assessment,account_reference,notes,evidence_count,created_by) "
                "select tenant_id,book_id,request_id,2,'submitted',provider,country,"
                "business_activity,"
                "requested_operation,assessment,account_reference,notes,evidence_count,created_by "
                "from gba.provider_admission_versions where tenant_id=%s and book_id=%s "
                "and request_id=%s and revision=1",
                (admission.ledger.business, admission.ledger.book, request),
            )
            await conn.execute(
                "insert into gba.provider_admission_evidence "
                "(tenant_id,book_id,request_id,revision,reference_no,reference) "
                "select tenant_id,book_id,request_id,2,reference_no,'FAKE-replaced-evidence' "
                "from gba.provider_admission_evidence where tenant_id=%s and book_id=%s "
                "and request_id=%s and revision=1",
                (admission.ledger.business, admission.ledger.book, request),
            )
            await conn.execute("set constraints all immediate")

    with pytest.raises(psycopg.errors.CheckViolation, match="preserves all evidence"):
        await replace_evidence()
    current = await admission.ledger.client.get(
        f"{admission.collection}/{request}", headers=admission.ledger.auth
    )
    assert current.json() == saved.json()


async def test_ordinary_words_are_not_misidentified_as_key_prefixes(
    admission: AdmissionWorld, app_pool: RuntimePool
) -> None:
    async with tenant_transaction(app_pool, admission.ledger.business) as conn:
        for text in ("risk_assessment", "TASK_REQUEST", "work_notes"):
            assert AdmissionDraftInput.model_validate(admission.draft(notes=text)).notes == text
            row = await (
                await conn.execute("select gba.admission_safe_text(%s,256)", (text,))
            ).fetchone()
            assert row == (True,)


async def test_receipt_cannot_claim_a_version_from_an_earlier_transaction(
    admission: AdmissionWorld, app_pool: RuntimePool
) -> None:
    request = uuid7()
    assert (await admission.save(request)).status_code == 200
    with pytest.raises(psycopg.errors.CheckViolation):
        async with tenant_transaction(app_pool, admission.ledger.business) as conn:
            await conn.execute(
                "insert into gba.provider_admission_receipts "
                "(tenant_id,actor_key,operation,idempotency_key,request_hash,book_id,"
                "request_id,revision,created_by) "
                "values (%s,%s,'admission_draft',%s,%s,%s,%s,1,%s)",
                (
                    admission.ledger.business,
                    f"user:{admission.ledger.user.user_id}",
                    str(uuid7()),
                    "a" * 64,
                    admission.ledger.book,
                    request,
                    admission.ledger.user.user_id,
                ),
            )


async def test_transaction_default_drift_blocks_admission(
    admission: AdmissionWorld, owner_conn: psycopg.Connection
) -> None:
    owner_conn.execute(
        "alter table gba.provider_admission_versions alter column created_transaction "
        "set default '0'::xid8"
    )
    try:
        result = await admission.ledger.client.get(
            admission.collection, headers=admission.ledger.auth
        )
        assert result.status_code == 503, result.text
    finally:
        owner_conn.execute(
            "alter table gba.provider_admission_versions alter column created_transaction "
            "set default pg_current_xact_id()"
        )


async def raw_version(
    conn: RuntimeConnection,
    admission: AdmissionWorld,
    request: UUID,
    *,
    revision: int = 2,
    state: str = "draft",
    assessment: str = "not_checked",
    provider: str = "stripe_connect",
    country: str = "US",
    evidence_count: int = 0,
) -> None:
    await conn.execute(
        "insert into gba.provider_admission_versions "
        "(tenant_id,book_id,request_id,revision,state,provider,countr"
        "y,business_activity,requested_operation,assessment,evidence_"
        "count,created_by)"
        " values (%s,%s,%s,%s,%s,%s,%s,'FAKE activity','charge',%s,%s,%s)",
        (
            admission.ledger.business,
            admission.ledger.book,
            request,
            revision,
            state,
            provider,
            country,
            assessment,
            evidence_count,
            admission.ledger.user.user_id,
        ),
    )


@pytest.mark.parametrize(
    "bad",
    [
        {"revision": 3},
        {"state": "approved"},
        {"assessment": "test_access"},
        {"assessment": "approved"},
        {"provider": "other"},
        {"country": "USA"},
        {"state": "submitted"},
    ],
)
async def test_sql_rejects_invalid_transitions_and_positive_assessment(
    admission: AdmissionWorld, app_pool: RuntimePool, bad: Mapping[str, object]
) -> None:
    request = uuid7()
    assert (await admission.save(request, evidence_references=[])).status_code == 200
    with pytest.raises(psycopg.errors.CheckViolation):
        async with tenant_transaction(app_pool, admission.ledger.business) as conn:
            # Inputs intentionally bypass Pydantic to exercise the SQL boundary.
            await conn.execute(
                "insert into gba.provider_admission_versions "
                "(tenant_id,book_id,request_id,revision,state,provider,countr"
                "y,business_activity,requested_operation,assessment,evidence_"
                "count,created_by)"
                " values (%s,%s,%s,%s,%s,%s,%s,'FAKE activity','charge',%s,0,%s)",
                (
                    admission.ledger.business,
                    admission.ledger.book,
                    request,
                    bad.get("revision", 2),
                    bad.get("state", "draft"),
                    bad.get("provider", "stripe_connect"),
                    bad.get("country", "US"),
                    bad.get("assessment", "not_checked"),
                    admission.ledger.user.user_id,
                ),
            )


async def test_sql_cannot_append_evidence_later_or_mutate_history(
    admission: AdmissionWorld, app_pool: RuntimePool, owner_conn: psycopg.Connection
) -> None:
    request = uuid7()
    assert (await admission.save(request)).status_code == 200
    with pytest.raises(psycopg.errors.CheckViolation):
        async with tenant_transaction(app_pool, admission.ledger.business) as conn:
            await conn.execute(
                "insert into gba.provider_admission_evidence "
                "(tenant_id,book_id,request_id,revision,reference_no,reference) "
                "values (%s,%s,%s,1,2,'FAKE late')",
                (admission.ledger.business, admission.ledger.book, request),
            )
    for table in ADMISSION_TABLES:
        with (  # noqa: PT012 - the immutable trigger refuses an owner transaction
            owner_tenant_transaction(owner_conn, admission.ledger.business),
            pytest.raises(psycopg.errors.CheckViolation),
            owner_conn.transaction(),
        ):
            # cancellation has no rows yet; create one below before its mutation check.
            if table == "provider_admission_cancellations":
                owner_conn.execute(
                    "insert into gba.provider_admission_cancellations "
                    "(tenant_id,actor_key,operation,idempotency_key,book_id,reque"
                    "st_id,revision,cancelled_by)"
                    " values (%s,%s,'admission_draft',%s,%s,%s,1,%s)",
                    (
                        admission.ledger.business,
                        f"user:{admission.ledger.user.user_id}",
                        str(uuid7()),
                        admission.ledger.book,
                        uuid7(),
                        admission.ledger.user.user_id,
                    ),
                )
            owner_conn.execute(
                sql.SQL("delete from gba.{} where tenant_id=%s").format(sql.Identifier(table)),
                (admission.ledger.business,),
            )
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        async with tenant_transaction(app_pool, admission.ledger.business) as conn:
            await conn.execute(
                "insert into gba.provider_admission_versions "
                "(tenant_id,book_id,request_id,revision,state,provider,countr"
                "y,business_activity,requested_operation,assessment,evidence_"
                "count,created_by,charge_enabled)"
                " values "
                "(%s,%s,%s,2,'draft','stripe_connect','US','FAKE','charge','not_checked',0,%s,true)",
                (
                    admission.ledger.business,
                    admission.ledger.book,
                    request,
                    admission.ledger.user.user_id,
                ),
            )


@pytest.mark.parametrize(
    "damage",
    ["trigger", "default", "execute", "capability_grant", "force_rls", "policy", "helper_source"],
)
async def test_guard_damage_blocks_only_admission(
    admission: AdmissionWorld, owner_conn: psycopg.Connection, damage: str
) -> None:
    mutations = {
        "trigger": (
            "alter table gba.provider_admission_versions disable trigger "
            "provider_admission_versions_next",
            "alter table gba.provider_admission_versions enable trigger "
            "provider_admission_versions_next",
        ),
        "default": (
            "alter table gba.provider_admission_versions alter column "
            "charge_enabled set default true",
            "alter table gba.provider_admission_versions alter column "
            "charge_enabled set default false",
        ),
        "execute": (
            "revoke execute on function gba.admission_safe_text(text,integer) from gba_runtime",
            "grant execute on function gba.admission_safe_text(text,integer) to gba_runtime",
        ),
        "capability_grant": (
            "grant insert (charge_enabled) on gba.provider_admission_versions to gba_runtime",
            "revoke insert (charge_enabled) on gba.provider_admission_versions from gba_runtime",
        ),
        "force_rls": (
            "alter table gba.provider_admission_versions no force row level security",
            "alter table gba.provider_admission_versions force row level security",
        ),
        "policy": (
            "create policy admission_untrusted_read on "
            "gba.provider_admission_versions using (true)",
            "drop policy admission_untrusted_read on gba.provider_admission_versions",
        ),
        "helper_source": (
            "create or replace function gba.admission_safe_text(value text, "
            "maximum integer) returns boolean language sql immutable parallel"
            " safe as $$ select true $$",
            None,
        ),
    }
    change, restore = mutations[damage]
    original = owner_conn.execute(
        "select pg_get_functiondef('gba.admission_safe_text(text,integer)'::regprocedure)"
    ).fetchone()
    owner_conn.execute(change)
    try:
        read = await admission.ledger.client.get(
            admission.collection, headers=admission.ledger.auth
        )
        saved = await admission.save(uuid7())
        assert read.status_code == saved.status_code == 503, (read.text, saved.text)
        assert (
            await admission.ledger.client.get(admission.ledger.base, headers=admission.ledger.auth)
        ).status_code == 200
    finally:
        assert original is not None
        owner_conn.execute(restore if restore is not None else original[0])
