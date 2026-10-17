"""K1g (review IR-05): role topology, table/function ACLs and context functions guard receipts."""

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.provider_receipt_guard import assert_provider_receipt_ready
from gorgona_booking.errors import DatabaseUnavailableError
from gorgona_booking.providers.authenticated_receipts import UnsafeReceiptWriterRoleError
from tests.integration import test_provider_event_inbox as archive
from tests.integration import test_provider_receipt_attestations as attested
from tests.integration import test_provider_receipt_routing as routing
from tests.integration.conftest import ProvisionedDatabase

pytestmark = pytest.mark.anyio
client = attested.client
idp = attested.idp
manager_a = attested.manager_a
manager_b = attested.manager_b
enabled = attested.enabled
inbox = attested.inbox
writer_pool = attested.writer_pool
routed = attested.routed
Routed = attested.Routed

_LOCATION = (
    "create or replace function gba.current_location_id() returns uuid "
    "language sql stable parallel safe as $$\n"
    "    select nullif(pg_catalog.current_setting('gba.location_id', true), '')::uuid\n$$"
)
_THIRD = "create role gba_k1g_third nologin"

# (id, damage, repair); "{app}" is the runtime login of the test database.
_DRIFT = [
    (
        "runtime-login-in-writer-group",
        ["grant gba_receipt_writer to {app}"],
        ["revoke gba_receipt_writer from {app}"],
    ),
    (
        "writer-group-has-parent",
        ["create role gba_k1g_parent nologin", "grant gba_k1g_parent to gba_receipt_writer"],
        ["drop role gba_k1g_parent"],
    ),
    (
        "bypassrls-writer-member",
        [
            "create role gba_k1g_bypass nologin bypassrls",
            "grant gba_receipt_writer to gba_k1g_bypass",
        ],
        ["drop role gba_k1g_bypass"],
    ),
    (
        "rewrite-rule",
        ["create rule gba_k1g_rule as on update to gba.provider_receipt_routes do instead nothing"],
        ["drop rule gba_k1g_rule on gba.provider_receipt_routes"],
    ),
    (
        "unlogged-table",
        ["alter table gba.provider_event_attestations set unlogged"],
        ["alter table gba.provider_event_attestations set logged"],
    ),
    (
        "third-role-table-grant",
        [_THIRD, "grant select on gba.provider_receipt_routes to gba_k1g_third"],
        [
            "revoke select on gba.provider_receipt_routes from gba_k1g_third",
            "drop role gba_k1g_third",
        ],
    ),
    (
        "runtime-grant-option",
        ["grant select on gba.provider_event_inbox to gba_runtime with grant option"],
        ["revoke grant option for select on gba.provider_event_inbox from gba_runtime"],
    ),
    (
        "third-role-function-grant",
        [_THIRD, "grant execute on function gba.check_provider_receipt() to gba_k1g_third"],
        [
            "revoke execute on function gba.check_provider_receipt() from gba_k1g_third",
            "drop role gba_k1g_third",
        ],
    ),
    (
        "location-function-body",
        [
            "create or replace function gba.current_location_id() returns uuid "
            "language sql stable parallel safe as $$ select null::uuid $$"
        ],
        [_LOCATION],
    ),
    (
        "tenant-function-definer",
        ["alter function gba.current_tenant_id() security definer"],
        ["alter function gba.current_tenant_id() security invoker"],
    ),
]


@pytest.mark.parametrize(("damage", "repair"), [pytest.param(d, r, id=i) for i, d, r in _DRIFT])
async def test_guard_drift_stops_routed_and_runtime_receipts(
    inbox: archive.Inbox,
    routed: Routed,
    writer_pool: RuntimePool,
    app_pool: RuntimePool,
    test_database: ProvisionedDatabase,
    damage: list[str],
    repair: list[str],
) -> None:
    app = str(conninfo_to_dict(test_database.app_dsn)["user"])
    with psycopg.connect(
        test_database.admin_dsn, dbname=test_database.name, autocommit=True
    ) as admin:
        try:
            for statement in damage:
                admin.execute(statement.format(app=app).encode())
            # The K1c writer-role check may refuse first on the writer path; either refuses.
            with pytest.raises((DatabaseUnavailableError, UnsafeReceiptWriterRoleError)):
                await attested.receive(writer_pool, routed, attested.delivery())
            with pytest.raises(DatabaseUnavailableError):
                await archive.receive(app_pool, inbox, inbox.event())
        finally:
            for statement in repair:
                admin.execute(statement.format(app=app).encode())
    async with tenant_transaction(app_pool, routed.tenant_id) as conn:
        await assert_provider_receipt_ready(conn)
    assert await routing.stored(app_pool, routed.tenant_id) == (0, 0, 0)
    assert (
        await attested.receive(writer_pool, routed, attested.delivery())
    ).disposition == "recorded"
