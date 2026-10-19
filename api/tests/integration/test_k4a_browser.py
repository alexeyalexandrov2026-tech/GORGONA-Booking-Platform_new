"""K4a/K4b/K3b: the finance screen for provider operations in a real browser, desktop and mobile.

Actual OIDC/PKCE, the static web export, the live API and PostgreSQL. Provider events are
synthetic, signed in memory and decided by the receipt worker before the browser starts; no
provider account, real key, network call or real money is involved.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path
from uuid import uuid7

import anyio
import psycopg
import pytest
from fastapi import FastAPI

from gorgona_booking.db.provisioning import add_membership, owner_tenant_transaction
from tests.integration import test_provider_payments as shared
from tests.integration import test_provider_receipt_attestations as attested
from tests.integration import test_provider_receipt_decisions as decided
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.live_server import free_port, live_server
from tests.integration.seed import seed_user
from tests.integration.test_credit_notes import CreditWorld
from tests.integration.test_management_browser import _browser_env, _management_app, _provider
from tests.integration.test_provider_payments import Money, event
from tests.integration.test_provider_receipt_attestations import Routed
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
enabled = shared.enabled
invoices = shared.invoices
payments = shared.payments
credits = shared.credits
inbox = shared.inbox
writer_pool = shared.writer_pool
routed = shared.routed
worker_pool = shared.worker_pool
backend = shared.backend
money = shared.money
PROJECTS = {"desktop": 1, "mobile": 2}
SLOW = 22  # with the six per-project operations, more than one 20-row page


async def project(money: Money, name: str, n: int) -> dict[str, str]:
    """One project's settlements and operations; amounts differ so each row is distinct."""
    apply = f"pi_FAKE{name}Apply"
    await money.reserved(f"1{n}.00")
    await money.observe(event("payment_intent.succeeded", object_id=apply, amount=1000 + 100 * n))
    # A manual payment that already names the provider ID: applying it needs linking.
    linked = f"pi_FAKE{name}Linked"
    obligation, partial = await money.reserved(f"2{n + 2}.00")
    recorded = await money.credits.payments.confirm(
        partial, 3, [(obligation, "10.00")], "10.00", f"FAKE Stripe {linked}", payment=uuid7()
    )
    assert recorded.status_code == 200, recorded.text
    # K3b: a second manual payment names it with another amount; linking it is refused.
    short, held = await money.reserved("9.00")
    recorded = await money.credits.payments.confirm(
        held, 3, [(short, "9.00")], "9.00", f"FAKE short Stripe {linked}", payment=uuid7()
    )
    assert recorded.status_code == 200, recorded.text
    await money.observe(event("payment_intent.succeeded", object_id=linked, amount=1000))
    # Applied before the browser, then a later charge disagrees: applied with conflict.
    conflict = f"pi_FAKE{name}Conflict"
    obligation, settled = await money.reserved(f"3{n}.00")
    conflict_raw = event("payment_intent.succeeded", object_id=conflict, amount=3000 + 100 * n)
    await money.observe(conflict_raw)
    applied = await money.apply(
        settled, await money.operation(conflict), [(obligation, f"3{n}.00")]
    )
    assert applied.status_code == 200, applied.text
    await money.observe(
        event(
            "charge.succeeded",
            object_id=f"ch_FAKE{name}Late",
            payment_intent=conflict,
            amount=100,
        )
    )
    # K4b: a later delivery of the same event states another amount.
    variant = conflict_raw.replace(
        f'"amount_received":3{n}00'.encode(), f'"amount_received":3{n}99'.encode()
    )
    assert variant != conflict_raw
    assert (await attested.receive(money.writer, money.routed, variant)).disposition == "conflict"
    # K4b: a decision without an operation, acknowledged in the browser.
    orphan = f"ch_FAKE{name}Orphan"
    await money.observe(event("charge.succeeded", object_id=orphan, payment_intent=None))
    return {
        "apply": apply,
        "apply_total": f"1{n}.00",
        "linked": linked,
        "linked_total": f"2{n + 2}.00",
        "conflict": conflict,
        # A second connection of the book with no clearing account: registered in the browser.
        "unregistered": f"acct_FAKE{name}New",
        "conflict_original": f"3{n}00",
        "conflict_delivered": f"3{n}99",
        "orphan": orphan,
        "waiting": f"pi_FAKE{name}Waiting",
    }


def second_connection(owner_conn: psycopg.Connection, routed: Routed, account: str) -> None:
    with owner_tenant_transaction(owner_conn, routed.tenant_id):
        owner_conn.execute(
            "insert into gba.provider_receipt_connections "
            "(tenant_id,id,book_id,namespace,account_id,api_version) values (%s,%s,%s,%s,%s,%s)",
            (
                routed.tenant_id,
                uuid7(),
                routed.book_id,
                "FAKE-receipts-" + uuid7().hex,
                account,
                "2026-09-30.endive",
            ),
        )


def _web() -> tuple[Path, str]:
    web = Path(__file__).resolve().parents[3] / "web"
    assert (web / "out/finance/index.html").exists(), "build web first"
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert npm is not None
    return web, npm


