"""PROPERTY-01 condition evidence of a property move-in."""

from datetime import datetime
from uuid import UUID, uuid7
from zoneinfo import ZoneInfo

import httpx
import pytest

from tests.integration import test_property_leases as lease_tests
from tests.integration.test_agreements import Agreements
from tests.integration.test_property_catalog import Catalog
from tests.integration.test_property_leases import lease_body, leases, register, signed
from tests.integration.test_property_listings import unit
from tests.unit.test_file_validation import png

pytestmark = pytest.mark.anyio
agreements = lease_tests.agreements
catalog = lease_tests.catalog
client = lease_tests.client
enabled = lease_tests.enabled
idp = lease_tests.idp
manager_a = lease_tests.manager_a
manager_b = lease_tests.manager_b
__all__ = ["agreements", "catalog", "client", "enabled", "idp", "manager_a", "manager_b"]


def move_in(c: Catalog, lease_id: UUID) -> str:
    return f"{leases(c)}/{lease_id}/move-in"


def reference(id_: object, revision: int = 1) -> dict[str, object]:
    return {"document_id": id_, "revision": revision}


async def record_move_in(
    c: Catalog,
    lease_id: UUID,
    body: dict[str, object],
    *,
    key: str | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    return await c.client.put(
        move_in(c, lease_id),
        json=body,
        headers={**(headers or c.headers), "Idempotency-Key": key or str(uuid7())},
    )


async def lease_with_evidence(c: Catalog, a: Agreements) -> tuple[UUID, str, dict[str, object]]:
    day = datetime.now(ZoneInfo("America/New_York")).date()
    signed_copy = (await a.create(file_id=await a.stored()))["document_id"]
    contract = await signed(
        a,
        signed_copy,
        effective_from=day.replace(month=1, day=1).isoformat(),
        effective_until=day.replace(month=12, day=31).isoformat(),
    )
    lease_id = uuid7()
    recorded = await register(c, lease_id, lease_body(await unit(c), contract))
    assert recorded.is_success, recorded.text

    report = (await a.create(category="report", file_id=await a.stored()))["document_id"]
    photo_file = await a.stored(png(), media="image/png", name="FAKE condition.png")
    photo = (await a.create(category="report", title="FAKE condition photo", file_id=photo_file))[
        "document_id"
    ]
    body = {
        "schema_version": 1,
        "term_revision": 1,
        "moved_in_on": day.isoformat(),
        "report": reference(report),
        "photos": [reference(photo)],
    }
    return lease_id, contract, body


async def test_record_move_in_with_immutable_report_and_photo(
    enabled: Catalog, agreements: Agreements
) -> None:
    lease_id, _, body = await lease_with_evidence(enabled, agreements)
    result = await record_move_in(enabled, lease_id, body, key="move-in")
    assert result.status_code == 200, result.text
    response = result.json()
    assert response["lease_id"] == str(lease_id)
    assert response["term_revision"] == body["term_revision"]
    assert response["moved_in_on"] == body["moved_in_on"]
    assert (response["report"], response["photos"]) == (body["report"], body["photos"])
    replay = await record_move_in(enabled, lease_id, body, key="move-in")
    assert replay.json() == response
    saved = await enabled.client.get(move_in(enabled, lease_id), headers=enabled.headers)
    assert saved.json() == response
