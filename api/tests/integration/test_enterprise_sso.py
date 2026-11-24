"""Integration tests for ENTERPRISE-01 Slice 1 (0143): corporate SSO provider registry,
employee directory links, and atomic deprovisioning proving immediate 403 loss of access.
"""

from dataclasses import dataclass
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.business import modules
from gorgona_booking.business.readiness_registry import Readiness
from gorgona_booking.db.provisioning import add_membership
from tests.integration import test_management_api as shared
from tests.integration.booking_support import BookingWorld
from tests.integration.configuration_support import Config
from tests.integration.seed import FakeUser, seed_user
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp


@dataclass(frozen=True)
class EnterpriseEnv:
    client: httpx.AsyncClient
    idp: FakeIdp
    world: BookingWorld
    owner: FakeUser
    employee: FakeUser
    tenant_b_owner: FakeUser

    @property
    def tenant_a(self) -> UUID:
        return self.world.a.tenant_id

    @property
    def tenant_b(self) -> UUID:
        return self.world.b.tenant_id

    def url(self, tenant: UUID, suffix: str) -> str:
        return f"/v1/businesses/{tenant}/enterprise{suffix}"

    def headers(self, user: FakeUser, *, key: str | None = None) -> dict[str, str]:
        h = self.idp.bearer(user.subject, email=user.email)
        if key is not None:
            h["Idempotency-Key"] = key
        return h


@pytest.fixture
def enable_analytics_for_test(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(
        modules.MODULES_BY_ID,
        "analytics",
        modules.MODULES_BY_ID["analytics"].model_copy(
            update={"enableable": True, "readiness": Readiness.TECHNICALLY_VERIFIED}
        ),
    )


@pytest.fixture
async def ent_env(
    client: httpx.AsyncClient,
    idp: FakeIdp,
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    enable_analytics_for_test: None,
) -> EnterpriseEnv:
    owner = seed_user(owner_conn, f"ent-owner-a-{uuid7()}")
    employee = seed_user(owner_conn, f"ent-emp-a-{uuid7()}")
    tenant_b_owner = seed_user(owner_conn, f"ent-owner-b-{uuid7()}")
    add_membership(owner_conn, tenant_id=world.a.tenant_id, user_id=owner.user_id, role="owner")
    add_membership(
        owner_conn, tenant_id=world.a.tenant_id, user_id=employee.user_id, role="manager"
    )
    add_membership(
        owner_conn, tenant_id=world.b.tenant_id, user_id=tenant_b_owner.user_id, role="owner"
    )
    owner_conn.commit()

    cfg = Config(client, idp)
    for u, tid in ((owner, world.a.tenant_id), (tenant_b_owner, world.b.tenant_id)):
        await cfg.profile(u, tid, 0, [25])
        await cfg.publish(u, tid, 0, ["analytics"])

    return EnterpriseEnv(
        client=client,
        idp=idp,
        world=world,
        owner=owner,
        employee=employee,
        tenant_b_owner=tenant_b_owner,
    )


async def test_deprovisioned_employee_loses_access_immediately(ent_env: EnterpriseEnv) -> None:
    h_owner = ent_env.headers(ent_env.owner)
    h_emp = ent_env.headers(ent_env.employee)

    # 1. Active employee can read enterprise SSO providers before deprovisioning
    before = await ent_env.client.get(
        ent_env.url(ent_env.tenant_a, "/sso-providers"), headers=h_emp
    )
    assert before.status_code == 200, before.text

    # 2. Owner registers corporate SSO provider & links employee
    prov_id, link_id = uuid7(), uuid7()
    r_prov = await ent_env.client.put(
        ent_env.url(ent_env.tenant_a, f"/sso-providers/{prov_id}"),
        headers=ent_env.headers(ent_env.owner, key=f"ent-prov-{uuid7()}"),
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "code": "OKTA_CORP",
            "display_name": "Okta Corporate IdP",
            "protocol": "oidc",
            "issuer_url": "https://corp.okta.com/oauth2/default",
            "email_domain": "corp-enterprise.example",
        },
    )
    assert r_prov.status_code == 200, r_prov.text

    r_link = await ent_env.client.put(
        ent_env.url(ent_env.tenant_a, f"/directory-links/{link_id}"),
        headers=ent_env.headers(ent_env.owner, key=f"ent-lnk-{uuid7()}"),
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "provider_id": str(prov_id),
            "user_id": str(ent_env.employee.user_id),
            "external_subject": f"okta|{ent_env.employee.user_id}",
            "employee_code": "EMP-404",
        },
    )
    assert r_link.status_code == 200, r_link.text
    assert r_link.json()["status"] == "active"

    # 3. Deprovision employee -> membership suspended atomically
    r_dep = await ent_env.client.post(
        ent_env.url(ent_env.tenant_a, f"/directory-links/{link_id}/deprovision"),
        headers=ent_env.headers(ent_env.owner, key=f"ent-dep-{uuid7()}"),
        json={"schema_version": 1, "reason": "Employee offboarding via SCIM"},
    )
    assert r_dep.status_code == 200, r_dep.text
    dep = r_dep.json()
    assert dep["link"]["status"] == "deprovisioned"
    assert dep["event"]["event_kind"] == "deprovisioned"
    assert dep["event"]["memberships_suspended"] == 1

    # 4. Deprovisioned employee IMMEDIATELY loses access (403 TENANT_ACCESS_DENIED)
    after = await ent_env.client.get(ent_env.url(ent_env.tenant_a, "/sso-providers"), headers=h_emp)
    assert after.status_code == 403
    assert after.json()["error"]["code"] == "TENANT_ACCESS_DENIED"

    # Also cannot access core business endpoint
    ws_after = await ent_env.client.get(f"/v1/businesses/{ent_env.tenant_a}", headers=h_emp)
    assert ws_after.status_code == 403

    # 5. Second deprovision attempt is rejected (ENTERPRISE_STATE_INVALID)
    r_dup = await ent_env.client.post(
        ent_env.url(ent_env.tenant_a, f"/directory-links/{link_id}/deprovision"),
        headers=ent_env.headers(ent_env.owner, key=f"ent-dep-dup-{uuid7()}"),
        json={"schema_version": 1, "reason": "Duplicate offboarding"},
    )
    assert r_dup.status_code == 409
    assert r_dup.json()["error"]["code"] == "ENTERPRISE_STATE_INVALID"

    # 6. Lifecycle events recorded (provisioned + deprovisioned)
    evs = (
        await ent_env.client.get(
            ent_env.url(ent_env.tenant_a, "/lifecycle-events"), headers=h_owner
        )
    ).json()["items"]
    assert {e["event_kind"] for e in evs} == {"provisioned", "deprovisioned"}

    # 7. Cross-tenant isolation: Tenant B sees zero SSO providers of Tenant A
    hb = ent_env.headers(ent_env.tenant_b_owner)
    b_provs = (
        await ent_env.client.get(ent_env.url(ent_env.tenant_b, "/sso-providers"), headers=hb)
    ).json()["items"]
    assert b_provs == []
