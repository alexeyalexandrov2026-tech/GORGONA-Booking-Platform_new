"""PRO-01 Slice 2: stages, tasks, DAG cycles, restricted matter files, and ACL search."""

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
from tests.unit.test_file_validation import pdf

pytestmark = pytest.mark.anyio
__all__ = ["client", "idp", "owner_a", "owner_b", "pro_env"]

PDF_BYTES = pdf()


async def test_stages_tasks_dag_cycles_files_and_acl_search(
    pro_env: ProjectsEnv,
    app_pool: AsyncConnectionPool,
) -> None:
    # 1. Create 1 restricted legal matter (lead_a only) and 1 branch-visible project
    restricted_id = uuid7()
    public_id = uuid7()

    r1 = await pro_env.client.put(
        pro_env.url(f"/matters/{restricted_id}"),
        headers=pro_env.headers(pro_env.lead_a, key=f"pw-m1-{uuid7()}"),
        json=_matter_payload(
            pro_env,
            code="TOPSEC-99",
            title="Project Helios Confidential Acquisition",
            access_mode="restricted",
        ),
    )
    assert r1.status_code == 200, r1.text

    r2 = await pro_env.client.put(
        pro_env.url(f"/matters/{public_id}"),
        headers=pro_env.headers(pro_env.lead_a, key=f"pw-m2-{uuid7()}"),
        json=_matter_payload(
            pro_env,
            code="PUB-01",
            title="Standard Helios Brand Audit",
            kind="project",
            status="active",
            access_mode="branch",
        ),
    )
    assert r2.status_code == 200, r2.text

    # 2. Add a stage on the restricted matter, submit deliverable, reject, resubmit, accept
    stage_id = uuid7()
    st1 = await pro_env.client.put(
        pro_env.url(f"/matters/{restricted_id}/stages/{stage_id}"),
        headers=pro_env.headers(pro_env.lead_a, key=f"pw-st1-{uuid7()}"),
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "stage_no": 1,
            "title": "Helios Due Diligence Phase",
            "fixed_fee_minor": 120_000,
        },
    )
    assert st1.status_code == 200, st1.text
    assert st1.json()["status"] == "open"

    sub1 = await pro_env.client.post(
        pro_env.url(f"/matters/{restricted_id}/stages/{stage_id}/submit"),
        headers=pro_env.headers(pro_env.lead_a, key=f"pw-sub1-{uuid7()}"),
        json={
            "schema_version": 1,
            "expected_revision": 1,
            "deliverable_summary": "Draft Helios DD memo v1",
        },
    )
    assert sub1.status_code == 200, sub1.text
    assert sub1.json()["deliverable_revision"] == 1
    assert sub1.json()["status"] == "submitted"

    rej = await pro_env.client.post(
        pro_env.url(f"/matters/{restricted_id}/stages/{stage_id}/decision"),
        headers=pro_env.headers(pro_env.lead_a, key=f"pw-rej-{uuid7()}"),
        json={"schema_version": 1, "expected_revision": 2, "decision": "reject"},
    )
    assert rej.status_code == 200, rej.text
    assert rej.json()["status"] == "rejected"

    sub2 = await pro_env.client.post(
        pro_env.url(f"/matters/{restricted_id}/stages/{stage_id}/submit"),
        headers=pro_env.headers(pro_env.lead_a, key=f"pw-sub2-{uuid7()}"),
        json={
            "schema_version": 1,
            "expected_revision": 3,
            "deliverable_summary": "Final Helios DD memo v2",
        },
    )
    assert sub2.status_code == 200, sub2.text
    assert sub2.json()["deliverable_revision"] == 2

    acc = await pro_env.client.post(
        pro_env.url(f"/matters/{restricted_id}/stages/{stage_id}/decision"),
        headers=pro_env.headers(pro_env.lead_a, key=f"pw-acc-{uuid7()}"),
        json={"schema_version": 1, "expected_revision": 4, "decision": "accept"},
    )
    assert acc.status_code == 200, acc.text
    assert acc.json()["status"] == "accepted"

    # 3. Create 3 tasks and verify DAG cycle detection (A -> B -> C -> A rejected!)
    t_a, t_b, t_c = uuid7(), uuid7(), uuid7()
    for tid, title in (
        (t_a, "Helios Antitrust Filing"),
        (t_b, "Helios Tax Review"),
        (t_c, "Helios Closing Checklist"),
    ):
        resp = await pro_env.client.put(
            pro_env.url(f"/matters/{restricted_id}/tasks/{tid}"),
            headers=pro_env.headers(pro_env.lead_a, key=f"pw-t-{tid}"),
            json={
                "schema_version": 1,
                "expected_revision": 0,
                "stage_id": str(stage_id),
                "title": title,
                "assignee_user_id": str(pro_env.lead_a.user_id),
                "priority": "high",
                "status": "in_progress",
            },
        )
        assert resp.status_code == 200, resp.text

    # Cannot assign a non-member to a restricted matter task
    bad_assign = await pro_env.client.put(
        pro_env.url(f"/matters/{restricted_id}/tasks/{uuid7()}"),
        headers=pro_env.headers(pro_env.lead_a, key=f"pw-bad-asg-{uuid7()}"),
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "title": "Blocked assign",
            "assignee_user_id": str(pro_env.peer_mgr_a.user_id),
        },
    )
    assert bad_assign.status_code == 422, bad_assign.text

    d1 = await pro_env.client.post(
        pro_env.url(f"/matters/{restricted_id}/tasks/{t_b}/dependencies"),
        headers=pro_env.headers(pro_env.lead_a, key=f"pw-d1-{uuid7()}"),
        json={"schema_version": 1, "depends_on_task_id": str(t_a)},
    )
    assert d1.status_code == 200, d1.text
    d2 = await pro_env.client.post(
        pro_env.url(f"/matters/{restricted_id}/tasks/{t_c}/dependencies"),
        headers=pro_env.headers(pro_env.lead_a, key=f"pw-d2-{uuid7()}"),
        json={"schema_version": 1, "depends_on_task_id": str(t_b)},
    )
    assert d2.status_code == 200, d2.text
    # Closing the loop A -> C creates A -> C -> B -> A cycle -> MUST reject!
    d_cycle = await pro_env.client.post(
        pro_env.url(f"/matters/{restricted_id}/tasks/{t_a}/dependencies"),
        headers=pro_env.headers(pro_env.lead_a, key=f"pw-dc-{uuid7()}"),
        json={"schema_version": 1, "depends_on_task_id": str(t_c)},
    )
    assert d_cycle.status_code == 409, d_cycle.text
    assert d_cycle.json()["error"]["code"] == "PROJECTS_DEPENDENCY_CYCLE"

    # 4. Upload a confidential PDF file to the restricted matter and verify download
    file_id = uuid7()
    up = await pro_env.client.put(
        pro_env.url(f"/matters/{restricted_id}/files/{file_id}"),
        params={
            "title": "Helios Board Resolution Secret",
            "category": "evidence",
            "stage_id": str(stage_id),
            "task_id": str(t_a),
        },
        headers={
            **pro_env.headers(pro_env.lead_a, key=f"pw-up-{uuid7()}"),
            "Content-Type": "application/pdf",
            "X-File-Name": "helios-secret-board.pdf",
        },
        content=PDF_BYTES,
    )
    assert up.status_code == 200, up.text
    assert up.json()["byte_size"] == len(PDF_BYTES)

    dl = await pro_env.client.get(
        pro_env.url(f"/matters/{restricted_id}/files/{file_id}/content"),
        headers=pro_env.headers(pro_env.lead_a),
    )
    assert dl.status_code == 200, dl.text
    assert dl.content == PDF_BYTES
    assert "default-src 'none'; sandbox" in dl.headers["content-security-policy"]

    # 5. Unified ACL-enforced Search ("Helios"):
    #    - lead_a sees BOTH matters + restricted stage + 3 tasks + secret file!
    #    - outsiders (peer_mgr_a, owner) see ONLY public_id (0 restricted hits)
    s_lead = await pro_env.client.get(
        pro_env.url("/search"),
        params={"q": "Helios"},
        headers=pro_env.headers(pro_env.lead_a),
    )
    assert s_lead.status_code == 200, s_lead.text
    ld = s_lead.json()
    assert {m["matter_id"] for m in ld["matters"]} == {str(restricted_id), str(public_id)}
    assert len(ld["stages"]) == 1
    assert len(ld["tasks"]) == 3
    assert len(ld["files"]) == 1

    for outsider in (pro_env.peer_mgr_a, pro_env.owner, pro_env.staff_a):
        s_out = await pro_env.client.get(
            pro_env.url("/search"),
            params={"q": "Helios"},
            headers=pro_env.headers(outsider),
        )
        assert s_out.status_code == 200, s_out.text
        od = s_out.json()
        assert [m["matter_id"] for m in od["matters"]] == [str(public_id)]
        assert od["stages"] == []
        assert od["tasks"] == []
        assert od["files"] == []

        # Direct access to restricted stages, tasks, files, and file bytes MUST return 404
        for path in (
            f"/matters/{restricted_id}/stages",
            f"/matters/{restricted_id}/tasks",
            f"/matters/{restricted_id}/tasks/{t_a}",
            f"/matters/{restricted_id}/files",
            f"/matters/{restricted_id}/files/{file_id}/content",
        ):
            r = await pro_env.client.get(pro_env.url(path), headers=pro_env.headers(outsider))
            assert r.status_code == 404, f"{outsider.subject} accessed {path}: {r.status_code}"

    # 6. Viewer role on restricted matter can read/download, but cannot write
    grant_v = await pro_env.client.post(
        pro_env.url(f"/matters/{restricted_id}/members"),
        headers=pro_env.headers(pro_env.lead_a, key=f"pw-gv-{uuid7()}"),
        json={
            "schema_version": 1,
            "user_id": str(pro_env.staff_a.user_id),
            "matter_role": "viewer",
        },
    )
    assert grant_v.status_code == 200, grant_v.text

    v_dl = await pro_env.client.get(
        pro_env.url(f"/matters/{restricted_id}/files/{file_id}/content"),
        headers=pro_env.headers(pro_env.staff_a),
    )
    assert v_dl.status_code == 200
    assert v_dl.content == PDF_BYTES

    v_write = await pro_env.client.put(
        pro_env.url(f"/matters/{restricted_id}/tasks/{uuid7()}"),
        headers=pro_env.headers(pro_env.staff_a, key=f"pw-vw-{uuid7()}"),
        json={"schema_version": 1, "expected_revision": 0, "title": "Viewer forbidden"},
    )
    assert v_write.status_code == 403, v_write.text

    # 7. Direct PostgreSQL 18 FORCE RLS check proves non-member sees 0 rows in all 4 new tables
    async with tenant_transaction(app_pool, pro_env.tenant) as conn:
        await conn.execute(
            "select pg_catalog.set_config('gba.user_id', %s, true)",
            (str(pro_env.peer_mgr_a.user_id),),
        )
        for tbl in (
            "project_stages",
            "project_tasks",
            "project_task_dependencies",
            "project_matter_files",
        ):
            row = await (
                await conn.execute(
                    f"select count(*) from gba.{tbl} where matter_id = %s",
                    (restricted_id,),
                )
            ).fetchone()
            assert row == (0,), f"RLS leak in {tbl}: {row}"
