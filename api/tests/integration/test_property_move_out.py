"""PROPERTY-01 6a: move-out condition report and photos (FAKE data).

docs/plan/PACKAGE_PROPERTY01_MOVE_OUT_DESIGN_2026-11-20.md.
"""

from datetime import date, timedelta
from typing import Any
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from tests.integration import test_property_move_in as move_in_tests
from tests.integration.test_agreements import Agreements
from tests.integration.test_property_catalog import Catalog
from tests.integration.test_property_lease_terms import amend, change, terminate
from tests.integration.test_property_leases import leases
from tests.integration.test_property_move_in import lease_with_evidence, record_move_in, reference
from tests.unit.test_file_validation import jpeg, png

pytestmark = pytest.mark.anyio
agreements = move_in_tests.agreements
catalog = move_in_tests.catalog
client = move_in_tests.client
enabled = move_in_tests.enabled
idp = move_in_tests.idp
manager_a = move_in_tests.manager_a
manager_b = move_in_tests.manager_b
__all__ = ["agreements", "catalog", "client", "enabled", "idp", "manager_a", "manager_b"]


def move_out_url(c: Catalog, lease_id: UUID) -> str:
    return f"{leases(c)}/{lease_id}/move-out"


async def record_move_out(
    c: Catalog,
    lease_id: UUID,
    body: dict[str, Any],
    *,
    key: str | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    return await c.client.put(
        move_out_url(c, lease_id),
        json=body,
        headers={**(headers or c.headers), "Idempotency-Key": key or str(uuid7())},
    )


async def move_out_evidence(
    a: Agreements,
    *,
    moved_out_on: str,
    term_revision: int = 1,
    condition_summary: str = "normal_wear",
    note: str | None = "FAKE Clean handover, keys returned",
) -> dict[str, Any]:
    report_id = (await a.create(category="report", file_id=await a.stored()))["document_id"]
    photo_file = await a.stored(jpeg(), media="image/jpeg", name="FAKE move-out.jpg")
    photo_id = (await a.create(category="report", title="FAKE move-out photo", file_id=photo_file))[
        "document_id"
    ]
    return {
        "schema_version": 1,
        "term_revision": term_revision,
        "moved_out_on": moved_out_on,
        "condition_summary": condition_summary,
        "note": note,
        "report": reference(report_id),
        "photos": [reference(photo_id)],
    }


async def test_move_out_requires_move_in_distinct_report_and_blocks_extension_or_earlier_release(
    enabled: Catalog,
    agreements: Agreements,
    app_pool: RuntimePool,
) -> None:
    lease_id, contract, mi_body = await lease_with_evidence(enabled, agreements)
    mi_day = date.fromisoformat(str(mi_body["moved_in_on"]))
    mo_body = await move_out_evidence(agreements, moved_out_on=mi_day.isoformat())

    # 1. Cannot record move-out before move-in exists (409)
    before_mi = await record_move_out(enabled, lease_id, mo_body)
    assert before_mi.status_code == 409, before_mi.text

    # Record move-in on (mi_day - 5) so we can test move-out before move-in day too
    earlier_mi = {**mi_body, "moved_in_on": (mi_day - timedelta(days=5)).isoformat()}
    assert (await record_move_in(enabled, lease_id, earlier_mi)).status_code == 200

    # 2. Refuses early/future dates, stale revision, or reused move-in report
    too_early = {**mo_body, "moved_out_on": (mi_day - timedelta(days=6)).isoformat()}
    assert (await record_move_out(enabled, lease_id, too_early)).status_code == 422

    in_future = {**mo_body, "moved_out_on": (mi_day + timedelta(days=1)).isoformat()}
    assert (await record_move_out(enabled, lease_id, in_future)).status_code == 422

    stale_rev = {**mo_body, "term_revision": 2}
    assert (await record_move_out(enabled, lease_id, stale_rev)).status_code == 409

    reused_report = {**mo_body, "report": mi_body["report"]}
    assert (await record_move_out(enabled, lease_id, reused_report)).status_code == 422

    # 3. Record valid move-out with damage_noted
    mo_body["condition_summary"] = "damage_noted"
    mo_body["note"] = "FAKE Scratched kitchen counter"
    recorded = await record_move_out(enabled, lease_id, mo_body, key="move-out-key-1")
    assert recorded.status_code == 200, recorded.text
    view = recorded.json()
    assert view["lease_id"] == str(lease_id)
    assert view["moved_out_on"] == mi_day.isoformat()
    assert view["condition_summary"] == "damage_noted"
    assert view["note"] == "FAKE Scratched kitchen counter"
    assert len(view["photos"]) == 1

    # Replay same key returns identical view; new key returns 409 conflict
    replay = await record_move_out(enabled, lease_id, mo_body, key="move-out-key-1")
    assert replay.status_code == 200
    assert replay.json() == view
    duplicate = await record_move_out(enabled, lease_id, mo_body)
    assert duplicate.status_code == 409

    # GET returns exact view
    fetched = await enabled.client.get(move_out_url(enabled, lease_id), headers=enabled.headers)
    assert fetched.status_code == 200
    assert fetched.json() == view

    # 4. After move-out, extending the lease is refused (409)
    signed_copy = (await agreements.get(f"/agreements/{contract}")).json()["document"][
        "document_id"
    ]
    ext_rev = await amend(
        agreements,
        contract,
        signed_copy,
        effective_from=(mi_day - timedelta(days=30)).isoformat(),
        effective_until=(mi_day + timedelta(days=60)).isoformat(),
    )
    ext_res = await change(enabled, lease_id, "extend", ext_rev)
    assert ext_res.status_code == 409, ext_res.text

    # 5. On a second lease, releasing earlier than moved_out_on is refused (409)
    lease_2, contract_2, mi_2 = await lease_with_evidence(enabled, agreements)
    assert (
        await record_move_in(
            enabled, lease_2, {**mi_2, "moved_in_on": (mi_day - timedelta(days=5)).isoformat()}
        )
    ).status_code == 200
    mo_2 = await move_out_evidence(agreements, moved_out_on=mi_day.isoformat())
    assert (await record_move_out(enabled, lease_2, mo_2)).status_code == 200
    term_early_rev = await terminate(
        agreements, contract_2, 2, (mi_day - timedelta(days=2)).isoformat()
    )
    rel_early = await change(enabled, lease_2, "release", term_early_rev)
    assert rel_early.status_code == 409, rel_early.text

    # Direct UPDATE / DELETE on property_move_outs rejected by PostgreSQL
    async with tenant_transaction(app_pool, enabled.tenant) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            await conn.execute(
                "update gba.property_move_outs set condition_summary = 'normal_wear' "
                "where tenant_id = %s and lease_id = %s",
                (enabled.tenant, lease_id),
            )


async def test_move_out_allows_release_on_or_after_moved_out_day_and_rejects_bad_photo(
    enabled: Catalog,
    agreements: Agreements,
) -> None:
    lease_id, contract, mi_body = await lease_with_evidence(enabled, agreements)
    mi_day = date.fromisoformat(str(mi_body["moved_in_on"]))
    assert (await record_move_in(enabled, lease_id, mi_body)).status_code == 200

    # PDF photo is rejected (422)
    pdf_doc = (await agreements.create(category="report", file_id=await agreements.stored()))[
        "document_id"
    ]
    bad_photo_body = await move_out_evidence(agreements, moved_out_on=mi_day.isoformat())
    bad_photo_body["photos"] = [reference(pdf_doc)]
    assert (await record_move_out(enabled, lease_id, bad_photo_body)).status_code == 422

    # Valid PNG photo succeeds
    good_photo_file = await agreements.stored(png(), media="image/png", name="FAKE ok.png")
    good_photo_doc = (
        await agreements.create(category="report", title="FAKE ok photo", file_id=good_photo_file)
    )["document_id"]
    bad_photo_body["photos"] = [reference(good_photo_doc)]
    assert (await record_move_out(enabled, lease_id, bad_photo_body)).status_code == 200

    # Finalizing release on moved_out_on succeeds!
    term_rev = await terminate(agreements, contract, 2, mi_day.isoformat())
    rel_ok = await change(enabled, lease_id, "release", term_rev)
    assert rel_ok.status_code == 200, rel_ok.text
