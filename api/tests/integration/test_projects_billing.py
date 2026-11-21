"""PRO-01 Slice 4: FIN-03 matter invoicing, double-billing prevention, and ACL-enforced exports."""

from datetime import date
from uuid import UUID, uuid7

import psycopg
import pytest
from psycopg_pool import AsyncConnectionPool

from gorgona_booking.business import ledger
from gorgona_booking.business.ledger_contracts import BookInput
from gorgona_booking.db.pool import tenant_transaction
from gorgona_booking.db.provisioning import add_membership
from tests.integration.seed import seed_user
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


async def _setup_book_and_accounts(
    env: ProjectsEnv, app_pool: AsyncConnectionPool
) -> tuple[UUID, UUID, UUID]:
    entity_id = uuid7()
    book_id = uuid7()
    r_ent = await env.client.put(
        f"/v1/businesses/{env.tenant}/legal-entities/{entity_id}",
        headers=env.headers(env.owner, key=f"pro-le-{uuid7()}"),
        json={"expected_revision": 0, "code": "PRO_LE", "legal_name": "Gorgona Legal LLP"},
    )
    assert r_ent.status_code == 200, r_ent.text

    async with tenant_transaction(app_pool, env.tenant) as conn:
        await ledger.save_book(
            conn,
            business_id=env.tenant,
            book_id=book_id,
            user_id=env.owner.user_id,
            actor=f"user:{env.owner.user_id}",
            key=str(uuid7()),
            body=BookInput(
                expected_revision=0,
                legal_entity_id=entity_id,
                base_currency="USD",
                fiscal_year_start_month=1,
                accounting_start=date(2026, 1, 1),
            ),
        )
        listed = await ledger.list_accounts(conn, env.tenant, book_id, after=None, limit=100)
    accounts = {a.code: a.account_id for a in listed.items}

    ar_id = accounts.get("1200")
    if ar_id is None:
        ar_id = uuid7()
        r = await env.client.put(
            f"/v1/businesses/{env.tenant}/ledger/books/{book_id}/accounts/{ar_id}",
            headers=env.headers(env.owner, key=f"pro-ar-{uuid7()}"),
            json={
                "schema_version": 1,
                "expected_revision": 0,
                "code": "1200",
                "type": "asset",
                "name": "Accounts Receivable",
                "archived": False,
            },
        )
        assert r.status_code == 200, r.text
    rev_id = accounts.get("4000")
    if rev_id is None:
        rev_id = uuid7()
        r = await env.client.put(
            f"/v1/businesses/{env.tenant}/ledger/books/{book_id}/accounts/{rev_id}",
            headers=env.headers(env.owner, key=f"pro-rev-{uuid7()}"),
            json={
                "schema_version": 1,
                "expected_revision": 0,
                "code": "4000",
                "type": "income",
                "name": "Legal & Consulting Revenue",
                "archived": False,
            },
        )
        assert r.status_code == 200, r.text
    return book_id, ar_id, rev_id


