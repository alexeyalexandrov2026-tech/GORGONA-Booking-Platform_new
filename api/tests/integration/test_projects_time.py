"""PRO-01 Slice 3: versioned time tracking, approval workflow, recurring schedules, and RLS."""

from uuid import uuid7

import pytest
from psycopg_pool import AsyncConnectionPool

from gorgona_booking.db.pool import tenant_transaction
from tests.integration.test_projects_matters import (
    ProjectsEnv,
    _matter_payload,
    client,
    idp,
    owner_a,
    owner_b,
    pro_env,
)

pytestmark = pytest.mark.anyio
__all__ = ["client", "idp", "owner_a", "owner_b", "pro_env"]


async def test_time_entry_versions_approvals_recurring_runs_and_ethical_wall(
    pro_env: ProjectsEnv,
    app_pool: AsyncConnectionPool,
) -> None:
    matter_id = uuid7()
    r = await pro_env.client.put(
        pro_env.url(f"/matters/{matter_id}"),
        headers=pro_env.headers(pro_env.lead_a, key=f"pt-m-{uuid7()}"),
        json=_matter_payload(
            pro_env,
            code="RET-2026",
            title="Restricted Counsel Retainer",
            kind="recurring_engagement",
            status="active",
            access_mode="restricted",
        ),
    )
    assert r.status_code == 200, r.text

    # Grant staff_a as contributor so they can log and submit time
    g = await pro_env.client.post(
        pro_env.url(f"/matters/{matter_id}/members"),
        headers=pro_env.headers(pro_env.lead_a, key=f"pt-gm-{uuid7()}"),
        json={
            "schema_version": 1,
            "user_id": str(pro_env.staff_a.user_id),
            "matter_role": "contributor",
        },
    )
    assert g.status_code == 200, g.text

    # 1. Contributor logs draft time entry (rev 1), edits & submits (rev 2), lead rejects (rev 3),
    #    contributor revises & resubmits (rev 4), lead approves (rev 5) -> immutable!
    te_id = uuid7()
    t1 = await pro_env.client.put(
        pro_env.url(f"/matters/{matter_id}/time-entries/{te_id}"),
        headers=pro_env.headers(pro_env.staff_a, key=f"pt-t1-{uuid7()}"),
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "work_date": "2026-11-21",
            "duration_minutes": 60,
            "hourly_rate_minor": 30_000,
            "billable": True,
            "description": "Initial draft research",
            "submit": False,
        },
    )
    assert t1.status_code == 200, t1.text
    assert t1.json()["amount_minor"] == 30_000
    assert t1.json()["status"] == "draft"

    t2 = await pro_env.client.put(
        pro_env.url(f"/matters/{matter_id}/time-entries/{te_id}"),
        headers=pro_env.headers(pro_env.staff_a, key=f"pt-t2-{uuid7()}"),
        json={
            "schema_version": 1,
            "expected_revision": 1,
            "work_date": "2026-11-21",
            "duration_minutes": 90,
            "hourly_rate_minor": 30_000,
            "billable": True,
            "description": "Completed case law analysis",
            "submit": True,
        },
    )
    assert t2.status_code == 200, t2.text
    assert t2.json()["amount_minor"] == 45_000
    assert t2.json()["status"] == "submitted"

    # Reject (rev 3)
    rej = await pro_env.client.post(
        pro_env.url(f"/matters/{matter_id}/time-entries/{te_id}/decision"),
        headers=pro_env.headers(pro_env.lead_a, key=f"pt-rej-{uuid7()}"),
        json={"schema_version": 1, "expected_revision": 2, "decision": "reject"},
    )
    assert rej.status_code == 200, rej.text
    assert rej.json()["status"] == "rejected"

    # Resubmit with updated description (rev 4)
    t4 = await pro_env.client.put(
        pro_env.url(f"/matters/{matter_id}/time-entries/{te_id}"),
        headers=pro_env.headers(pro_env.staff_a, key=f"pt-t4-{uuid7()}"),
        json={
            "schema_version": 1,
            "expected_revision": 3,
            "work_date": "2026-11-21",
            "duration_minutes": 90,
            "hourly_rate_minor": 30_000,
            "billable": True,
            "description": "Completed case law analysis with citations",
            "submit": True,
        },
    )
    assert t4.status_code == 200, t4.text

    # Approve (rev 5)
    app = await pro_env.client.post(
        pro_env.url(f"/matters/{matter_id}/time-entries/{te_id}/decision"),
        headers=pro_env.headers(pro_env.lead_a, key=f"pt-app-{uuid7()}"),
        json={"schema_version": 1, "expected_revision": 4, "decision": "approve"},
    )
    assert app.status_code == 200, app.text
    assert app.json()["status"] == "approved"
    assert app.json()["revision"] == 5

    # Approved entry cannot be edited
    bad_edit = await pro_env.client.put(
        pro_env.url(f"/matters/{matter_id}/time-entries/{te_id}"),
        headers=pro_env.headers(pro_env.staff_a, key=f"pt-bad-{uuid7()}"),
        json={
            "schema_version": 1,
            "expected_revision": 5,
            "work_date": "2026-11-21",
            "duration_minutes": 30,
            "hourly_rate_minor": 30_000,
            "billable": True,
            "description": "Tamper after approval",
            "submit": False,
        },
    )
    assert bad_edit.status_code == 409, bad_edit.text

    # Full revision chain 1..5 preserved
    revs = await pro_env.client.get(
        pro_env.url(f"/matters/{matter_id}/time-entries/{te_id}/revisions"),
        headers=pro_env.headers(pro_env.lead_a),
    )
    assert revs.status_code == 200
    assert [rv["revision"] for rv in revs.json()["items"]] == [1, 2, 3, 4, 5]

    # 2. Recurring schedule + idempotent run materialization creating task + advancing next_run_date
    sched_id = uuid7()
    sc = await pro_env.client.put(
        pro_env.url(f"/matters/{matter_id}/recurring-schedules/{sched_id}"),
        headers=pro_env.headers(pro_env.lead_a, key=f"pt-sc-{uuid7()}"),
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "title": "Monthly Compliance Review",
            "task_template_title": "Monthly regulatory check",
            "default_assignee_user_id": str(pro_env.staff_a.user_id),
            "cadence": "monthly",
            "next_run_date": "2026-11-01",
            "fixed_fee_minor": 200_000,
            "status": "active",
        },
    )
    assert sc.status_code == 200, sc.text

    run_key = f"pt-run-{uuid7()}"
    run1 = await pro_env.client.post(
        pro_env.url(f"/matters/{matter_id}/recurring-schedules/{sched_id}/run"),
        headers=pro_env.headers(pro_env.lead_a, key=run_key),
        json={"schema_version": 1, "expected_revision": 1},
    )
    assert run1.status_code == 200, run1.text
    r1_data = run1.json()
    assert r1_data["period_start"] == "2026-11-01"
    assert r1_data["period_end"] == "2026-11-30"
    assert r1_data["fee_minor"] == 200_000
    assert r1_data["billing_status"] == "unbilled"

    # Idempotent replay returns exact same run_id and task_id
    run1_replay = await pro_env.client.post(
        pro_env.url(f"/matters/{matter_id}/recurring-schedules/{sched_id}/run"),
        headers=pro_env.headers(pro_env.lead_a, key=run_key),
        json={"schema_version": 1, "expected_revision": 1},
    )
    assert run1_replay.status_code == 200
    assert run1_replay.json()["run_id"] == r1_data["run_id"]

    # Schedule next_run_date advanced to 2026-12-01 (revision 2)
    scheds = await pro_env.client.get(
        pro_env.url(f"/matters/{matter_id}/recurring-schedules"),
        headers=pro_env.headers(pro_env.lead_a),
    )
    assert scheds.json()["items"][0]["next_run_date"] == "2026-12-01"
    assert scheds.json()["items"][0]["revision"] == 2

    # 3. Ethical wall blocks non-member peer manager & owner across API and PostgreSQL 18 FORCE RLS
    for outsider in (pro_env.peer_mgr_a, pro_env.owner):
        for path in (
            f"/matters/{matter_id}/time-entries",
            f"/matters/{matter_id}/time-entries/{te_id}/revisions",
            f"/matters/{matter_id}/recurring-schedules",
            f"/matters/{matter_id}/recurring-runs",
        ):
            resp = await pro_env.client.get(pro_env.url(path), headers=pro_env.headers(outsider))
            assert resp.status_code == 404, f"{outsider.subject} accessed {path}"

    async with tenant_transaction(app_pool, pro_env.tenant) as conn:
        await conn.execute(
            "select pg_catalog.set_config('gba.user_id', %s, true)",
            (str(pro_env.peer_mgr_a.user_id),),
        )
        for tbl in (
            "project_time_entries",
            "project_time_entry_revisions",
            "project_recurring_schedules",
            "project_recurring_runs",
        ):
            row = await (
                await conn.execute(
                    f"select count(*) from gba.{tbl} where matter_id = %s",
                    (matter_id,),
                )
            ).fetchone()
            assert row == (0,), f"RLS leak in {tbl}: {row}"
