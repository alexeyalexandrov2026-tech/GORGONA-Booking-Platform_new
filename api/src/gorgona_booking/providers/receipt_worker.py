"""K2a receipt worker: attested receipts become permanent decisions. No provider call, no money.

The database decides. A worker claims an attested event with a lease, then records a decision
that carries only that lease; the trigger classifies the stored facts, links the canonical
provider operation and refuses a stale or forged lease. Every conflict or unkeyed fact becomes
`needs_review`. Nothing here reads or writes the ledger, settlements or obligations, and an event
without an attestation is never claimed. There is no process entry point or schedule yet.
"""

from typing import Literal
from uuid import UUID, uuid4

from gorgona_booking.business.contracts import Versioned
from gorgona_booking.db.pool import (
    RuntimeConnection,
    RuntimePool,
    tenant_transaction,
    unscoped_transaction,
)
from gorgona_booking.db.provider_receipt_guard import assert_provider_receipt_ready

MAX_LEASE_SECONDS = 600
MAX_BATCH = 500


class UnsafeReceiptWorkerRoleError(RuntimeError):
    """A worker credential is shared with the application or the writer, or has excess rights."""


class ReceiptDecision(Versioned):
    tenant_id: UUID
    event_id: UUID
    generation: int
    outcome: Literal["observed", "needs_review"]
    reason: Literal[
        "success", "not_final", "conflicting_facts", "unkeyed_operation", "refund_without_payment"
    ]
    operation_id: UUID | None


_ROLE_CHECK = """
select bool_and(not (r.rolsuper or r.rolbypassrls or r.rolcreaterole
    or r.rolcreatedb or r.rolreplication)
    and pg_catalog.pg_has_role(r.oid,'gba_receipt_worker','USAGE')
    and not pg_catalog.pg_has_role(r.oid,'gba_runtime','MEMBER')
    and not pg_catalog.pg_has_role(r.oid,'gba_receipt_writer','MEMBER')
    and not pg_catalog.has_schema_privilege(r.oid,'gba','CREATE')
    and not exists (
        select 1 from pg_catalog.pg_namespace n where n.nspname='gba'
          and pg_catalog.pg_has_role(r.oid,n.nspowner,'MEMBER'))
    and not exists (
        select 1 from pg_catalog.pg_class c join pg_catalog.pg_namespace n on n.oid=c.relnamespace
        where n.nspname='gba' and (
            pg_catalog.pg_has_role(r.oid,c.relowner,'MEMBER') or
            (c.relname<>all(array['provider_event_inbox','provider_event_deliveries',
                'provider_event_attestations','provider_operations','provider_event_leases',
                'provider_event_decisions']) and (
                pg_catalog.has_table_privilege(r.oid,c.oid,
                    'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
                or pg_catalog.has_any_column_privilege(r.oid,c.oid,
                    'SELECT,INSERT,UPDATE,REFERENCES'))))))
from pg_catalog.pg_roles r where r.rolname in (current_user,session_user)
    or pg_catalog.pg_has_role(session_user,r.oid,'MEMBER')
"""

_DISCOVER = (
    "select a.tenant_id,a.event_id from gba.provider_event_attestations a "
    "where (%(tenant)s::uuid is null or a.tenant_id=%(tenant)s::uuid) "
    "and not exists (select 1 from gba.provider_event_decisions d "
    "where d.tenant_id=a.tenant_id and d.event_id=a.event_id) "
    "group by a.tenant_id,a.event_id order by min(a.verified_at),a.event_id limit %(limit)s"
)

# A held lease makes this statement wait for its holder and then return no row.
_CLAIM = (
    "insert into gba.provider_event_leases (tenant_id,event_id,generation,holder,expires_at) "
    "select %(tenant)s,%(event)s,1,%(holder)s,now()+make_interval(secs=>%(seconds)s) "
    "where not exists (select 1 from gba.provider_event_decisions d "
    "where d.tenant_id=%(tenant)s and d.event_id=%(event)s) "
    "on conflict (tenant_id,event_id) do update set "
    "generation=gba.provider_event_leases.generation+1,holder=excluded.holder,"
    "expires_at=excluded.expires_at where gba.provider_event_leases.expires_at<now() "
    "returning generation"
)

