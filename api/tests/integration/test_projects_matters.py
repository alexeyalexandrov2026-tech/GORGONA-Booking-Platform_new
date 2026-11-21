"""PRO-01 Slice 1: legal matters, projects, conflict checks, ethical-wall FORCE RLS and access."""

from dataclasses import dataclass
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest
from psycopg_pool import AsyncConnectionPool

from gorgona_booking.business import modules
from gorgona_booking.business.readiness_registry import Readiness
from gorgona_booking.db.pool import tenant_transaction
from gorgona_booking.db.provisioning import add_membership
from tests.integration.booking_support import BookingWorld
from tests.integration.seed import FakeUser, seed_other_branch, seed_user
from tests.integration.test_counterparties import card
from tests.integration.test_delegations import (
    client,
    idp,
    owner_a,
    owner_b,
)
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
__all__ = ["client", "idp", "owner_a", "owner_b"]

ENABLED_PROJECTS = [
    "counterparties",
    "documents",
    "finance",
    "finance_documents",
    "projects",
]


@dataclass(frozen=True)
class ProjectsEnv:
    client: httpx.AsyncClient
    idp: FakeIdp
    tenant: UUID
    branch_a: UUID
    branch_b: UUID
    owner: FakeUser
    lead_a: FakeUser
    peer_mgr_a: FakeUser
    branch_b_mgr: FakeUser
    staff_a: FakeUser
    client_id: UUID

    def headers(self, user: FakeUser | None = None, *, key: str | None = None) -> dict[str, str]:
        who = user or self.owner
        h = self.idp.bearer(who.subject, email=who.email)
        if key is not None:
            h["Idempotency-Key"] = key
        return h

    def url(self, suffix: str) -> str:
        return f"/v1/businesses/{self.tenant}/projects{suffix}"


async def _publish_modules(
    client: httpx.AsyncClient, idp: FakeIdp, owner: FakeUser, tenant: UUID, mods: list[str]
) -> None:
    hdr = idp.bearer(owner.subject, email=owner.email)
    ba = f"/v1/businesses/{tenant}"
    prof = await client.put(
        f"{ba}/profile",
        headers={**hdr, "Idempotency-Key": f"pro-prof-{uuid7()}"},
        json={"expected_revision": 0, "industry_ids": [16]},
    )
    assert prof.status_code == 200, prof.text
    draft = await client.put(
        f"{ba}/configuration/draft",
        headers={**hdr, "Idempotency-Key": f"pro-cfg-draft-{uuid7()}"},
        json={"expected_version": 0, "profile_revision": 1, "module_ids": mods},
    )
    assert draft.status_code == 200, draft.text
    ver = draft.json()["version"]
    for step, rev in (("validate", 1), ("publish", 2)):
        s = await client.post(
            f"{ba}/configuration/versions/{ver}/{step}",
            headers={**hdr, "Idempotency-Key": f"pro-cfg-{step}-{uuid7()}"},
            json={"expected_revision": rev},
        )
        assert s.status_code == 200, s.text


