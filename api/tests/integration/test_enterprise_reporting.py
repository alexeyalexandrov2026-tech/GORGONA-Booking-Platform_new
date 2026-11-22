"""Integration tests for ENTERPRISE-01 Slice 2 (0144): consent-based consolidated group
reporting preserving Stage 1 ownership boundaries, legal-entity attribution, currency
separation, and immediate revocation exclusion.
"""

from uuid import uuid7

import pytest

from tests.integration.test_enterprise_sso import (
    EnterpriseEnv,
    client,
    enable_analytics_for_test,
    ent_env,
    idp,
)

pytestmark = pytest.mark.anyio
__all__ = ["client", "enable_analytics_for_test", "ent_env", "idp"]


async def test_group_receives_only_consented_reports_without_ownership_transfer(
    ent_env: EnterpriseEnv,
) -> None:
    ha = ent_env.headers(ent_env.owner)
    hb = ent_env.headers(ent_env.tenant_b_owner)
    ta, tb = ent_env.tenant_a, ent_env.tenant_b

    # 1. Tenant A creates a business group, invites Tenant B, and Tenant B accepts (ADR-0018)
    group_id = uuid7()
    assert (
        await ent_env.client.put(
            f"/v1/businesses/{ta}/groups/{group_id}",
            headers=ent_env.headers(ent_env.owner, key=f"grp-cr-{uuid7()}"),
            json={"schema_version": 1, "code": "HOLDING_01", "name": "Gorgona Holding Group"},
        )
    ).status_code == 200
    assert (
        await ent_env.client.put(
            f"/v1/businesses/{ta}/groups/{group_id}/members/{tb}",
            headers=ent_env.headers(ent_env.owner, key=f"grp-inv-{uuid7()}"),
            json={"schema_version": 1},
        )
    ).status_code == 200
    assert (
        await ent_env.client.post(
            f"/v1/businesses/{tb}/groups/{group_id}/accept",
            headers=ent_env.headers(ent_env.tenant_b_owner, key=f"grp-acc-{uuid7()}"),
            json={"schema_version": 1, "expected_revision": 1},
        )
    ).status_code == 200

    # 2. Tenant B creates its own legal entity & publishes 2 report snapshots:
    # revenue_by_currency (will be consented) and headcount (will NOT be consented)
    le_b = uuid7()
    assert (
        await ent_env.client.put(
            f"/v1/businesses/{tb}/legal-entities/{le_b}",
            headers=ent_env.headers(ent_env.tenant_b_owner, key=f"ent-leb-{uuid7()}"),
            json={"expected_revision": 0, "code": "SUB_B_US", "legal_name": "Subsidiary B US Inc"},
        )
    ).status_code == 200

    for rset, cnt, amt in (
        ("revenue_by_currency", 12, 50000),
        ("headcount", 25, 0),
    ):
        r_snap = await ent_env.client.put(
            ent_env.url(tb, f"/group-report-snapshots/{uuid7()}"),
            headers=ent_env.headers(ent_env.tenant_b_owner, key=f"snap-{rset}-{uuid7()}"),
            json={
                "schema_version": 1,
                "organizer_business_id": str(ta),
                "group_id": str(group_id),
                "legal_entity_id": str(le_b),
                "period_key": "2026-10",
                "currency": "USD",
                "report_set": rset,
                "metric_count": cnt,
                "metric_amount_minor": amt,
                "notes": f"Published {rset}",
            },
        )
        assert r_snap.status_code == 200, r_snap.text

    # 3. Before any grant, organizer Tenant A sees ZERO snapshots!
    before_grant = await ent_env.client.get(
        ent_env.url(ta, f"/groups/{group_id}/consolidated-report?period_key=2026-10"),
        headers=ha,
    )
    assert before_grant.status_code == 200, before_grant.text
    assert before_grant.json()["entries"] == []
    assert before_grant.json()["totals_by_currency"] == []

    # 4. Tenant B grants consent ONLY for ["revenue_by_currency"]
    grant_id = uuid7()
    r_grant = await ent_env.client.put(
        ent_env.url(tb, f"/group-report-grants/{grant_id}"),
        headers=ent_env.headers(ent_env.tenant_b_owner, key=f"grt-1-{uuid7()}"),
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "organizer_business_id": str(ta),
            "group_id": str(group_id),
            "allowed_report_sets": ["revenue_by_currency"],
            "status": "active",
        },
    )
    assert r_grant.status_code == 200, r_grant.text

    # Organizer sees ONLY revenue_by_currency (headcount strictly hidden by PG18 RLS!)
    cons = await ent_env.client.get(
        ent_env.url(ta, f"/groups/{group_id}/consolidated-report?period_key=2026-10"),
        headers=ha,
    )
    assert cons.status_code == 200, cons.text
    body = cons.json()
    assert len(body["entries"]) == 1
    entry = body["entries"][0]
    assert entry["owner_business_id"] == str(tb)
    assert entry["legal_entity_id"] == str(le_b)
    assert entry["report_set"] == "revenue_by_currency"
    assert entry["currency"] == "USD"
    assert entry["metric_amount_minor"] == 50000
    assert body["totals_by_currency"] == [
        {
            "currency": "USD",
            "report_set": "revenue_by_currency",
            "total_count": 12,
            "total_amount_minor": 50000,
            "contributing_businesses": 1,
        }
    ]

    # Ownership NOT transferred: organizer Tenant A still gets 403 on Tenant B's own resources!
    assert (
        await ent_env.client.get(f"/v1/businesses/{tb}/legal-entities", headers=ha)
    ).status_code == 403

    # 5. Tenant B revokes grant -> organizer immediately sees ZERO snapshots again!
    r_rev = await ent_env.client.put(
        ent_env.url(tb, f"/group-report-grants/{grant_id}"),
        headers=ent_env.headers(ent_env.tenant_b_owner, key=f"grt-rev-{uuid7()}"),
        json={
            "schema_version": 1,
            "expected_revision": 1,
            "organizer_business_id": str(ta),
            "group_id": str(group_id),
            "allowed_report_sets": ["revenue_by_currency"],
            "status": "revoked",
        },
    )
    assert r_rev.status_code == 200, r_rev.text
    assert r_rev.json()["revoked_at"] is not None

    after_rev = await ent_env.client.get(
        ent_env.url(ta, f"/groups/{group_id}/consolidated-report?period_key=2026-10"),
        headers=ha,
    )
    assert after_rev.status_code == 200, after_rev.text
    assert after_rev.json()["entries"] == []
    assert after_rev.json()["totals_by_currency"] == []
    # Tenant B still sees its own grants
    assert (
        len(
            (await ent_env.client.get(ent_env.url(tb, "/group-report-grants"), headers=hb)).json()[
                "items"
            ]
        )
        == 1
    )
