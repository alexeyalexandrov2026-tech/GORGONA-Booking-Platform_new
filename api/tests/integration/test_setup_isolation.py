"""Readiness and live-setting guards use the selected company, not any visible membership."""

from uuid import uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.db.provisioning import (
    add_membership,
    grant_platform_admin,
    owner_tenant_transaction,
)
from gorgona_booking.onboarding.service import apply_onboarding
from tests.integration import test_onboarding as shared
from tests.integration.seed import FakeUser, Salon, seed_user
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp


async def test_member_lists_only_include_the_selected_company(
    client: httpx.AsyncClient,
    owner_conn: psycopg.Connection,
    companies: tuple[Salon, Salon],
    both_owner: FakeUser,
    idp: FakeIdp,
) -> None:
    headers = idp.bearer(both_owner.subject, email=both_owner.email)
    for salon in companies:
        with owner_tenant_transaction(owner_conn, salon.tenant_id):
            expected = {
                str(row[0])
                for row in owner_conn.execute(
                    "select id from gba.memberships where tenant_id = %s", (salon.tenant_id,)
                ).fetchall()
            }
        response = await client.get(f"/v1/salons/{salon.tenant_id}/members", headers=headers)
        assert response.status_code == 200, response.text
        assert {item["membership_id"] for item in response.json()} == expected


@pytest.fixture
def companies(owner_conn: psycopg.Connection, salons: tuple[Salon, Salon]) -> tuple[Salon, Salon]:
    for salon, state in zip(salons, ("not_live", "live"), strict=True):
        with owner_tenant_transaction(owner_conn, salon.tenant_id):
            owner_conn.execute(
                "update gba.tenants set booking_state = %s where id = %s",
                (state, salon.tenant_id),
            )
            owner_conn.execute(
                "insert into gba.salon_fact_confirmations "
                "(tenant_id, fact_key, status, recorded_by) "
                "values (%s, 'timezone', 'confirmed', 'FAKE test setup')",
                (salon.tenant_id,),
            )
    return salons


@pytest.fixture
def both_owner(owner_conn: psycopg.Connection, companies: tuple[Salon, Salon]) -> FakeUser:
    user = seed_user(owner_conn, f"FAKE-multi-company-owner-{uuid7()}")
    for salon in companies:
        add_membership(owner_conn, tenant_id=salon.tenant_id, user_id=user.user_id, role="owner")
    return user