@pytest.fixture
async def pro_env(
    client: httpx.AsyncClient,
    idp: FakeIdp,
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    owner_a: FakeUser,
    monkeypatch: pytest.MonkeyPatch,
) -> ProjectsEnv:
    monkeypatch.setitem(
        modules.MODULES_BY_ID,
        "projects",
        modules.MODULES_BY_ID["projects"].model_copy(
            update={"enableable": True, "readiness": Readiness.TECHNICALLY_VERIFIED}
        ),
    )
    branch_b, _ = seed_other_branch(owner_conn, world.a)
    lead_a = seed_user(owner_conn, "pro-lead-a")
    peer_mgr_a = seed_user(owner_conn, "pro-peer-mgr-a")
    branch_b_mgr = seed_user(owner_conn, "pro-branch-b-mgr")
    staff_a = seed_user(owner_conn, "pro-staff-a")
    for user, role, loc in (
        (lead_a, "manager", world.a.location_id),
        (peer_mgr_a, "manager", world.a.location_id),
        (branch_b_mgr, "manager", branch_b),
        (staff_a, "artist", world.a.location_id),
    ):
        add_membership(
            owner_conn,
            tenant_id=world.a.tenant_id,
            user_id=user.user_id,
            role=role,
            location_id=loc,
        )
    owner_conn.commit()

    await _publish_modules(client, idp, owner_a, world.a.tenant_id, ENABLED_PROJECTS)
    client_id = uuid7()
    c_resp = await client.put(
        f"/v1/businesses/{world.a.tenant_id}/counterparties/{client_id}",
        headers={
            **idp.bearer(owner_a.subject, email=owner_a.email),
            "Idempotency-Key": f"pro-cp-{uuid7()}",
        },
        json=card(display_name="Acme Legal Client", roles=["customer"]),
    )
    assert c_resp.status_code == 200, c_resp.text
    return ProjectsEnv(
        client=client,
        idp=idp,
        tenant=world.a.tenant_id,
        branch_a=world.a.location_id,
        branch_b=branch_b,
        owner=owner_a,
        lead_a=lead_a,
        peer_mgr_a=peer_mgr_a,
        branch_b_mgr=branch_b_mgr,
        staff_a=staff_a,
        client_id=client_id,
    )


def _matter_payload(
    env: ProjectsEnv,
    *,
    expected_revision: int = 0,
    code: str = "MAT-001",
    title: str = "Confidential Litigation",
    kind: str = "legal_case",
    status: str = "intake",
    access_mode: str = "restricted",
    location_id: UUID | None = None,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "expected_revision": expected_revision,
        "location_id": str(location_id or env.branch_a),
        "code": code,
        "title": title,
        "description": "Privileged legal work",
        "kind": kind,
        "status": status,
        "access_mode": access_mode,
        "client_counterparty_id": str(env.client_id),
        "currency": "USD",
        "budget_minor": 250_000,
        "opened_on": "2026-11-21",
        "due_on": "2026-12-31",
    }


async def test_projects_module_cannot_be_enabled_without_readiness_override(
    client: httpx.AsyncClient,
    idp: FakeIdp,
    world: BookingWorld,
    owner_a: FakeUser,
) -> None:
    hdr = idp.bearer(owner_a.subject, email=owner_a.email)
    ba = f"/v1/businesses/{world.a.tenant_id}"
    prof = await client.put(
        f"{ba}/profile",
        headers={**hdr, "Idempotency-Key": f"pro-nr-prof-{uuid7()}"},
        json={"expected_revision": 0, "industry_ids": [16]},
    )
    assert prof.status_code == 200, prof.text
    draft = await client.put(
        f"{ba}/configuration/draft",
        headers={**hdr, "Idempotency-Key": f"pro-noready-{uuid7()}"},
        json={"expected_version": 0, "profile_revision": 1, "module_ids": ENABLED_PROJECTS},
    )
    assert draft.status_code == 200, draft.text
    ver = draft.json()["version"]
    val = await client.post(
        f"{ba}/configuration/versions/{ver}/validate",
        headers={**hdr, "Idempotency-Key": f"pro-noready-val-{uuid7()}"},
        json={"expected_revision": 1},
    )
    assert val.status_code == 422, val.text
    assert val.json()["error"]["code"] == "CONFIGURATION_INVALID"
    problems = val.json()["error"]["details"]["problems"]
    assert any(p["code"] == "MODULE_NOT_READY" and p["module_id"] == "projects" for p in problems)


