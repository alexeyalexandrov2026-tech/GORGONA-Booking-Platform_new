"""A person in several companies only ever sees the company of the request.

`gba.tenants` and `gba.memberships` have permissive read policies for the caller's other
companies (and for platform admins), so a query without a company filter returned rows of
another company: readiness showed another company's booking state, an edit in a company
that is not live was recorded as confirmed, and the owner fact counted the caller's
ownership of a different company. FAKE companies only.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID

import httpx
import psycopg
import pytest

from gorgona_booking.api.app import create_app
from gorgona_booking.config import Settings
from gorgona_booking.db.pool import RuntimePool
from gorgona_booking.db.provisioning import (
    add_membership,
    grant_platform_admin,
    owner_tenant_transaction,
)
from tests.integration.seed import Salon, seed_salon, seed_user
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio


@pytest.fixture(scope="module")
def idp() -> FakeIdp:
    return FakeIdp()


@pytest.fixture
async def client(app_pool: RuntimePool, idp: FakeIdp) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(Settings(environment="test"), pool=app_pool, token_verifier=idp.verifier())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://api.test"
    ) as http:
        yield http


@dataclass(frozen=True)
class TwoCompanies:
    live: Salon
    not_live: Salon
    manager: dict[str, str]
    manager_user_id: UUID
    membership_in_live: UUID


@pytest.fixture
def two(owner_conn: psycopg.Connection, idp: FakeIdp) -> TwoCompanies:
    # The live company is created first, so an unfiltered lookup meets its row first.
    live = seed_salon(owner_conn, "live")
    not_live = seed_salon(owner_conn, "draft")
    with owner_tenant_transaction(owner_conn, not_live.tenant_id):
        owner_conn.execute(
            "update gba.tenants set booking_state = 'not_live' where id = %s",
            (not_live.tenant_id,),
        )
    person = seed_user(owner_conn, "two-companies")
    membership_in_live = add_membership(
        owner_conn, tenant_id=live.tenant_id, user_id=person.user_id, role="owner"
    )
    add_membership(owner_conn, tenant_id=not_live.tenant_id, user_id=person.user_id, role="manager")
    return TwoCompanies(
        live=live,
        not_live=not_live,
        manager=idp.bearer(person.subject, email=person.email),
        manager_user_id=person.user_id,
        membership_in_live=membership_in_live,
    )


def _code(response: httpx.Response) -> str:
    return str(response.json()["error"]["code"])


def _facts(response: httpx.Response) -> dict[str, str]:
    return {item["fact"]: item["status"] for item in response.json()["items"]}


async def test_readiness_reports_each_company_booking_state(
    client: httpx.AsyncClient, two: TwoCompanies
) -> None:
    for salon, state in ((two.not_live, "not_live"), (two.live, "live")):
        response = await client.get(f"/v1/salons/{salon.tenant_id}/readiness", headers=two.manager)
        assert response.status_code == 200, response.text
        assert response.json()["booking_state"] == state


async def test_platform_support_readiness_reports_the_requested_company(
    client: httpx.AsyncClient, owner_conn: psycopg.Connection, idp: FakeIdp, two: TwoCompanies
) -> None:
    operator = seed_user(owner_conn, "support")
    grant_platform_admin(owner_conn, user_id=operator.user_id, granted_by="test")
    support = idp.bearer(operator.subject, email=operator.email)
    for salon, state in ((two.not_live, "not_live"), (two.live, "live")):
        response = await client.get(f"/v1/salons/{salon.tenant_id}/readiness", headers=support)
        assert response.status_code == 200, response.text
        assert response.json()["booking_state"] == state


async def test_hours_edit_in_a_company_that_is_not_live_needs_reconfirmation(
    client: httpx.AsyncClient, two: TwoCompanies
) -> None:
    response = await client.put(
        f"/v1/salons/{two.not_live.tenant_id}/business-hours",
        json={
            "location_id": str(two.not_live.location_id),
            "hours": [{"weekday": 1, "opens": "09:00", "closes": "17:00"}],
        },
        headers=two.manager,
    )
    assert response.status_code == 200, response.text
    assert _facts(response)["business_hours"] == "unconfirmed"


async def test_a_fact_can_be_unconfirmed_in_a_company_that_is_not_live(
    client: httpx.AsyncClient, two: TwoCompanies
) -> None:
    response = await client.put(
        f"/v1/salons/{two.not_live.tenant_id}/facts/timezone",
        json={"status": "unconfirmed"},
        headers=two.manager,
    )
    assert response.status_code == 200, response.text
    assert _facts(response)["timezone"] == "unconfirmed"


async def test_owner_fact_ignores_ownership_of_another_company(
    client: httpx.AsyncClient, two: TwoCompanies
) -> None:
    # The person owns the live company but only manages this one, which has no owner.
    response = await client.get(
        f"/v1/salons/{two.not_live.tenant_id}/readiness", headers=two.manager
    )
    assert response.status_code == 200, response.text
    assert _facts(response)["owner"] == "missing"


async def test_membership_of_another_company_cannot_be_changed_here(
    client: httpx.AsyncClient, owner_conn: psycopg.Connection, idp: FakeIdp, two: TwoCompanies
) -> None:
    admin = seed_user(owner_conn, "admin")
    add_membership(
        owner_conn, tenant_id=two.not_live.tenant_id, user_id=admin.user_id, role="owner"
    )
    add_membership(owner_conn, tenant_id=two.live.tenant_id, user_id=admin.user_id, role="owner")
    headers = idp.bearer(admin.subject, email=admin.email)
    response = await client.post(
        f"/v1/salons/{two.not_live.tenant_id}/members/{two.membership_in_live}/suspend",
        headers=headers,
    )
    assert (response.status_code, _code(response)) == (404, "NOT_FOUND")


async def test_duplicate_invitation_check_is_limited_to_this_company(
    client: httpx.AsyncClient, owner_conn: psycopg.Connection, idp: FakeIdp
) -> None:
    first, second = seed_salon(owner_conn, "first"), seed_salon(owner_conn, "second")
    owner = seed_user(owner_conn, "inviter")
    for salon in (first, second):
        add_membership(owner_conn, tenant_id=salon.tenant_id, user_id=owner.user_id, role="owner")
    colleague = seed_user(owner_conn, "colleague")
    add_membership(owner_conn, tenant_id=first.tenant_id, user_id=colleague.user_id, role="artist")
    headers = idp.bearer(owner.subject, email=owner.email)
    body = {"email": colleague.email, "role": "artist"}

    already = await client.post(
        f"/v1/salons/{first.tenant_id}/invitations", json=body, headers=headers
    )
    assert (already.status_code, _code(already)) == (409, "ALREADY_MEMBER")
    invited = await client.post(
        f"/v1/salons/{second.tenant_id}/invitations", json=body, headers=headers
    )
    assert invited.status_code == 201, invited.text
