"""Owner-induced schema drift must stop receipt writes before storage is touched."""

import re
from importlib import resources

import psycopg
import pytest

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.provider_receipt_guard import assert_provider_receipt_ready
from gorgona_booking.errors import DatabaseUnavailableError
from tests.integration import test_provider_event_inbox as shared

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
manager_b = shared.manager_b
enabled = shared.enabled
inbox = shared.inbox

_DROP = "drop trigger provider_event_inbox_check on gba.provider_event_inbox;"
_TRIGGER = (
    "create trigger provider_event_inbox_check before insert on gba.provider_event_inbox "
    "for each row "
)
_RESTORE = _DROP + _TRIGGER + "execute function gba.check_provider_receipt();"
_LEDGER = (resources.files("gorgona_booking.db") / "migrations" / "0020_ledger.sql").read_text(
    encoding="utf-8"
)
_IMMUTABLE = re.findall(
    r"create function gba\.reject_ledger_mutation\(\).*?\$\$;", _LEDGER, re.DOTALL
)[0].replace("create function", "create or replace function", 1)


@pytest.mark.parametrize(
    ("damage", "repair"),
    [
        pytest.param(
            "create schema receipt_guard_review;"
            "create function receipt_guard_review.check_provider_receipt() returns trigger "
            "language plpgsql as $$ begin return new; end $$;"
            + _DROP
            + _TRIGGER
            + "execute function receipt_guard_review.check_provider_receipt();",
            _RESTORE + "drop schema receipt_guard_review cascade;",
            id="shadow-trigger-function",
        ),
        pytest.param(
            _DROP + _TRIGGER + "when (false) execute function gba.check_provider_receipt();",
            _RESTORE,
            id="conditional-trigger",
        ),
        pytest.param(
            _DROP + _TRIGGER + "execute function gba.check_provider_receipt('unexpected');",
            _RESTORE,
            id="trigger-arguments",
        ),
        pytest.param(
            "create or replace function gba.reject_ledger_mutation() returns trigger "
            "language plpgsql as $$ begin return new; end $$;",
            _IMMUTABLE,
            id="changed-shared-immutable-function",
        ),
        pytest.param(
            "create schema receipt_guard_review;"
            "alter table gba.ledger_books set schema receipt_guard_review;",
            "alter table receipt_guard_review.ledger_books set schema gba;"
            "drop schema receipt_guard_review;",
            id="shadow-fk-parent",
        ),
        pytest.param(
            "grant select(facts) on gba.provider_event_inbox to public;",
            "revoke select(facts) on gba.provider_event_inbox from public;",
            id="public-column-grant",
        ),
    ],
)
async def test_receipt_guard_binds_approved_objects_and_complete_trigger_shape(
    inbox: shared.Inbox,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
    damage: str,
    repair: str,
) -> None:
    async with tenant_transaction(app_pool, inbox.ledger.business) as conn:
        await assert_provider_receipt_ready(conn)
    owner_conn.execute(damage.encode())
    try:
        with pytest.raises(DatabaseUnavailableError):
            await shared.receive(app_pool, inbox, inbox.event())
    finally:
        owner_conn.execute(repair.encode())
        async with tenant_transaction(app_pool, inbox.ledger.business) as conn:
            await assert_provider_receipt_ready(conn)
    assert await shared.counts(app_pool, inbox) == (0, 0)