async def test_legal_case_conflict_check_gate_and_revisions(pro_env: ProjectsEnv) -> None:
    matter_id = uuid7()
    # Cannot start legal_case directly in active status
    bad_start = await pro_env.client.put(
        pro_env.url(f"/matters/{matter_id}"),
        headers=pro_env.headers(pro_env.lead_a, key=f"bad-start-{uuid7()}"),
        json=_matter_payload(pro_env, status="active"),
    )
    assert bad_start.status_code == 409, bad_start.text
    assert bad_start.json()["error"]["code"] == "PROJECTS_CONFLICT_CHECK_REQUIRED"

    # Start in intake (succeeds, revision 1, creator automatically added as lead)
    created = await pro_env.client.put(
        pro_env.url(f"/matters/{matter_id}"),
        headers=pro_env.headers(pro_env.lead_a, key=f"create-{uuid7()}"),
        json=_matter_payload(pro_env, status="intake"),
    )
    assert created.status_code == 200, created.text
    assert created.json()["revision"] == 1
    assert created.json()["status"] == "intake"

    # Attempting to activate without a conflict check is rejected
    no_chk = await pro_env.client.put(
        pro_env.url(f"/matters/{matter_id}"),
        headers=pro_env.headers(pro_env.lead_a, key=f"act-no-chk-{uuid7()}"),
        json=_matter_payload(pro_env, expected_revision=1, status="active"),
    )
    assert no_chk.status_code == 409, no_chk.text
    assert no_chk.json()["error"]["code"] == "PROJECTS_CONFLICT_CHECK_REQUIRED"

    # Record a 'blocked' conflict check -> activation STILL blocked
    blocked_chk = await pro_env.client.post(
        pro_env.url(f"/matters/{matter_id}/conflict-checks"),
        headers=pro_env.headers(pro_env.lead_a, key=f"chk-blk-{uuid7()}"),
        json={
            "schema_version": 1,
            "checked_parties": "Acme vs Rival Corp",
            "decision": "blocked",
            "rationale": "Rival Corp is an existing client pending waiver.",
        },
    )
    assert blocked_chk.status_code == 200, blocked_chk.text

    still_blocked = await pro_env.client.put(
        pro_env.url(f"/matters/{matter_id}"),
        headers=pro_env.headers(pro_env.lead_a, key=f"act-blk-{uuid7()}"),
        json=_matter_payload(pro_env, expected_revision=1, status="active"),
    )
    assert still_blocked.status_code == 409, still_blocked.text

    # Record a 'waived' conflict check -> activation succeeds (revision 2)
    waived_chk = await pro_env.client.post(
        pro_env.url(f"/matters/{matter_id}/conflict-checks"),
        headers=pro_env.headers(pro_env.lead_a, key=f"chk-waiv-{uuid7()}"),
        json={
            "schema_version": 1,
            "checked_parties": "Acme vs Rival Corp",
            "decision": "waived",
            "rationale": "Written conflict waivers obtained from both parties.",
        },
    )
    assert waived_chk.status_code == 200, waived_chk.text

    activated = await pro_env.client.put(
        pro_env.url(f"/matters/{matter_id}"),
        headers=pro_env.headers(pro_env.lead_a, key=f"act-ok-{uuid7()}"),
        json=_matter_payload(pro_env, expected_revision=1, status="active"),
    )
    assert activated.status_code == 200, activated.text
    assert activated.json()["revision"] == 2
    assert activated.json()["status"] == "active"

    # Close matter (revision 3) -> cannot reopen
    closed = await pro_env.client.put(
        pro_env.url(f"/matters/{matter_id}"),
        headers=pro_env.headers(pro_env.lead_a, key=f"close-{uuid7()}"),
        json=_matter_payload(pro_env, expected_revision=2, status="closed"),
    )
    assert closed.status_code == 200, closed.text
    assert closed.json()["closed_at"] is not None

    reopen = await pro_env.client.put(
        pro_env.url(f"/matters/{matter_id}"),
        headers=pro_env.headers(pro_env.lead_a, key=f"reopen-{uuid7()}"),
        json=_matter_payload(pro_env, expected_revision=3, status="active"),
    )
    assert reopen.status_code == 409, reopen.text

    revs = await pro_env.client.get(
        pro_env.url(f"/matters/{matter_id}/revisions"),
        headers=pro_env.headers(pro_env.lead_a),
    )
    assert revs.status_code == 200, revs.text
    assert [r["revision"] for r in revs.json()["items"]] == [1, 2, 3]