_DECIDE = (
    "insert into gba.provider_event_decisions (tenant_id,event_id,generation,holder) "
    "values (%(tenant)s,%(event)s,%(generation)s,%(holder)s) "
    "returning outcome,reason,operation_id"
)


async def assert_safe_receipt_worker_role(conn: RuntimeConnection) -> None:
    """Refuse unless every role of this session is a pure worker, then check the schema."""
    row = await (await conn.execute(_ROLE_CHECK)).fetchone()
    if row is None or row[0] is not True:
        raise UnsafeReceiptWorkerRoleError("Receipt worker database role is unsafe")
    await assert_provider_receipt_ready(conn)


def _lease_seconds(seconds: int) -> int:
    if not 1 <= seconds <= MAX_LEASE_SECONDS:
        raise ValueError(f"Receipt lease must last 1 to {MAX_LEASE_SECONDS} seconds")
    return seconds


async def discover(
    conn: RuntimeConnection, *, limit: int, tenant_id: UUID | None = None
) -> list[tuple[UUID, UUID]]:
    """Attested, undecided events, oldest attestation first; IDs only."""
    rows = await (await conn.execute(_DISCOVER, {"tenant": tenant_id, "limit": limit})).fetchall()
    return [(row[0], row[1]) for row in rows]


async def claim(
    conn: RuntimeConnection,
    tenant_id: UUID,
    event_id: UUID,
    *,
    holder: UUID,
    lease_seconds: int,
) -> int | None:
    """Take the event's lease inside the caller's company transaction; None if held or decided."""
    row = await (
        await conn.execute(
            _CLAIM,
            {
                "tenant": tenant_id,
                "event": event_id,
                "holder": holder,
                "seconds": _lease_seconds(lease_seconds),
            },
        )
    ).fetchone()
    return None if row is None else int(row[0])


async def decide(
    conn: RuntimeConnection,
    tenant_id: UUID,
    event_id: UUID,
    *,
    holder: UUID,
    generation: int,
) -> ReceiptDecision:
    """Record the decision under the lease; the database refuses a stale or forged one."""
    row = await (
        await conn.execute(
            _DECIDE,
            {"tenant": tenant_id, "event": event_id, "generation": generation, "holder": holder},
        )
    ).fetchone()
    if row is None:
        raise RuntimeError("Receipt decision was not recorded")
    return ReceiptDecision(
        tenant_id=tenant_id,
        event_id=event_id,
        generation=generation,
        outcome=row[0],
        reason=row[1],
        operation_id=row[2],
    )


async def process_batch(
    pool: RuntimePool,
    *,
    limit: int = 50,
    lease_seconds: int = 60,
    tenant_id: UUID | None = None,
) -> list[ReceiptDecision]:
    """Decide up to `limit` attested events, each in its own claim and decision transaction.

    Events that another worker holds are skipped. A failure stops the batch; its committed
    decisions stay, and an uncommitted lease expires for the next run.
    """
    if not 1 <= limit <= MAX_BATCH:
        raise ValueError(f"Receipt batch must hold 1 to {MAX_BATCH} events")
    _lease_seconds(lease_seconds)
    holder = uuid4()
    async with unscoped_transaction(pool) as conn:
        await assert_safe_receipt_worker_role(conn)
        found = await discover(conn, limit=limit, tenant_id=tenant_id)
    decided: list[ReceiptDecision] = []
    for tenant, event in found:
        async with tenant_transaction(pool, tenant) as conn:
            generation = await claim(
                conn, tenant, event, holder=holder, lease_seconds=lease_seconds
            )
        if generation is None:
            continue
        async with tenant_transaction(pool, tenant) as conn:
            decided.append(await decide(conn, tenant, event, holder=holder, generation=generation))
    return decided