@pytest.mark.parametrize("platform", [False, True])
async def test_readiness_reports_each_selected_company_state(
    client: httpx.AsyncClient,
    owner_conn: psycopg.Connection,
    companies: tuple[Salon, Salon],
    both_owner: FakeUser,
    idp: FakeIdp,
    platform: bool,
) -> None:
    user = both_owner
    if platform:
        user = seed_user(owner_conn, f"FAKE-multi-company-support-{uuid7()}")
        grant_platform_admin(owner_conn, user_id=user.user_id, granted_by="FAKE test")
    headers = idp.bearer(user.subject, email=user.email)
    states = []
    for salon in companies:
        response = await client.get(f"/v1/salons/{salon.tenant_id}/readiness", headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["salon_id"] == str(salon.tenant_id)
        states.append(response.json()["booking_state"])
    # Both companies are deliberately checked: no dependency on PostgreSQL row order.
    assert states == ["not_live", "live"]


async def test_live_fact_protection_does_not_borrow_another_company_state(
    client: httpx.AsyncClient,
    owner_conn: psycopg.Connection,
    companies: tuple[Salon, Salon],
    both_owner: FakeUser,
    idp: FakeIdp,
) -> None:
    headers = idp.bearer(both_owner.subject, email=both_owner.email)
    statuses, facts = [], []
    for salon in companies:
        response = await client.put(
            f"/v1/salons/{salon.tenant_id}/facts/timezone",
            headers=headers,
            json={"status": "unconfirmed", "source_note": "FAKE owner correction"},
        )
        statuses.append(response.status_code)
        if response.status_code == 409:
            assert response.json()["error"]["code"] == "SALON_IS_LIVE"
        with owner_tenant_transaction(owner_conn, salon.tenant_id):
            facts.append(
                owner_conn.execute(
                    "select status from gba.salon_fact_confirmations where fact_key = 'timezone'"
                ).fetchone()
            )
    assert statuses == [200, 409]
    assert facts == [("unconfirmed",), ("confirmed",)]


@pytest.mark.parametrize(
    ("endpoint", "fact"),
    [("business-hours", "business_hours"), ("policies", "cancellation_policy")],
)
async def test_setting_edits_confirm_facts_only_for_the_selected_live_company(
    client: httpx.AsyncClient,
    owner_conn: psycopg.Connection,
    companies: tuple[Salon, Salon],
    both_owner: FakeUser,
    idp: FakeIdp,
    endpoint: str,
    fact: str,
) -> None:
    headers = idp.bearer(both_owner.subject, email=both_owner.email)
    facts = []
    for salon in companies:
        payload = (
            {
                "location_id": str(salon.location_id),
                "hours": [{"weekday": 1, "opens": "09:00", "closes": "17:00"}],
            }
            if endpoint == "business-hours"
            else {"cancellation_policy": {"FAKE": "test policy"}}
        )
        response = await client.put(
            f"/v1/salons/{salon.tenant_id}/{endpoint}", headers=headers, json=payload
        )
        assert response.status_code == 200, response.text
        with owner_tenant_transaction(owner_conn, salon.tenant_id):
            facts.append(
                owner_conn.execute(
                    "select status, recorded_by from gba.salon_fact_confirmations "
                    "where fact_key = %s",
                    (fact,),
                ).fetchone()
            )
    assert facts == [
        ("unconfirmed", f"user:{both_owner.user_id}"),
        ("confirmed", f"user:{both_owner.user_id}"),
    ]


async def test_owner_fact_requires_an_owner_of_the_selected_company(
    client: httpx.AsyncClient,
    owner_conn: psycopg.Connection,
    salons: tuple[Salon, Salon],
    idp: FakeIdp,
) -> None:
    selected, other = salons
    user = seed_user(owner_conn, f"FAKE-manager-and-owner-{uuid7()}")
    add_membership(owner_conn, tenant_id=selected.tenant_id, user_id=user.user_id, role="manager")
    add_membership(owner_conn, tenant_id=other.tenant_id, user_id=user.user_id, role="owner")
    headers = idp.bearer(user.subject, email=user.email)
    path = f"/v1/salons/{selected.tenant_id}/readiness"
    response = await client.get(path, headers=headers)
    assert response.status_code == 200, response.text
    fact = next(item for item in response.json()["items"] if item["fact"] == "owner")
    assert fact["status"] == "missing"
    actual_owner = seed_user(owner_conn, f"FAKE-selected-owner-{uuid7()}")
    add_membership(
        owner_conn, tenant_id=selected.tenant_id, user_id=actual_owner.user_id, role="owner"
    )
    response = await client.get(path, headers=headers)
    assert response.status_code == 200, response.text
    fact = next(item for item in response.json()["items"] if item["fact"] == "owner")
    assert fact["status"] == "confirmed"


async def test_platform_cannot_publish_ownerless_company_using_ownership_elsewhere(
    client: httpx.AsyncClient,
    owner_conn: psycopg.Connection,
    salons: tuple[Salon, Salon],
    idp: FakeIdp,
) -> None:
    operator = seed_user(owner_conn, f"FAKE-publisher-owner-elsewhere-{uuid7()}")
    grant_platform_admin(owner_conn, user_id=operator.user_id, granted_by="FAKE test")
    add_membership(
        owner_conn, tenant_id=salons[0].tenant_id, user_id=operator.user_id, role="owner"
    )
    target = apply_onboarding(
        owner_conn,
        shared.fake_spec(f"fake-ownerless-{uuid7()}", status="confirmed"),
        actor="FAKE test setup",
    )
    response = await client.post(
        f"/v1/platform/salons/{target.tenant_id}/go-live",
        headers=idp.bearer(operator.subject, email=operator.email),
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "NOT_READY"
    assert response.json()["error"]["details"]["missing"] == ["owner"]
    with owner_tenant_transaction(owner_conn, target.tenant_id):
        assert owner_conn.execute(
            "select booking_state from gba.tenants where id = %s", (target.tenant_id,)
        ).fetchone() == ("not_live",)
