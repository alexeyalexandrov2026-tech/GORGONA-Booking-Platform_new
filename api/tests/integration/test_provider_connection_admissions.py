"""K0b (E-03): only an owner-recorded admission lets a connection receive, decide and move money.

Synthetic only: no provider account, real key, worker schedule or money outside the test book.
"""

import asyncio
from uuid import uuid7

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict

from gorgona_booking.db import cli
from gorgona_booking.db.pool import RuntimeConnection, RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import (
    AdmissionState,
    owner_tenant_transaction,
    record_receipt_admission,
)
from gorgona_booking.errors import DatabaseUnavailableError
from gorgona_booking.providers import authenticated_receipts as service
from gorgona_booking.providers import receipt_worker as worker
from gorgona_booking.providers.authenticated_receipts import ReceiptAuthority
from gorgona_booking.providers.inbox import ReceiptBindingRejectedError, ReceiptResult
from gorgona_booking.providers.stripe_contracts import SignedStripeEvent
from tests.integration import test_provider_event_inbox as archive
from tests.integration import test_provider_payments as paid
from tests.integration import test_provider_receipt_attestations as attested
from tests.integration import test_provider_receipt_decisions as decided
from tests.integration import test_provider_receipt_routing as routing
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.test_provider_receipt_attestations import Routed

pytestmark = pytest.mark.anyio
client = paid.client
idp = paid.idp
manager_a = paid.manager_a
manager_b = paid.manager_b
enabled = paid.enabled
invoices = paid.invoices
payments = paid.payments
credits = paid.credits
inbox = paid.inbox
writer_pool = paid.writer_pool
routed = paid.routed
worker_pool = paid.worker_pool
money = paid.money


def admit(
    owner_conn: psycopg.Connection,
    scope: Routed,
    state: AdmissionState = "test_access",
    *,
    account_id: str | None = None,
    charge: bool = True,
    refund: bool = True,
) -> int:
    return record_receipt_admission(
        owner_conn,
        scope.tenant_id,
        scope.connection_id,
        state=state,
        account_id=scope.policy.account_id if account_id is None else account_id,
        charge=charge,
        refund=refund,
        evidence="FAKE synthetic admission",
    )


@pytest.fixture
def unadmitted(inbox: archive.Inbox, owner_conn: psycopg.Connection) -> Routed:
    return attested.provision(
        owner_conn,
        tenant_id=inbox.ledger.business,
        connection_id=inbox.connection,
        book_id=inbox.ledger.book,
        namespace=inbox.namespace,
        admit=False,
    )


async def history(pool: RuntimePool, scope: Routed) -> list[tuple[object, ...]]:
    async with tenant_transaction(pool, scope.tenant_id) as conn:
        rows = await (
            await conn.execute(
                "select revision,state,environment,charge_allowed,refund_allowed,currency,"
                "account_id,recorded_by from gba.provider_connection_admissions "
                "where connection_id=%s order by revision",
                (scope.connection_id,),
            )
        ).fetchall()
    return [tuple(row) for row in rows]


async def test_the_owner_records_revisions_that_stay_permanent(
    routed: Routed,
    owner_conn: psycopg.Connection,
    app_pool: RuntimePool,
    test_database: ProvisionedDatabase,
) -> None:
    owner = str(conninfo_to_dict(test_database.owner_dsn)["user"])
    assert admit(owner_conn, routed, charge=True, refund=False) == 2
    assert admit(owner_conn, routed, "suspended") == 3
    assert await history(app_pool, routed) == [
        (1, "test_access", "test", True, True, "USD", "acct_FAKEreceipt", owner),
        (2, "test_access", "test", True, False, "USD", "acct_FAKEreceipt", owner),
        (3, "suspended", "test", True, True, "USD", "acct_FAKEreceipt", owner),
    ]
    for statement in (
        "update gba.provider_connection_admissions set state='test_access'",
        "delete from gba.provider_connection_admissions",
    ):
        with (
            pytest.raises(psycopg.errors.CheckViolation),
            owner_tenant_transaction(owner_conn, routed.tenant_id),
        ):
            owner_conn.execute(statement)
    assert len(await history(app_pool, routed)) == 3