async def test_ethical_wall_force_rls_and_revocation(
    pro_env: ProjectsEnv,
    app_pool: AsyncConnectionPool,
) -> None:
    restricted_id = uuid7()
    branch_id = uuid7()

    # lead_a creates 1 restricted legal case and 1 branch-visible project
    r1 = await pro_env.client.put(
        pro_env.url(f"/matters/{restricted_id}"),
        headers=pro_env.headers(pro_env.lead_a, key=f"ew-r1-{uuid7()}"),
        json=_matter_payload(
            pro_env, code="WALL-01", title="Secret Merger", access_mode="restricted"
        ),
    )
    assert r1.status_code == 200, r1.text

    r2 = await pro_env.client.put(
        pro_env.url(f"/matters/{branch_id}"),
        headers=pro_env.headers(pro_env.lead_a, key=f"ew-r2-{uuid7()}"),
        json=_matter_payload(
            pro_env,
            code="OPEN-01",
            title="Public Website Refresh",
            kind="project",
            status="active",
            access_mode="branch",
        ),
    )
    assert r2.status_code == 200, r2.text

    # Add a conflict check on restricted_id so child table RLS is also proven
    chk = await pro_env.client.post(
        pro_env.url(f"/matters/{restricted_id}/conflict-checks"),
        headers=pro_env.headers(pro_env.lead_a, key=f"ew-chk-{uuid7()}"),
        json={
            "schema_version": 1,
            "checked_parties": "Secret Target Co",
            "decision": "clear",
            "rationale": "Cleared.",
        },
    )
    assert chk.status_code == 200, chk.text

    # Same-branch peer manager AND company owner who are NOT on the restricted matter
    # see ONLY OPEN-01 and get 404 on restricted_id and all its sub-resources!
    for outsider in (pro_env.peer_mgr_a, pro_env.owner, pro_env.staff_a):
        listed = await pro_env.client.get(
            pro_env.url("/matters"), headers=pro_env.headers(outsider)
        )
        assert listed.status_code == 200, listed.text
        ids = {item["matter_id"] for item in listed.json()["items"]}
        assert str(branch_id) in ids
        assert str(restricted_id) not in ids

        for path in (
            f"/matters/{restricted_id}",
            f"/matters/{restricted_id}/revisions",
            f"/matters/{restricted_id}/conflict-checks",
            f"/matters/{restricted_id}/members",
        ):
            resp = await pro_env.client.get(pro_env.url(path), headers=pro_env.headers(outsider))
            assert resp.status_code == 404, f"{outsider.subject} saw {path}: {resp.text}"

    # Branch B manager cannot see EITHER matter (branch RLS isolation)
    b_list = await pro_env.client.get(
        pro_env.url("/matters"), headers=pro_env.headers(pro_env.branch_b_mgr)
    )
    assert b_list.status_code == 200
    assert b_list.json()["items"] == []

    # Direct PostgreSQL 18 runtime SQL check proves FORCE RLS enforces ethical wall below the API
    async with tenant_transaction(app_pool, pro_env.tenant) as conn:
        await conn.execute(
            "select pg_catalog.set_config('gba.user_id', %s, true)",
            (str(pro_env.peer_mgr_a.user_id),),
        )
        cnt_m = await (
            await conn.execute(
                "select count(*) from gba.project_matters where id = %s", (restricted_id,)
            )
        ).fetchone()
        cnt_r = await (
            await conn.execute(
                "select count(*) from gba.project_matter_revisions where matter_id = %s",
                (restricted_id,),
            )
        ).fetchone()
        cnt_c = await (
            await conn.execute(
                "select count(*) from gba.project_conflict_checks where matter_id = %s",
                (restricted_id,),
            )
        ).fetchone()
        assert cnt_m == (0,)
        assert cnt_r == (0,)
        assert cnt_c == (0,)

    # Grant peer_mgr_a as 'contributor' -> peer_mgr_a can read, but cannot manage ACL (only lead!)
    grant_contrib = await pro_env.client.post(
        pro_env.url(f"/matters/{restricted_id}/members"),
        headers=pro_env.headers(pro_env.lead_a, key=f"grant-c-{uuid7()}"),
        json={
            "schema_version": 1,
            "user_id": str(pro_env.peer_mgr_a.user_id),
            "matter_role": "contributor",
        },
    )
    assert grant_contrib.status_code == 200, grant_contrib.text

    can_read = await pro_env.client.get(
        pro_env.url(f"/matters/{restricted_id}"),
        headers=pro_env.headers(pro_env.peer_mgr_a),
    )
    assert can_read.status_code == 200, can_read.text

    cannot_manage = await pro_env.client.post(
        pro_env.url(f"/matters/{restricted_id}/members"),
        headers=pro_env.headers(pro_env.peer_mgr_a, key=f"try-grant-{uuid7()}"),
        json={
            "schema_version": 1,
            "user_id": str(pro_env.staff_a.user_id),
            "matter_role": "viewer",
        },
    )
    assert cannot_manage.status_code == 403, cannot_manage.text

    # Cannot revoke the LAST active lead (lead_a)
    members_list = (
        await pro_env.client.get(
            pro_env.url(f"/matters/{restricted_id}/members"),
            headers=pro_env.headers(pro_env.lead_a),
        )
    ).json()["items"]
    lead_a_member_id = next(
        m["member_id"] for m in members_list if m["user_id"] == str(pro_env.lead_a.user_id)
    )
    bad_revoke = await pro_env.client.post(
        pro_env.url(f"/matters/{restricted_id}/members/{lead_a_member_id}/revoke"),
        headers=pro_env.headers(pro_env.lead_a, key=f"rev-last-{uuid7()}"),
    )
    assert bad_revoke.status_code == 409, bad_revoke.text
    assert bad_revoke.json()["error"]["code"] == "PROJECTS_ACL_CONFLICT"

    # Promote peer_mgr_a to 'lead', then revoke original creator lead_a -> creator loses access!
    promote = await pro_env.client.post(
        pro_env.url(f"/matters/{restricted_id}/members"),
        headers=pro_env.headers(pro_env.lead_a, key=f"promote-{uuid7()}"),
        json={
            "schema_version": 1,
            "user_id": str(pro_env.peer_mgr_a.user_id),
            "matter_role": "lead",
        },
    )
    assert promote.status_code == 200, promote.text

    revoke_creator = await pro_env.client.post(
        pro_env.url(f"/matters/{restricted_id}/members/{lead_a_member_id}/revoke"),
        headers=pro_env.headers(pro_env.peer_mgr_a, key=f"rev-creator-{uuid7()}"),
    )
    assert revoke_creator.status_code == 200, revoke_creator.text
    assert revoke_creator.json()["revoked_at"] is not None

    # Original creator lead_a IMMEDIATELY loses access (creation_xid expired at commit!)
    creator_gone = await pro_env.client.get(
        pro_env.url(f"/matters/{restricted_id}"),
        headers=pro_env.headers(pro_env.lead_a),
    )
    assert creator_gone.status_code == 404, creator_gone.text

    # peer_mgr_a (the new lead) retains full access
    new_lead_ok = await pro_env.client.get(
        pro_env.url(f"/matters/{restricted_id}"),
        headers=pro_env.headers(pro_env.peer_mgr_a),
    )
    assert new_lead_ok.status_code == 200, new_lead_ok.text
