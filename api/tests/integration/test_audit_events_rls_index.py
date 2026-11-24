"""OPS-04 integration tests: verify 0149 audit_events RLS equivalence and index scan plan."""

import json
from uuid import uuid7

import psycopg
import pytest
from psycopg.errors import InsufficientPrivilege

from gorgona_booking.db.pool import RuntimePool, tenant_transaction, unscoped_transaction
from tests.integration.booking_support import BookingWorld

pytestmark = pytest.mark.anyio


async def test_0149_audit_events_rls_keeps_strict_isolation_and_uses_indexes(
    world: BookingWorld,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
) -> None:
    tenant_a = world.a.tenant_id
    tenant_b = world.b.tenant_id
    marker_a = f"ops04-a-{uuid7()}"
    marker_b = f"ops04-b-{uuid7()}"
    marker_p = f"ops04-platform-{uuid7()}"

    # 1. Insert tenant A, tenant B, and platform (NULL tenant_id) audit events via gba_runtime
    async with tenant_transaction(app_pool, tenant_a) as conn:
        await conn.execute(
            "insert into gba.audit_events (tenant_id, actor, action, target_type, target_id) "
            "values (%s, %s, %s, %s, %s)",
            (tenant_a, "ops04:test", "ops.check", "audit", marker_a),
        )
        # Cross-tenant insert under tenant_a context must be blocked by RLS WITH CHECK
        with pytest.raises(InsufficientPrivilege):
            async with conn.transaction():
                await conn.execute(
                    "insert into gba.audit_events "
                    "(tenant_id, actor, action, target_type, target_id) "
                    "values (%s, %s, %s, %s, %s)",
                    (tenant_b, "ops04:test", "ops.check", "audit", "cross-tenant-blocked"),
                )
        # Platform (NULL tenant_id) insert under tenant_a context must also be blocked
        with pytest.raises(InsufficientPrivilege):
            async with conn.transaction():
                await conn.execute(
                    "insert into gba.audit_events "
                    "(tenant_id, actor, action, target_type, target_id) "
                    "values (null, %s, %s, %s, %s)",
                    ("ops04:test", "ops.check", "audit", "null-tenant-blocked"),
                )

    async with tenant_transaction(app_pool, tenant_b) as conn:
        await conn.execute(
            "insert into gba.audit_events (tenant_id, actor, action, target_type, target_id) "
            "values (%s, %s, %s, %s, %s)",
            (tenant_b, "ops04:test", "ops.check", "audit", marker_b),
        )

    async with unscoped_transaction(app_pool) as conn:
        await conn.execute(
            "insert into gba.audit_events (tenant_id, actor, action, target_type, target_id) "
            "values (null, %s, %s, %s, %s)",
            ("ops04:test", "ops.check", "audit", marker_p),
        )
        # Tenant insert under unscoped (NULL) context must be blocked by RLS WITH CHECK
        with pytest.raises(InsufficientPrivilege):
            async with conn.transaction():
                await conn.execute(
                    "insert into gba.audit_events "
                    "(tenant_id, actor, action, target_type, target_id) "
                    "values (%s, %s, %s, %s, %s)",
                    (tenant_a, "ops04:test", "ops.check", "audit", "unscoped-tenant-blocked"),
                )

    # 2. Verify exact read visibility in all three contexts (A, B, unscoped NULL)
    async with tenant_transaction(app_pool, tenant_a) as conn:
        seen_a = {
            r[0]
            for r in await (
                await conn.execute(
                    "select target_id from gba.audit_events where target_id = any(%s)",
                    ([marker_a, marker_b, marker_p],),
                )
            ).fetchall()
        }
        assert seen_a == {marker_a}

    async with tenant_transaction(app_pool, tenant_b) as conn:
        seen_b = {
            r[0]
            for r in await (
                await conn.execute(
                    "select target_id from gba.audit_events where target_id = any(%s)",
                    ([marker_a, marker_b, marker_p],),
                )
            ).fetchall()
        }
        assert seen_b == {marker_b}

    async with unscoped_transaction(app_pool) as conn:
        seen_p = {
            r[0]
            for r in await (
                await conn.execute(
                    "select target_id from gba.audit_events where target_id = any(%s)",
                    ([marker_a, marker_b, marker_p],),
                )
            ).fetchall()
        }
        assert seen_p == {marker_p}

    # 3. Verify PostgreSQL planner can use indexes under RLS (not forced into Seq Scan)
    owner_conn.execute("analyze gba.audit_events")
    owner_conn.commit()
    async with tenant_transaction(app_pool, tenant_a) as conn:
        await conn.execute("set local enable_seqscan = off")
        plan_row = await (
            await conn.execute(
                "explain (format json) "
                "select count(*), min(occurred_at), max(occurred_at) from gba.audit_events"
            )
        ).fetchone()
        assert plan_row is not None
        plan_text = json.dumps(plan_row[0])
        assert "audit_events_tenant_time_idx" in plan_text

    async with unscoped_transaction(app_pool) as conn:
        await conn.execute("set local enable_seqscan = off")
        plan_row = await (
            await conn.execute(
                "explain (format json) "
                "select count(*), min(occurred_at), max(occurred_at) from gba.audit_events"
            )
        ).fetchone()
        assert plan_row is not None
        plan_text = json.dumps(plan_row[0])
        assert "Seq Scan" not in plan_text
        assert (
            "audit_events_platform_time_idx" in plan_text
            or "audit_events_tenant_time_idx" in plan_text
        )
