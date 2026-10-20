"""K0b (E-02, E-05): the ingress and worker run as processes; synthetic signed events only.

The ingress listens on an ephemeral 127.0.0.1 port; its key is read from a named variable of a
test environment mapping. No provider account or real key is used, and no secret, ingress ID or
payload may reach a log or the console.
"""

import asyncio
import logging
import secrets
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import httpx
import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from gorgona_booking.db.bootstrap import BootstrapSpec, bootstrap
from gorgona_booking.db.pool import RuntimePool
from gorgona_booking.db.provisioning import owner_tenant_transaction
from gorgona_booking.providers.authenticated_receipts import UnsafeReceiptWriterRoleError
from gorgona_booking.providers.receipt_processes import (
    ingress_settings,
    run_worker,
    serve_ingress,
    worker_settings,
)
from gorgona_booking.providers.receipt_worker import UnsafeReceiptWorkerRoleError
from tests.integration import test_provider_receipt_attestations as attested
from tests.integration import test_provider_receipt_decisions as decided
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.test_provider_connection_admissions import admit
from tests.integration.test_provider_receipt_attestations import Routed
from tests.unit import test_stripe_event_boundary as signed

pytestmark = pytest.mark.anyio
client = attested.client
idp = attested.idp
manager_a = attested.manager_a
manager_b = attested.manager_b
enabled = attested.enabled
inbox = attested.inbox
routed = attested.routed
SECRET_NAME = "GBA_TEST_K0B_WEBHOOK_SECRET"
REFERENCE = "env:" + SECRET_NAME


@dataclass(frozen=True)
class Logins:
    writer: str = field(repr=False)
    worker: str = field(repr=False)


@pytest.fixture
def logins(test_database: ProvisionedDatabase) -> Logins:
    owner = conninfo_to_dict(test_database.owner_dsn)
    app = conninfo_to_dict(test_database.app_dsn)
    writer_password, worker_password = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    bootstrap(
        test_database.admin_dsn,
        BootstrapSpec(
            database=test_database.name,
            owner_role=str(owner["user"]),
            owner_password=str(owner["password"]),
            app_role=str(app["user"]),
            app_password=str(app["password"]),
            receipt_writer_role="gba_test_process_writer",
            receipt_writer_password=writer_password,
            receipt_worker_role="gba_test_process_worker",
            receipt_worker_password=worker_password,
        ),
    )
    return Logins(
        writer=make_conninfo(
            test_database.app_dsn, user="gba_test_process_writer", password=writer_password
        ),
        worker=make_conninfo(
            test_database.app_dsn, user="gba_test_process_worker", password=worker_password
        ),
    )


@pytest.fixture
def keyed(routed: Routed, owner_conn: psycopg.Connection) -> Routed:
    """The routed connection rotated to a config whose key lives in a named variable."""
    with owner_tenant_transaction(owner_conn, routed.tenant_id):
        owner_conn.execute(
            "update gba.provider_verification_configs set revoked=true,revoked_reason='rotation' "
            "where id=%s",
            (routed.verification_config_id,),
        )
    config, version = attested.provision_config(
        owner_conn, routed.tenant_id, routed.connection_id, REFERENCE
    )
    assert version == 2
    return Routed(
        tenant_id=routed.tenant_id,
        connection_id=routed.connection_id,
        book_id=routed.book_id,
        ingress_id=routed.ingress_id,
        verification_config_id=config,
        secret_ref=REFERENCE,
        policy=routed.policy,
        key=attested.fake_key(),
    )


def environment(logins: Logins, scope: Routed) -> dict[str, str]:
    return {
        "GBA_RECEIPT_WRITER_DATABASE_URL": logins.writer,
        "GBA_RECEIPT_WORKER_DATABASE_URL": logins.worker,
        "GBA_RECEIPT_SECRET_REFS": REFERENCE,
        SECRET_NAME: scope.key.get_secret_value(),
        "GBA_RECEIPT_PORT": "0",
    }


class _Ingress:
    def __init__(self, values: dict[str, str]) -> None:
        self.values = values
        self.ports: list[int] = []
        self.stop = asyncio.Event()
        self.task: asyncio.Task[None] | None = None


