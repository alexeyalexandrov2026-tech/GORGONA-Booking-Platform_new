"""OPS-03 integration tests: provider/auth fail-closed behavior and offline sync conflict matrix."""

from datetime import date
from uuid import uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.business import ledger
from gorgona_booking.business.ledger import PeriodClosedError
from gorgona_booking.business.ledger_contracts import (
    BookInput,
    CloseInput,
    EntryInput,
    LineInput,
)
from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import add_membership, owner_tenant_transaction
from tests.integration import test_management_api as shared
from tests.integration.booking_support import BookingWorld
from tests.integration.configuration_support import Config
from tests.integration.seed import FakeUser, seed_user
from tests.integration.test_counterparties import card
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a


async def test_ops03_offline_sync_conflicts_revoked_actor_closed_period_and_fail_closed(
    client: httpx.AsyncClient,
    idp: FakeIdp,
    world: BookingWorld,
    manager_a: FakeUser,
    owner_conn: psycopg.Connection,
    app_pool: RuntimePool,
) -> None:
    tenant_id = world.a.tenant_id
    cfg = Config(client, idp)
    await cfg.profile(manager_a, tenant_id, 0, [1, 25])
    await cfg.publish(manager_a, tenant_id, 0, ["booking_resources", "counterparties", "finance"])

    # 1. Create counterparty rev 1, then simulate two competing offline edits against rev 1
    cp_id = uuid7()
    first_key = f"ops03-create-{uuid7()}"
    create_body = card(display_name="FAKE Offline Base", email="base@example.invalid", phone=None)
    res1 = await client.put(
        f"/v1/businesses/{tenant_id}/counterparties/{cp_id}",
        json=create_body,
        headers={**cfg.headers(manager_a), "Idempotency-Key": first_key},
    )
    assert res1.status_code == 200, res1.text
    assert res1.json()["revision"] == 1

    # Online client wins revision 1 -> 2
    edit_key = f"ops03-edit-{uuid7()}"
    edit_body = card(
        expected_revision=1,
        display_name="FAKE Online Winner",
        email="winner@example.invalid",
        phone=None,
    )
    res_win = await client.put(
        f"/v1/businesses/{tenant_id}/counterparties/{cp_id}",
        json=edit_body,
        headers={**cfg.headers(manager_a), "Idempotency-Key": edit_key},
    )
    assert res_win.status_code == 200, res_win.text
    assert res_win.json()["revision"] == 2

    # 1a. Network retry with exact same Idempotency-Key and payload succeeds idempotently
    res_retry = await client.put(
        f"/v1/businesses/{tenant_id}/counterparties/{cp_id}",
        json=edit_body,
        headers={**cfg.headers(manager_a), "Idempotency-Key": edit_key},
    )
    assert res_retry.status_code == 200, res_retry.text
    assert res_retry.json()["revision"] == 2

    # 1b. Same Idempotency-Key reused with mutated offline payload -> fail-closed 409
    mutated_body = card(
        expected_revision=1,
        display_name="FAKE Mutated Replay",
        email="mutated@example.invalid",
        phone=None,
    )
    res_idem_conflict = await client.put(
        f"/v1/businesses/{tenant_id}/counterparties/{cp_id}",
        json=mutated_body,
        headers={**cfg.headers(manager_a), "Idempotency-Key": edit_key},
    )
    assert res_idem_conflict.status_code == 422, res_idem_conflict.text
    assert res_idem_conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"

    # 1c. Competing offline client with fresh key and stale expected_revision=1 -> 409 conflict
    res_stale = await client.put(
        f"/v1/businesses/{tenant_id}/counterparties/{cp_id}",
        json=card(
            expected_revision=1,
            display_name="FAKE Stale Offline Edit",
            email="stale@example.invalid",
            phone=None,
        ),
        headers={**cfg.headers(manager_a), "Idempotency-Key": f"ops03-stale-{uuid7()}"},
    )
    assert res_stale.status_code == 409, res_stale.text

    # Verify winning server record remained intact
    res_get = await client.get(
        f"/v1/businesses/{tenant_id}/counterparties/{cp_id}",
        headers=cfg.headers(manager_a),
    )
    assert res_get.status_code == 200, res_get.text
    assert res_get.json()["revision"] == 2
    assert res_get.json()["display_name"] == "FAKE Online Winner"

    # 2. Offline sync submitted after employee membership was revoked -> 403 fail-closed
    revoked_staff = seed_user(owner_conn, f"FAKE-ops03-revoked-{uuid7()}")
    add_membership(
        owner_conn,
        tenant_id=tenant_id,
        user_id=revoked_staff.user_id,
        role="manager",
    )
    with owner_tenant_transaction(owner_conn, tenant_id):
        owner_conn.execute(
            "update gba.memberships set status = 'revoked' where tenant_id = %s and user_id = %s",
            (tenant_id, revoked_staff.user_id),
        )
    res_revoked = await client.put(
        f"/v1/businesses/{tenant_id}/counterparties/{cp_id}",
        json=card(
            expected_revision=2,
            display_name="FAKE Revoked Offline Sync",
            email="revoked@example.invalid",
            phone=None,
        ),
        headers={**cfg.headers(revoked_staff), "Idempotency-Key": f"ops03-revoked-{uuid7()}"},
    )
    assert res_revoked.status_code == 403, res_revoked.text

    # 3. Fail-closed auth/provider outage: forged/broken bearer rejected with 401
    res_bad_auth = await client.put(
        f"/v1/businesses/{tenant_id}/counterparties/{cp_id}",
        json=card(
            expected_revision=2,
            display_name="FAKE Forged Token Sync",
            email="forged@example.invalid",
            phone=None,
        ),
        headers={
            "Authorization": "Bearer invalid.provider.token",
            "Idempotency-Key": f"ops03-badauth-{uuid7()}",
        },
    )
    assert res_bad_auth.status_code == 401, res_bad_auth.text

    # 4. Offline ledger posting into a closed accounting period -> rejected, book stays balanced
    le_id = uuid7()
    res_le = await client.put(
        f"/v1/businesses/{tenant_id}/legal-entities/{le_id}",
        json={"expected_revision": 0, "code": "OPS03", "legal_name": "FAKE OPS03 Resilience LLC"},
        headers=cfg.headers(manager_a),
    )
    assert res_le.status_code == 200, res_le.text

    book_id = uuid7()
    async with tenant_transaction(app_pool, tenant_id) as conn:
        await ledger.save_book(
            conn,
            business_id=tenant_id,
            book_id=book_id,
            user_id=manager_a.user_id,
            actor=f"user:{manager_a.user_id}",
            key=f"ops03-book-{uuid7()}",
            body=BookInput(
                expected_revision=0,
                legal_entity_id=le_id,
                base_currency="USD",
                fiscal_year_start_month=1,
                accounting_start=date(2026, 1, 1),
            ),
        )
        accounts = await ledger.list_accounts(conn, tenant_id, book_id, after=None, limit=100)
        debit_acc, credit_acc = accounts.items[0].account_id, accounts.items[-1].account_id
        await ledger.change_period(
            conn,
            business_id=tenant_id,
            book_id=book_id,
            period=date(2026, 9, 1),
            action="closed",
            user_id=manager_a.user_id,
            actor=f"user:{manager_a.user_id}",
            key=f"ops03-close-{uuid7()}",
            body=CloseInput(expected_sequence=0, reason="Month-end close before offline sync"),
        )
        with pytest.raises(PeriodClosedError):
            await ledger.post_entry(
                conn,
                business_id=tenant_id,
                book_id=book_id,
                entry_id=uuid7(),
                user_id=manager_a.user_id,
                actor=f"user:{manager_a.user_id}",
                key=f"ops03-late-entry-{uuid7()}",
                body=EntryInput(
                    entry_date=date(2026, 9, 15),
                    currency="USD",
                    lines=(
                        LineInput(account_id=debit_acc, side="debit", amount="45.00"),
                        LineInput(account_id=credit_acc, side="credit", amount="45.00"),
                    ),
                ),
            )
        entries = await ledger.list_entries(
            conn, tenant_id, book_id, period=None, after=None, limit=50
        )
        assert entries.items == ()
