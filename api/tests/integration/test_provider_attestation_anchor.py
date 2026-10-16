"""K1d R1: an attested verification config must exist; synthetic data, no provider account."""

from uuid import uuid7

import psycopg
import pytest

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.providers.inbox import record_event
from tests.integration import test_provider_event_inbox as archive
from tests.integration import test_provider_receipt_attestations as attested

pytestmark = pytest.mark.anyio
client = archive.client
idp = archive.idp
manager_a = archive.manager_a
manager_b = archive.manager_b
enabled = archive.enabled
inbox = archive.inbox
writer_pool = attested.writer_pool


async def test_writer_cannot_attest_under_an_unknown_verification_config(
    inbox: archive.Inbox,
    writer_pool: RuntimePool,
    app_pool: RuntimePool,
) -> None:
    event = inbox.event()

    async def attest() -> None:
        async with tenant_transaction(writer_pool, inbox.ledger.business) as conn:
            result = await record_event(conn, inbox.connection, event)
            await conn.execute(
                "insert into gba.provider_event_attestations "
                "(tenant_id,event_id,delivery_sha256,verification_config_id) values (%s,%s,%s,%s)",
                (inbox.ledger.business, result.event_id, event.delivery_sha256, uuid7()),
            )

    with pytest.raises(psycopg.errors.CheckViolation):
        await attest()
    assert await archive.counts(app_pool, inbox) == (0, 0)
