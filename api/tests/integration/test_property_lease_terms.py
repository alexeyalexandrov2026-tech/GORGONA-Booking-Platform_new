"""PROPERTY-01 signed changes to an exclusive unit lease."""

from uuid import UUID, uuid7

import httpx
import pytest

from tests.integration import test_property_leases as lease_tests
from tests.integration.test_agreements import Agreements, draft
from tests.integration.test_property_catalog import Catalog
from tests.integration.test_property_leases import lease_body, leases, register, signed
from tests.integration.test_property_listings import unit

pytestmark = pytest.mark.anyio
agreements = lease_tests.agreements
catalog = lease_tests.catalog
client = lease_tests.client
enabled = lease_tests.enabled
idp = lease_tests.idp
manager_a = lease_tests.manager_a
manager_b = lease_tests.manager_b
__all__ = ["agreements", "catalog", "client", "enabled", "idp", "manager_a", "manager_b"]


def terms(c: Catalog, lease_id: UUID) -> str:
    return f"{leases(c)}/{lease_id}/terms"


async def change(
    c: Catalog,
    lease_id: UUID,
    action: str,
    agreement_revision: int,
    expected_revision: int = 1,
    *,
    key: str | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    return await c.client.post(
        terms(c, lease_id),
        json={
            "schema_version": 1,
            "action": action,
            "agreement_revision": agreement_revision,
            "expected_revision": expected_revision,
        },
        headers={**(headers or c.headers), "Idempotency-Key": key or str(uuid7())},
    )


async def amend(
    a: Agreements, subject: str, document: object, expected: int = 2, **dates: object
) -> int:
    partner = (await a.get(f"/agreements/{subject}")).json()["counterparty_id"]
    saved = await a.put(subject, draft(partner, expected_revision=expected, **dates))
    assert saved.is_success, saved.text
    result = await a.agree(subject, expected + 1, document={"document_id": document, "revision": 1})
    assert result.is_success, result.text
    return expected + 2


async def test_extend_signed_lease_preserves_registration(
    enabled: Catalog, agreements: Agreements
) -> None:
    document = (await agreements.create(file_id=await agreements.stored()))["document_id"]
    revised_document = (
        await agreements.create(title="FAKE signed extension", file_id=await agreements.stored())
    )["document_id"]
    object_id, lease_id = await unit(enabled), uuid7()
    subject = await signed(agreements, document)
    original = await register(enabled, lease_id, lease_body(object_id, subject), key="registration")
    assert original.is_success, original.text
    revision = await amend(agreements, subject, revised_document, effective_until="2027-01-31")
    extended = await change(enabled, lease_id, "extend", revision, key="extension")
    assert extended.status_code == 200, extended.text
    row = extended.json()
    assert (row["revision"], row["action"], row["agreement_revision"]) == (2, "extend", 4)
    assert (row["starts_on"], row["ends_on"], row["document_id"]) == (
        "2026-01-01",
        "2027-01-31",
        revised_document,
    )
    replay = await change(enabled, lease_id, "extend", revision, key="extension")
    assert (replay.status_code, replay.json()) == (200, row)
    registration_replay = await register(
        enabled, lease_id, lease_body(object_id, subject), key="registration"
    )
    assert registration_replay.json() == original.json()
    history = await enabled.client.get(terms(enabled, lease_id), headers=enabled.headers)
    assert history.is_success, history.text
    assert [(i["revision"], i["ends_on"]) for i in history.json()["items"]] == [
        (2, "2027-01-31"),
        (1, "2026-12-31"),
    ]