async def test_fin03_matter_invoicing_and_ethical_wall_exports(
    pro_env: ProjectsEnv,
    owner_conn: psycopg.Connection,
    app_pool: AsyncConnectionPool,
) -> None:
    book_id, ar_id, rev_id = await _setup_book_and_accounts(pro_env, app_pool)

    # Seed a company-wide manager with FINANCE_MANAGE + PROJECTS_MANAGE who is NOT on the wall
    corp_outsider = seed_user(owner_conn, "pro-corp-outsider")
    add_membership(
        owner_conn,
        tenant_id=pro_env.tenant,
        user_id=corp_outsider.user_id,
        role="manager",
        location_id=None,
    )
    owner_conn.commit()

    # 1. Owner creates a restricted legal matter (owner is lead) + a branch-visible public project
    restricted_id = uuid7()
    public_id = uuid7()
    r1 = await pro_env.client.put(
        pro_env.url(f"/matters/{restricted_id}"),
        headers=pro_env.headers(pro_env.owner, key=f"pb-m1-{uuid7()}"),
        json=_matter_payload(
            pro_env,
            code="SEC-BILL-1",
            title="Restricted Patent Defense",
            kind="project",
            status="active",
            access_mode="restricted",
        ),
    )
    assert r1.status_code == 200, r1.text

    r2 = await pro_env.client.put(
        pro_env.url(f"/matters/{public_id}"),
        headers=pro_env.headers(pro_env.owner, key=f"pb-m2-{uuid7()}"),
        json=_matter_payload(
            pro_env,
            code="OPEN-BILL-1",
            title="Public Advisory Engagement",
            kind="project",
            status="active",
            access_mode="branch",
        ),
    )
    assert r2.status_code == 200, r2.text

    # 2. On the restricted matter: create accepted fixed-fee stage ($1,200), approved time ($450),
    #    and materialized recurring run ($2,000)
    stage_id = uuid7()
    assert (
        await pro_env.client.put(
            pro_env.url(f"/matters/{restricted_id}/stages/{stage_id}"),
            headers=pro_env.headers(pro_env.owner, key=f"pb-st-{uuid7()}"),
            json={
                "schema_version": 1,
                "expected_revision": 0,
                "stage_no": 1,
                "title": "Prior Art Search",
                "fixed_fee_minor": 120_000,
            },
        )
    ).status_code == 200
    assert (
        await pro_env.client.post(
            pro_env.url(f"/matters/{restricted_id}/stages/{stage_id}/submit"),
            headers=pro_env.headers(pro_env.owner, key=f"pb-st-sub-{uuid7()}"),
            json={
                "schema_version": 1,
                "expected_revision": 1,
                "deliverable_summary": "Prior art report delivered",
            },
        )
    ).status_code == 200
    assert (
        await pro_env.client.post(
            pro_env.url(f"/matters/{restricted_id}/stages/{stage_id}/decision"),
            headers=pro_env.headers(pro_env.owner, key=f"pb-st-acc-{uuid7()}"),
            json={"schema_version": 1, "expected_revision": 2, "decision": "accept"},
        )
    ).status_code == 200

    te_id = uuid7()
    assert (
        await pro_env.client.put(
            pro_env.url(f"/matters/{restricted_id}/time-entries/{te_id}"),
            headers=pro_env.headers(pro_env.owner, key=f"pb-te-{uuid7()}"),
            json={
                "schema_version": 1,
                "expected_revision": 0,
                "work_date": "2026-11-21",
                "duration_minutes": 90,
                "hourly_rate_minor": 30_000,
                "billable": True,
                "description": "Claim construction analysis",
                "submit": True,
            },
        )
    ).status_code == 200
    assert (
        await pro_env.client.post(
            pro_env.url(f"/matters/{restricted_id}/time-entries/{te_id}/decision"),
            headers=pro_env.headers(pro_env.owner, key=f"pb-te-app-{uuid7()}"),
            json={"schema_version": 1, "expected_revision": 1, "decision": "approve"},
        )
    ).status_code == 200

    sched_id = uuid7()
    assert (
        await pro_env.client.put(
            pro_env.url(f"/matters/{restricted_id}/recurring-schedules/{sched_id}"),
            headers=pro_env.headers(pro_env.owner, key=f"pb-sc-{uuid7()}"),
            json={
                "schema_version": 1,
                "expected_revision": 0,
                "title": "Monthly Docket Watch",
                "task_template_title": "Check USPTO docket",
                "cadence": "monthly",
                "next_run_date": "2026-11-01",
                "fixed_fee_minor": 200_000,
                "status": "active",
            },
        )
    ).status_code == 200
    run_res = await pro_env.client.post(
        pro_env.url(f"/matters/{restricted_id}/recurring-schedules/{sched_id}/run"),
        headers=pro_env.headers(pro_env.owner, key=f"pb-run-{uuid7()}"),
        json={"schema_version": 1, "expected_revision": 1},
    )
    assert run_res.status_code == 200, run_res.text
    run_id = run_res.json()["run_id"]

    # 3. Issue combined FIN-03 receivable invoice ($1,200 + $450 + $2,000 = $3,650 / 365_000 minor)
    inv_res = await pro_env.client.post(
        pro_env.url(f"/matters/{restricted_id}/invoices"),
        headers=pro_env.headers(pro_env.owner, key=f"pb-inv1-{uuid7()}"),
        json={
            "schema_version": 1,
            "book_id": str(book_id),
            "receivable_account_id": str(ar_id),
            "revenue_account_id": str(rev_id),
            "invoice_date": "2026-11-21",
            "due_date": "2026-12-21",
            "title": "Patent Defense Billing #1",
            "number": "PRO-INV-001",
            "time_entry_ids": [str(te_id)],
            "stage_ids": [str(stage_id)],
            "recurring_run_ids": [run_id],
        },
    )
    assert inv_res.status_code == 200, inv_res.text
    inv_data = inv_res.json()
    assert inv_data["total_minor"] == 365_000
    assert len(inv_data["items"]) == 3

    # Verify real FIN-03 invoice draft exists in financial_documents
    fin_get = await pro_env.client.get(
        f"/v1/businesses/{pro_env.tenant}/financial-documents/books/{book_id}"
        f"/invoices/{inv_data['invoice_document_id']}",
        headers=pro_env.headers(pro_env.owner),
    )
    assert fin_get.status_code == 200, fin_get.text
    assert fin_get.json()["total"] == "3650.00"

    # Double-billing ANY already-billed item MUST fail (409)
    for field, val in (
        ("time_entry_ids", [str(te_id)]),
        ("stage_ids", [str(stage_id)]),
        ("recurring_run_ids", [run_id]),
    ):
        dup = await pro_env.client.post(
            pro_env.url(f"/matters/{restricted_id}/invoices"),
            headers=pro_env.headers(pro_env.owner, key=f"pb-dup-{field}-{uuid7()}"),
            json={
                "schema_version": 1,
                "book_id": str(book_id),
                "receivable_account_id": str(ar_id),
                "revenue_account_id": str(rev_id),
                "invoice_date": "2026-11-21",
                "due_date": "2026-12-21",
                "title": "Double bill attempt",
                field: val,
            },
        )
        assert dup.status_code == 409, f"Expected 409 for duplicate {field}: {dup.text}"

    # 4. Authorized single-matter & portfolio exports for owner (active lead)
    m_exp = await pro_env.client.post(
        pro_env.url(f"/matters/{restricted_id}/exports"),
        headers=pro_env.headers(pro_env.owner, key=f"pb-mexp-{uuid7()}"),
    )
    assert m_exp.status_code == 200, m_exp.text
    assert m_exp.json()["export"]["invoice_count"] == 1
    assert m_exp.json()["export"]["time_entry_count"] == 1
    assert m_exp.json()["export"]["recurring_run_count"] == 1

    p_exp_owner = await pro_env.client.post(
        pro_env.url("/exports"),
        headers=pro_env.headers(pro_env.owner, key=f"pb-pexp-own-{uuid7()}"),
        json={"schema_version": 1, "location_id": str(pro_env.branch_a)},
    )
    assert p_exp_owner.status_code == 200, p_exp_owner.text
    assert p_exp_owner.json()["export"]["matter_count"] == 2
    assert p_exp_owner.json()["export"]["invoice_count"] == 1

    # 5. ETHICAL WALL PROOF on Invoices & Exports:
    #    Even a company-wide manager with FINANCE_MANAGE + PROJECTS_MANAGE gets 404 on
    #    restricted matter invoices & single-matter export, and ZERO restricted records in
    #    portfolio export & export audit log!
    assert (
        await pro_env.client.get(
            pro_env.url(f"/matters/{restricted_id}/invoices"),
            headers=pro_env.headers(corp_outsider),
        )
    ).status_code == 404
    assert (
        await pro_env.client.post(
            pro_env.url(f"/matters/{restricted_id}/exports"),
            headers=pro_env.headers(corp_outsider, key=f"pb-out-mexp-{uuid7()}"),
        )
    ).status_code == 404

    p_exp_out = await pro_env.client.post(
        pro_env.url("/exports"),
        headers=pro_env.headers(corp_outsider, key=f"pb-out-pexp-{uuid7()}"),
        json={"schema_version": 1, "location_id": str(pro_env.branch_a)},
    )
    assert p_exp_out.status_code == 200, p_exp_out.text
    out_data = p_exp_out.json()
    assert out_data["export"]["matter_count"] == 1
    assert out_data["export"]["invoice_count"] == 0
    assert out_data["export"]["time_entry_count"] == 0
    assert [m["matter"]["matter_id"] for m in out_data["matters"]] == [str(public_id)]

    # Export history for corp_outsider ONLY shows corp_outsider's own portfolio export
    exp_list = await pro_env.client.get(
        pro_env.url("/exports"), headers=pro_env.headers(corp_outsider)
    )
    assert exp_list.status_code == 200
    assert [e["export_id"] for e in exp_list.json()["items"]] == [out_data["export"]["export_id"]]

    # Direct PostgreSQL 18 FORCE RLS check on all 3 new tables
    async with tenant_transaction(app_pool, pro_env.tenant) as conn:
        await conn.execute(
            "select pg_catalog.set_config('gba.user_id', %s, true)",
            (str(corp_outsider.user_id),),
        )
        for tbl in ("project_matter_invoices", "project_matter_invoice_items", "project_exports"):
            row = await (
                await conn.execute(
                    f"select count(*) from gba.{tbl} where matter_id = %s",
                    (restricted_id,),
                )
            ).fetchone()
            assert row == (0,), f"RLS leak in {tbl}: {row}"