def _browse(
    servers: tuple[tuple[FastAPI, int], tuple[FastAPI, int]],
    web: Path,
    npm: str,
    env: dict[str, str],
) -> str:
    (provider, idp_port), (app, app_port) = servers
    with live_server(provider, idp_port), live_server(app, app_port):
        result = subprocess.run(  # noqa: S603 - fixed repository script, located npm
            [npm, "run", "test:management:provider"],
            cwd=web,
            env=env,
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
        )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


async def test_k4a_real_browser_provider_operations(
    money: Money,
    credits: CreditWorld,
    routed: Routed,
    owner_conn: psycopg.Connection,
    test_database: ProvisionedDatabase,
) -> None:
    if os.environ.get("GBA_REQUIRE_BROWSER") != "1":
        pytest.skip("BLOCKED: K4a browser requires GBA_REQUIRE_BROWSER=1")
    web, npm = await anyio.to_thread.run_sync(_web)
    fixture = {name: await project(money, name, n) for name, n in PROJECTS.items()}
    for item in fixture.values():
        second_connection(owner_conn, routed, item["unregistered"])
    await money.observe(
        *(
            event("payment_intent.processing", status="processing", object_id=f"pi_FAKEslow{i}")
            for i in range(SLOW)
        )
    )
    total = len(await money.listed())
    # K4b: attested last and never decided, so they wait for the worker in the browser.
    await decided.receive_all(
        money.writer,
        money.routed,
        *(
            event("payment_intent.succeeded", object_id=item["waiting"])
            for item in fixture.values()
        ),
    )
    assert total == SLOW + 3 * len(PROJECTS)
    app_port, idp_port = free_port(), free_port()
    origin, issuer = f"http://127.0.0.1:{app_port}", f"http://127.0.0.1:{idp_port}"
    owner = seed_user(owner_conn, f"FAKE-k4a-browser-{uuid7()}", issuer=issuer)
    add_membership(owner_conn, tenant_id=routed.tenant_id, user_id=owner.user_id, role="owner")
    live_idp = FakeIdp()
    provider, verifier = _provider(issuer, origin, live_idp, owner)
    app = _management_app(test_database, verifier, issuer, web)
    env = {
        **_browser_env(origin, issuer),
        "GBA_K4A_FIXTURE": json.dumps(fixture),
        "GBA_K4A_TOTAL": str(total),
        "GBA_K4A_SLOW": str(SLOW),
    }
    output = await anyio.to_thread.run_sync(
        _browse, ((provider, idp_port), (app, app_port)), web, npm, env
    )
    print(output)  # noqa: T201 - actual browser evidence in pytest -s
    with owner_tenant_transaction(owner_conn, routed.tenant_id):
        for item in fixture.values():
            for object_id, expected in (
                (item["apply"], 1),
                (item["linked"], 0),
                (item["conflict"], 1),
            ):
                row = owner_conn.execute(
                    "select count(*) from gba.external_payment_provenance v "
                    "join gba.provider_operations o on o.tenant_id=v.tenant_id "
                    "and o.id=v.operation_id where o.tenant_id=%s and o.provider_object_id=%s",
                    (routed.tenant_id, object_id),
                ).fetchone()
                assert row == (expected,), (object_id, row)
            row = owner_conn.execute(
                "select a.account_id from gba.provider_clearing_accounts a "
                "join gba.provider_receipt_connections c on c.tenant_id=a.tenant_id "
                "and c.id=a.connection_id where c.tenant_id=%s and c.account_id=%s",
                (routed.tenant_id, item["unregistered"]),
            ).fetchone()
            assert row == (credits.chart["1000"],), row
        row = owner_conn.execute(
            "select count(*) from gba.external_payments where tenant_id=%s and book_id=%s",
            (routed.tenant_id, routed.book_id),
        ).fetchone()
        # Four manual, two applied before the browser, two applied in it: never a duplicate.
        assert row == (8,)
        for item in fixture.values():
            row = owner_conn.execute(
                "select p.amount_minor,p.attestation from gba.provider_payment_links l "
                "join gba.external_payments p on p.tenant_id=l.tenant_id "
                "and p.book_id=l.book_id and p.id=l.payment_id "
                "join gba.provider_operations o on o.tenant_id=l.tenant_id "
                "and o.id=l.operation_id where l.tenant_id=%s and o.provider_object_id=%s",
                (routed.tenant_id, item["linked"]),
            ).fetchone()
            assert row == (1000, "manual_attestation"), row
        rows = owner_conn.execute(
            "select e.facts->'resource'->>'id',k.note from gba.provider_event_acknowledgements k "
            "join gba.provider_event_inbox e on e.tenant_id=k.tenant_id and e.id=k.event_id "
            "where k.tenant_id=%s order by 1",
            (routed.tenant_id,),
        ).fetchall()
        assert rows == sorted(
            (item["orphan"], f"FAKE {name} checked with the provider")
            for name, item in fixture.items()
        )