@pytest.fixture
async def started(logins: Logins, keyed: Routed) -> AsyncIterator[_Ingress]:
    process = _Ingress(environment(logins, keyed))
    process.task = asyncio.create_task(
        serve_ingress(
            ingress_settings(process.values), started=process.ports.append, stop=process.stop
        )
    )
    async with asyncio.timeout(15):
        while not process.ports:
            if process.task.done():
                await process.task
            await asyncio.sleep(0.01)
    try:
        yield process
    finally:
        process.stop.set()
        await asyncio.wait_for(process.task, 30)


async def deliver(port: int, scope: Routed, raw: bytes) -> httpx.Response:
    async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as session:
        return await session.post(
            f"/v1/provider-events/stripe/{scope.ingress_id}",
            content=raw,
            headers={
                # The running ingress checks the signature time against the real clock.
                "Stripe-Signature": signed.signed(raw, scope.key, int(time.time())),
                "Content-Type": "application/json; charset=utf-8",
            },
        )


async def test_the_processes_receive_and_decide_a_signed_payment_once(
    started: _Ingress,
    keyed: Routed,
    app_pool: RuntimePool,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    caplog.set_level(logging.DEBUG)
    raw = decided.stripe("payment_intent.succeeded")
    port = started.ports[0]
    for _ in range(2):  # a retried delivery is a duplicate, not a second fact (E-05)
        answer = await deliver(port, keyed, raw)
        assert (answer.status_code, answer.content) == (200, b'{"received":true}')
    settings = worker_settings(started.values, ["--once"])
    # The shared test database may hold other companies' undecided events; count this one's.
    assert await run_worker(settings) >= 1
    assert len(await decided.decisions(app_pool, keyed.tenant_id)) == 1
    await run_worker(settings)
    assert len(await decided.decisions(app_pool, keyed.tenant_id)) == 1
    output = capsys.readouterr()
    # The test's own HTTP client (httpx, httpcore) logs the URL it calls; the processes must not.
    served = [
        f"{record.getMessage()} {record.__dict__}"  # the message and every extra field
        for record in caplog.records
        if not record.name.startswith(("httpx", "httpcore"))
    ]
    shown = "\n".join(served) + output.out + output.err
    assert keyed.key.get_secret_value() not in shown
    assert str(keyed.ingress_id) not in shown
    assert "payment_intent" not in shown


async def test_the_worker_loop_stops_cleanly_between_batches(logins: Logins, keyed: Routed) -> None:
    stop = asyncio.Event()
    settings = worker_settings(environment(logins, keyed), ["--interval", "1"])
    task = asyncio.create_task(run_worker(settings, stop=stop))
    await asyncio.sleep(1.5)
    assert not task.done()
    stop.set()
    assert await asyncio.wait_for(task, 10) >= 0


async def test_each_process_refuses_the_other_login(logins: Logins, keyed: Routed) -> None:
    values = environment(logins, keyed)
    crossed = {
        **values,
        "GBA_RECEIPT_WRITER_DATABASE_URL": logins.worker,
        "GBA_RECEIPT_WORKER_DATABASE_URL": logins.writer,
    }
    ports: list[int] = []
    with pytest.raises(UnsafeReceiptWriterRoleError):
        await serve_ingress(ingress_settings(crossed), started=ports.append)
    assert ports == []
    with pytest.raises(UnsafeReceiptWorkerRoleError):
        await run_worker(worker_settings(crossed, ["--once"]))


async def test_an_unadmitted_connection_is_refused_by_the_running_ingress(
    started: _Ingress, keyed: Routed, owner_conn: psycopg.Connection, app_pool: RuntimePool
) -> None:
    admit(owner_conn, keyed, "suspended")
    answer = await deliver(started.ports[0], keyed, decided.stripe("payment_intent.succeeded"))
    assert answer.status_code == 400
    assert answer.content == (
        b'{"error":{"code":"PROVIDER_RECEIPT_REFUSED","message":"Provider receipt was refused"}}'
    )
    assert await attested.attestations(app_pool, keyed.tenant_id) == []