@pytest.mark.parametrize(
    "case",
    [
        "wrong_account",
        "revoked",
        "first_suspended",
        "no_operation",
        "unscoped",
        "branch",
        "production",
        "other_currency",
    ],
)
async def test_an_admission_that_does_not_fit_is_refused(
    routed: Routed,
    owner_conn: psycopg.Connection,
    app_pool: RuntimePool,
    case: str,
) -> None:
    scope = routed
    if case == "first_suspended":
        # A connection that has no admission yet: its first revision must be test access.
        connection = routing.second_connection(owner_conn, routed)
        scope = Routed(
            tenant_id=routed.tenant_id,
            connection_id=connection,
            book_id=routed.book_id,
            ingress_id=routed.ingress_id,
            verification_config_id=routed.verification_config_id,
            secret_ref=routed.secret_ref,
            policy=routed.policy.model_copy(update={"account_id": "acct_FAKEsecond"}),
            key=routed.key,
        )
    before = await history(app_pool, routed)
    if case == "revoked":
        with owner_tenant_transaction(owner_conn, routed.tenant_id):
            owner_conn.execute(
                "update gba.provider_receipt_connections set revoked=true,"
                "revoked_reason='retired' where id=%s",
                (routed.connection_id,),
            )
    if case in ("wrong_account", "revoked", "first_suspended", "no_operation"):
        with pytest.raises(psycopg.errors.CheckViolation):
            admit(
                owner_conn,
                scope,
                "suspended" if case == "first_suspended" else "test_access",
                account_id="acct_FAKEother" if case == "wrong_account" else scope.policy.account_id,
                charge=case != "no_operation",
                refund=case != "no_operation",
            )
    else:
        column, value = {
            "production": ("environment", "live"),
            "other_currency": ("currency", "EUR"),
        }.get(case, ("environment", "test"))

        def insert() -> None:
            with owner_conn.transaction():
                if case != "unscoped":
                    owner_conn.execute(
                        "select set_config('gba.tenant_id',%s,true)", (str(routed.tenant_id),)
                    )
                if case == "branch":
                    owner_conn.execute(
                        "select set_config('gba.location_id',%s,true)", (str(uuid7()),)
                    )
                owner_conn.execute(
                    "insert into gba.provider_connection_admissions (tenant_id,connection_id,"
                    f"state,charge_allowed,refund_allowed,account_id,evidence,{column}) "
                    "values (%s,%s,'test_access',true,true,'acct_FAKEreceipt','FAKE',%s)",
                    (routed.tenant_id, routed.connection_id, value),
                )

        with pytest.raises(psycopg.errors.CheckViolation):
            insert()
    if case != "revoked":
        assert await history(app_pool, routed) == before


_WRITES = (
    "insert into gba.provider_connection_admissions (tenant_id,connection_id,state,"
    "charge_allowed,refund_allowed,account_id,evidence) values "
    "(%(tenant)s,%(connection)s,'test_access',true,true,'acct_FAKEreceipt','FAKE')",
    "update gba.provider_connection_admissions set state='suspended'",
    "delete from gba.provider_connection_admissions",
    "truncate gba.provider_connection_admissions",
)


@pytest.mark.parametrize("statement", _WRITES)
@pytest.mark.parametrize("role", ["runtime", "writer", "worker"])
async def test_no_application_role_can_record_or_change_an_admission(
    routed: Routed,
    app_pool: RuntimePool,
    writer_pool: RuntimePool,
    worker_pool: RuntimePool,
    role: str,
    statement: str,
) -> None:
    pool = {"runtime": app_pool, "writer": writer_pool, "worker": worker_pool}[role]
    params = {"tenant": routed.tenant_id, "connection": routed.connection_id}

    async def write() -> None:
        async with tenant_transaction(pool, routed.tenant_id) as conn:
            await conn.execute(statement, params if "%(" in statement else None)

    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        await write()


