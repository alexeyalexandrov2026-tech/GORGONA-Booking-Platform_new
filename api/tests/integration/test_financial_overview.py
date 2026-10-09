"""The UI write gate reports actual readiness and publication; reading enables nothing."""

from uuid import uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.business import modules
from gorgona_booking.business.readiness_registry import Readiness
from tests.integration import test_invoice_issue as shared
from tests.integration.configuration_support import Config
from tests.integration.test_invoice_issue import InvoiceWorld
from tests.integration.test_ledger import LedgerWorld
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
manager_b = shared.manager_b
enabled = shared.enabled
invoices = shared.invoices


def path(business: object) -> str:
    return f"/v1/businesses/{business}/financial-documents/overview"


async def test_overview_requires_authentication(client: httpx.AsyncClient) -> None:
    assert (await client.get(path(uuid7()))).status_code == 401


async def test_accepted_h_stays_closed_until_published_and_when_acceptance_is_withdrawn(
    enabled: LedgerWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    feature = modules.MODULES_BY_ID["finance_documents"]
    assert (feature.readiness, feature.enableable) == (Readiness.TECHNICALLY_VERIFIED, True)
    # G is published for this company; the accepted H workflow is not.
    result = await enabled.client.get(path(enabled.business), headers=enabled.headers())
    assert result.status_code == 200, result.text
    assert result.json() == {
        "schema_version": 1,
        "business_id": str(enabled.business),
        "write_enabled": False,
        "blocked_reason": "module_disabled",
    }
    monkeypatch.setitem(
        modules.MODULES_BY_ID,
        "finance_documents",
        feature.model_copy(update={"enableable": False, "readiness": Readiness.PLANNED}),
    )
    withdrawn = await enabled.client.get(path(enabled.business), headers=enabled.headers())
    assert withdrawn.status_code == 200, withdrawn.text
    assert (withdrawn.json()["write_enabled"], withdrawn.json()["blocked_reason"]) == (
        False,
        "not_ready",
    )


async def test_overview_tracks_publication_without_changing_it(
    invoices: InvoiceWorld, idp: FakeIdp
) -> None:
    world = invoices.ledger
    result = await world.client.get(path(world.business), headers=world.headers())
    assert result.status_code == 200, result.text
    assert result.json()["write_enabled"] is True
    assert result.json()["blocked_reason"] is None
    await Config(world.client, idp).publish(world.user, world.business, 2, ["booking_resources"])
    off = await world.client.get(path(world.business), headers=world.headers())
    assert off.status_code == 200, off.text
    assert off.json()["write_enabled"] is False
    assert off.json()["blocked_reason"] == "module_disabled"


async def test_overview_fails_closed_for_damaged_financial_controls(
    enabled: LedgerWorld, owner_conn: psycopg.Connection
) -> None:
    owner_conn.execute(
        "alter table gba.external_payment_revisions alter column created_transaction "
        "set default '0'::xid8"
    )
    try:
        response = await enabled.client.get(path(enabled.business), headers=enabled.headers())
        assert response.status_code == 503, response.text
    finally:
        owner_conn.execute(
            "alter table gba.external_payment_revisions alter column created_transaction "
            "set default pg_current_xact_id()"
        )
