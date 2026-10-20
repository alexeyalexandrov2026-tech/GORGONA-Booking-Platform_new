"""K0b anchor (E-03): a connection the owner never admitted attests nothing; synthetic only.

Self-contained on purpose: it uses only the K1d routed receipt, so it runs on the code before
K0b and shows the gap there.
"""

import secrets
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import uuid7

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from pydantic import SecretStr

from gorgona_booking.db.bootstrap import BootstrapSpec, bootstrap
from gorgona_booking.db.pool import RuntimePool, create_runtime_pool, tenant_transaction
from gorgona_booking.db.provisioning import owner_tenant_transaction
from gorgona_booking.providers.authenticated_receipts import receive_routed_receipt
from gorgona_booking.providers.inbox import ReceiptBindingRejectedError
from tests.integration import test_provider_event_inbox as archive
from tests.integration.conftest import ProvisionedDatabase
from tests.unit import test_stripe_event_boundary as signed

pytestmark = pytest.mark.anyio
client = archive.client
idp = archive.idp
manager_a = archive.manager_a
manager_b = archive.manager_b
enabled = archive.enabled
inbox = archive.inbox
ANCHOR_WRITER = "gba_test_admission_anchor_writer"


@pytest.fixture
async def anchor_writer(test_database: ProvisionedDatabase) -> AsyncIterator[RuntimePool]:
    owner = conninfo_to_dict(test_database.owner_dsn)
    app = conninfo_to_dict(test_database.app_dsn)
    password = secrets.token_urlsafe(32)
    bootstrap(
        test_database.admin_dsn,
        BootstrapSpec(
            database=test_database.name,
            owner_role=str(owner["user"]),
            owner_password=str(owner["password"]),
            app_role=str(app["user"]),
            app_password=str(app["password"]),
            receipt_writer_role=ANCHOR_WRITER,
            receipt_writer_password=password,
        ),
    )
    pool = create_runtime_pool(
        make_conninfo(test_database.app_dsn, user=ANCHOR_WRITER, password=password)
    )
    await pool.open(wait=True)
    try:
        yield pool
    finally:
        await pool.close()


async def test_a_connection_without_an_owner_admission_attests_nothing(
    inbox: archive.Inbox,
    owner_conn: psycopg.Connection,
    anchor_writer: RuntimePool,
    app_pool: RuntimePool,
) -> None:
    tenant, reference = inbox.ledger.business, "test:k0b-" + uuid7().hex
    ingress = uuid7()
    with owner_tenant_transaction(owner_conn, tenant):
        owner_conn.execute(
            "insert into gba.provider_verification_configs "
            "(tenant_id,id,connection_id,secret_ref) values (%s,%s,%s,%s)",
            (tenant, uuid7(), inbox.connection, reference),
        )
        owner_conn.execute(
            "insert into gba.provider_receipt_routes (ingress_id,tenant_id,connection_id) "
            "values (%s,%s,%s)",
            (ingress, tenant, inbox.connection),
        )
    key = SecretStr("whsec_" + secrets.token_urlsafe(32))
    value = signed.event("payment_intent.succeeded")
    value["account"] = "acct_FAKEreceipt"
    raw = signed.body(value)
    with pytest.raises(ReceiptBindingRejectedError):
        await receive_routed_receipt(
            anchor_writer,
            ingress,
            raw,
            signed.signed(raw, key),
            key_store={reference: key},
            now=datetime.fromtimestamp(signed.NOW, UTC),
        )
    async with tenant_transaction(app_pool, tenant) as conn:
        row = await (
            await conn.execute("select count(*) from gba.provider_event_attestations")
        ).fetchone()
    assert row == (0,)