async def test_the_owner_command_records_an_admission_without_printing_a_secret(
    unadmitted: Routed,
    app_pool: RuntimePool,
    test_database: ProvisionedDatabase,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("GBA_MIGRATION_DATABASE_URL", test_database.owner_dsn)
    cli.main(
        [
            "admit-receipt-connection",
            "--tenant",
            str(unadmitted.tenant_id),
            "--connection",
            str(unadmitted.connection_id),
            "--account",
            unadmitted.policy.account_id,
            "--state",
            "test_access",
            "--operations",
            "charge",
            "--evidence",
            "FAKE owner command test",
        ]
    )
    shown = capsys.readouterr()
    assert "revision 1, test_access" in shown.out
    password = str(conninfo_to_dict(test_database.owner_dsn)["password"])
    assert password not in shown.out + shown.err
    rows = await history(app_pool, unadmitted)
    assert [(row[0], row[1], row[3], row[4]) for row in rows] == [(1, "test_access", True, False)]


async def test_an_unadmitted_or_suspended_connection_attests_nothing(
    unadmitted: Routed,
    owner_conn: psycopg.Connection,
    writer_pool: RuntimePool,
    app_pool: RuntimePool,
) -> None:
    with pytest.raises(ReceiptBindingRejectedError):
        await attested.receive(writer_pool, unadmitted, attested.delivery())
    assert admit(owner_conn, unadmitted) == 1
    await attested.receive(writer_pool, unadmitted, attested.delivery())
    assert admit(owner_conn, unadmitted, "suspended") == 2
    with pytest.raises(ReceiptBindingRejectedError):
        await attested.receive(writer_pool, unadmitted, attested.delivery(amount=2000))
    # K5r (review R2): deliveries refused while suspended are lost to it, so the suspension is
    # final; a new connection is provisioned instead of re-admitting this one.
    with pytest.raises(psycopg.errors.CheckViolation, match="suspended"):
        admit(owner_conn, unadmitted)
    with pytest.raises(ReceiptBindingRejectedError):
        await attested.receive(writer_pool, unadmitted, attested.delivery())
    rows = await attested.attestations(app_pool, unadmitted.tenant_id)
    assert len(rows) == 1


async def test_sql_alone_cannot_attest_or_decide_for_a_suspended_connection(
    routed: Routed,
    owner_conn: psycopg.Connection,
    writer_pool: RuntimePool,
    worker_pool: RuntimePool,
) -> None:
    received = await attested.receive(writer_pool, routed, attested.delivery())
    admit(owner_conn, routed, "suspended")

    async def attest_variant() -> None:
        async with tenant_transaction(writer_pool, routed.tenant_id) as conn:
            await conn.execute(
                "insert into gba.provider_event_attestations "
                "(tenant_id,event_id,delivery_sha256,verification_config_id) "
                "select tenant_id,event_id,delivery_sha256,%s from gba.provider_event_deliveries "
                "where event_id=%s",
                (routed.verification_config_id, received.event_id),
            )

    async def decide() -> None:
        holder = uuid7()
        async with tenant_transaction(worker_pool, routed.tenant_id) as conn:
            generation = await worker.claim(
                conn, routed.tenant_id, received.event_id, holder=holder, lease_seconds=60
            )
            assert generation is not None
            await worker.decide(
                conn, routed.tenant_id, received.event_id, holder=holder, generation=generation
            )

    for attempt in (attest_variant, decide):
        with pytest.raises(psycopg.errors.CheckViolation):
            await attempt()


async def test_the_worker_leaves_a_suspended_connection_undecided(
    routed: Routed,
    owner_conn: psycopg.Connection,
    writer_pool: RuntimePool,
    worker_pool: RuntimePool,
) -> None:
    await decided.receive_all(writer_pool, routed, decided.stripe("payment_intent.succeeded"))
    admit(owner_conn, routed, "suspended")
    assert await worker.process_batch(worker_pool, tenant_id=routed.tenant_id) == []
    assert await decided.decisions(worker_pool, routed.tenant_id) == {}
    # K5r (review R2): the suspension is final, so its events never become decidable again.
    with pytest.raises(psycopg.errors.CheckViolation, match="suspended"):
        admit(owner_conn, routed)
    assert await worker.process_batch(worker_pool, tenant_id=routed.tenant_id) == []
    assert await decided.decisions(worker_pool, routed.tenant_id) == {}


@pytest.mark.parametrize("admission", ["suspended", "refund_only"])
async def test_money_needs_an_admission_for_its_operation(
    money: paid.Money,
    owner_conn: psycopg.Connection,
    app_pool: RuntimePool,
    admission: str,
) -> None:
    obligation, settlement = await money.reserved()
    await money.observe(paid.event("payment_intent.succeeded"))
    operation = await money.operation()
    if admission == "suspended":
        admit(owner_conn, money.routed, "suspended")
    else:
        admit(owner_conn, money.routed, charge=False, refund=True)
    refused = await money.apply(settlement, operation, [(obligation, "10.00")])
    assert paid.error(refused)[:2] == (409, "PROVIDER_OPERATION_NOT_READY")
    assert paid.error(refused)[2]["reason"] == "not_admitted"
    assert await money.count(app_pool, "external_payments") == 0
    if admission == "suspended":
        # K5r (review R2): a suspension is final; the operation stays without money.
        with pytest.raises(psycopg.errors.CheckViolation, match="suspended"):
            admit(owner_conn, money.routed)
        return
    admit(owner_conn, money.routed)
    applied = await money.apply(settlement, operation, [(obligation, "10.00")])
    assert applied.status_code == 200, applied.text


async def test_a_suspension_waits_for_a_receipt_in_flight_then_refuses_the_next(
    routed: Routed,
    writer_pool: RuntimePool,
    app_pool: RuntimePool,
    test_database: ProvisionedDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    held, release = asyncio.Event(), asyncio.Event()
    pids: list[int] = []
    original = service._attest_event

    async def paused(
        conn: RuntimeConnection,
        authority: ReceiptAuthority,
        event: SignedStripeEvent,
        result: ReceiptResult,
    ) -> None:
        await original(conn, authority, event, result)
        pids.append(await decided.backend(conn))
        held.set()
        await release.wait()

    monkeypatch.setattr(service, "_attest_event", paused)
    receipt = asyncio.create_task(attested.receive(writer_pool, routed, attested.delivery()))
    suspension = None
    monitor = await psycopg.AsyncConnection.connect(
        test_database.admin_dsn, dbname=test_database.name, autocommit=True
    )

    def suspend() -> int:
        with psycopg.connect(test_database.owner_dsn, autocommit=True) as owner:
            return admit(owner, routed, "suspended")

    try:
        await asyncio.wait_for(held.wait(), 15)
        suspension = asyncio.create_task(asyncio.to_thread(suspend))
        await decided.blocked_by(monitor, pids[0], "insert into gba.provider_connection_admissions")
        assert not suspension.done()
        release.set()
        result = await asyncio.wait_for(receipt, 15)
        assert await asyncio.wait_for(suspension, 15) == 2
    finally:
        release.set()
        for task in (receipt, suspension):
            if task is not None and not task.done():
                task.cancel()
        await asyncio.gather(
            *(task for task in (receipt, suspension) if task is not None), return_exceptions=True
        )
        await monitor.close()
    assert result.disposition == "recorded"
    monkeypatch.undo()
    with pytest.raises(ReceiptBindingRejectedError):
        await attested.receive(writer_pool, routed, attested.delivery(amount=2000))


async def test_a_disabled_admission_gate_stops_receipts(
    routed: Routed,
    owner_conn: psycopg.Connection,
    writer_pool: RuntimePool,
) -> None:
    owner_conn.execute(
        "alter table gba.provider_event_attestations "
        "disable trigger provider_event_attestations_admission"
    )
    try:
        with pytest.raises(DatabaseUnavailableError):
            await attested.receive(writer_pool, routed, attested.delivery())
    finally:
        owner_conn.execute(
            "alter table gba.provider_event_attestations "
            "enable trigger provider_event_attestations_admission"
        )
