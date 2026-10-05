"""Company-wide documents and validated files against real disposable PostgreSQL."""

import asyncio
import hashlib
from collections.abc import AsyncIterator, Mapping
from urllib.parse import quote
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest
from psycopg import sql

from gorgona_booking.api.app import create_app
from gorgona_booking.business.file_validation import MAX_FILE_BYTES, VALIDATOR_VERSION
from gorgona_booking.config import Settings
from gorgona_booking.db.pool import RuntimePool, tenant_transaction, unscoped_transaction
from gorgona_booking.db.provisioning import (
    add_membership,
    grant_platform_admin,
    owner_tenant_transaction,
)
from tests.integration import test_management_api as shared
from tests.integration.booking_support import BookingWorld
from tests.integration.configuration_support import Config
from tests.integration.module_support import verified_modules
from tests.integration.seed import FakeUser, seed_user
from tests.integration.test_counterparties import card
from tests.integration.test_delegations import Parties
from tests.support.fake_idp import FakeIdp
from tests.unit.test_file_validation import jpeg, pdf, png

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
manager_b = shared.manager_b

ALL_MODULES = ["booking_resources", "counterparties", "documents"]
PDF = pdf()


def doc(**changes: object) -> dict[str, object]:
    return {
        "schema_version": 1,
        "expected_revision": 0,
        "title": "FAKE Supply agreement",
        "category": "agreement",
        "valid_from": None,
        "valid_until": None,
        "archived": False,
        "file_id": None,
        **changes,
    }


class Documents:
    def __init__(
        self, client: httpx.AsyncClient, business: UUID, user: FakeUser, idp: FakeIdp
    ) -> None:
        self.client = client
        self.business = business
        self.user = user
        self.auth = idp.bearer(user.subject, email=user.email)
        self.base = f"/v1/businesses/{business}"
        self.config = Config(client, idp)

    def headers(self, key: str | None = None) -> dict[str, str]:
        return {**self.auth, "Idempotency-Key": key or str(uuid7())}

    async def enable(self, modules: list[str] = ALL_MODULES) -> None:
        await self.config.profile(self.user, self.business, 0, [1, 6, 24])
        with verified_modules("documents"):
            await self.config.publish(self.user, self.business, 0, modules)

    async def upload(
        self,
        data: bytes | AsyncIterator[bytes] | Unread = PDF,
        *,
        media: str = "application/pdf",
        name: str = "FAKE Agreement.pdf",
        file_id: UUID | None = None,
        key: str | None = None,
        raw_name: str | None = None,
    ) -> httpx.Response:
        return await self.client.put(
            f"{self.base}/document-files/{file_id or uuid7()}",
            content=data,
            headers={
                **self.headers(key),
                "Content-Type": media,
                "X-File-Name": quote(name) if raw_name is None else raw_name,
            },
        )

    async def stored(self, data: bytes = PDF, **options: str) -> str:
        response = await self.upload(data, **options)  # type: ignore[arg-type]
        assert response.status_code == 200, response.text
        return str(response.json()["file_id"])

    async def save(
        self, subject: UUID | str, body: Mapping[str, object], key: str | None = None
    ) -> httpx.Response:
        return await self.client.put(
            f"{self.base}/documents/{subject}", json=dict(body), headers=self.headers(key)
        )

    async def create(self, **changes: object) -> dict[str, object]:
        response = await self.save(uuid7(), doc(**changes))
        assert response.status_code == 200, response.text
        data: dict[str, object] = response.json()
        return data

    async def get(self, suffix: str, **params: str | int | bool) -> httpx.Response:
        return await self.client.get(f"{self.base}{suffix}", headers=self.auth, params=params)

    async def link(
        self, subject: object, body: Mapping[str, object], key: str | None = None
    ) -> httpx.Response:
        return await self.client.post(
            f"{self.base}/documents/{subject}/counterparty-links",
            json=dict(body),
            headers=self.headers(key),
        )

    async def counterparty(self, **changes: object) -> str:
        response = await self.client.put(
            f"{self.base}/counterparties/{uuid7()}", json=card(**changes), headers=self.headers()
        )
        assert response.status_code == 200, response.text
        return str(response.json()["counterparty_id"])


@pytest.fixture
async def enabled(
    client: httpx.AsyncClient, world: BookingWorld, manager_a: FakeUser, idp: FakeIdp
) -> Documents:
    docs = Documents(client, world.a.tenant_id, manager_a, idp)
    await docs.enable()
    return docs


async def chunks(data: bytes, size: int = 1 << 20) -> AsyncIterator[bytes]:
    for start in range(0, len(data), size):
        yield data[start : start + size]


class Unread:
    """A request body that records whether the server started reading it."""

    def __init__(self) -> None:
        self.read = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        self.read = True
        yield PDF


async def scalar(pool: RuntimePool, business: UUID, query: str, *params: object) -> object:
    async with tenant_transaction(pool, business) as conn:
        row = await (await conn.execute(query, params)).fetchone()
    assert row is not None
    return row[0]


async def test_documents_use_real_registry_and_require_explicit_publication(
    client: httpx.AsyncClient, world: BookingWorld, manager_a: FakeUser, idp: FakeIdp
) -> None:
    docs = Documents(client, world.a.tenant_id, manager_a, idp)
    listed = await docs.get("/documents")
    assert listed.status_code == 200, listed.text
    assert listed.json() == {
        "schema_version": 1,
        "business_id": str(docs.business),
        "file_uploads": "enabled",
        "items": [],
        "next_cursor": None,
    }
    for refused in (await docs.upload(), await docs.save(uuid7(), doc())):
        assert (refused.status_code, refused.json()["error"]["code"]) == (409, "MODULE_DISABLED")
    # Without the test override the registry still refuses the module.
    await docs.config.profile(manager_a, docs.business, 0, [1])
    assert (await docs.config.draft(manager_a, docs.business, 0, ALL_MODULES)).status_code == 200
    refused = await docs.config.step(manager_a, docs.business, 1, "validate", 1)
    assert refused.status_code == 422, refused.text
    assert ("MODULE_NOT_READY", "documents") in {
        (p["code"], p["module_id"]) for p in refused.json()["error"]["details"]["problems"]
    }
    with verified_modules("documents"):
        published = await docs.config.publish(manager_a, docs.business, 1, ALL_MODULES)
    assert published["state"] == "published"
    assert (await docs.upload()).status_code == 200


async def test_upload_keeps_validated_metadata_and_reference_only_receipts(
    enabled: Documents, app_pool: RuntimePool
) -> None:
    file_id, key = uuid7(), str(uuid7())
    first = await enabled.upload(name="FAKE Agreement.pdf", file_id=file_id, key=key)
    assert first.status_code == 200, first.text
    assert first.json() == {
        "schema_version": 1,
        "business_id": str(enabled.business),
        "file_id": str(file_id),
        "media_type": "application/pdf",
        "size_bytes": len(PDF),
        "sha256": hashlib.sha256(PDF).hexdigest(),
        "file_name": "FAKE Agreement.pdf",
        "validator_version": VALIDATOR_VERSION,
        "scan_status": "not_scanned",
        "uploaded_at": first.json()["uploaded_at"],
    }
    assert (await enabled.upload(file_id=file_id, key=key)).json() == first.json()
    assert (await enabled.get(f"/document-files/{file_id}")).json() == first.json()
    assert (await enabled.get(f"/document-files/{uuid7()}")).status_code == 404
    reused = await enabled.upload(png(), media="image/png", name="x.png", key=key)
    assert reused.status_code == 422, reused.text
    taken = await enabled.upload(png(), media="image/png", name="x.png", file_id=file_id)
    assert taken.status_code == 409, taken.text
    unicode = await enabled.upload(jpeg(), media="image/jpeg", name="../Договор‮ №1.jpeg")
    assert unicode.status_code == 200, unicode.text
    assert unicode.json()["file_name"] == "Договор №1.jpg"
    async with tenant_transaction(app_pool, enabled.business) as conn:
        assert (
            await (await conn.execute("select count(*) from gba.document_files")).fetchone()
        ) == (2,)
        audits = await (
            await conn.execute(
                "select details from gba.audit_events where action = 'document_file.uploaded'"
            )
        ).fetchall()
        assert [set(row[0]) for row in audits] == [
            {"size_bytes", "media_type", "sha256", "validator_version"}
        ] * 2
        assert "FAKE Agreement" not in str(audits)
        assert "Договор" not in str(audits)
        receipts = await (
            await conn.execute(
                "select response_body from gba.idempotency_keys "
                "where operation = 'business.document_file.upload'"
            )
        ).fetchall()
        assert [set(row[0]) for row in receipts] == [{"file_id"}] * 2


async def test_upload_refusals_happen_before_storage(
    enabled: Documents, app_pool: RuntimePool
) -> None:
    overhead = len(png(text_bytes=1)) - 1
    exact = png(text_bytes=MAX_FILE_BYTES - overhead)
    assert len(exact) == MAX_FILE_BYTES
    cases = [
        (await enabled.upload(media="text/plain"), 415, "UNSUPPORTED_MEDIA_TYPE"),
        (await enabled.upload(media="image/png"), 415, "FILE_TYPE_MISMATCH"),
        (await enabled.upload(pdf(b"<< /JavaScript (FAKE) >>")), 422, "FILE_ACTIVE_CONTENT"),
        (await enabled.upload(b""), 422, "FILE_UNREADABLE"),
        (await enabled.upload(raw_name="%FF.pdf"), 422, "INVALID_FILE_NAME"),
        (await enabled.upload(exact + b"x", media="image/png"), 413, "FILE_TOO_LARGE"),
        (
            await enabled.upload(chunks(exact + b"x"), media="image/png"),
            413,
            "FILE_TOO_LARGE",
        ),
    ]
    assert [(r.status_code, r.json()["error"]["code"]) for r, _, _ in cases] == [
        (status, code) for _, status, code in cases
    ]
    assert "transfer-encoding" in cases[-1][0].request.headers
    assert await scalar(app_pool, enabled.business, "select count(*) from gba.document_files") == 0
    assert (
        await scalar(
            app_pool,
            enabled.business,
            "select count(*) from gba.idempotency_keys "
            "where operation = 'business.document_file.upload'",
        )
        == 0
    )
    accepted = await enabled.upload(exact, media="image/png", name="FAKE.png")
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["size_bytes"] == MAX_FILE_BYTES
    streamed = await enabled.upload(chunks(exact), media="image/png", name="FAKE.png")
    assert streamed.status_code == 200, streamed.text


async def test_staging_refuses_uploads_before_reading_the_body(
    enabled: Documents, app_pool: RuntimePool, idp: FakeIdp
) -> None:
    app = create_app(Settings(environment="test"), pool=app_pool, token_verifier=idp.verifier())
    app.state.settings = app.state.settings.model_copy(update={"environment": "staging"})
    body = Unread()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://api.test"
    ) as http:
        staging = Documents(http, enabled.business, enabled.user, idp)
        refused = await staging.upload(body)
        assert refused.status_code == 503, refused.text
        assert refused.json()["error"]["code"] == "FILE_SCANNING_NOT_CONFIGURED"
        assert body.read is False
        assert (await staging.get("/documents")).json()["file_uploads"] == "scanner_not_configured"
        # Documents without files remain available.
        assert (await staging.save(uuid7(), doc())).status_code == 200
    assert await scalar(app_pool, enabled.business, "select count(*) from gba.document_files") == 0


async def test_versions_history_conflicts_and_search(enabled: Documents) -> None:
    file_id = await enabled.stored()
    subject, key = uuid7(), str(uuid7())
    original = doc(file_id=file_id, valid_from="2026-01-01", valid_until="2026-12-31")
    first = await enabled.save(subject, original, key)
    assert first.status_code == 200, first.text
    assert (first.json()["revision"], first.json()["file"]["file_id"]) == (1, file_id)
    assert first.json()["file"]["scan_status"] == "not_scanned"
    second = await enabled.save(subject, doc(expected_revision=1, title="FAKE Supply v2"))
    assert second.status_code == 200, second.text
    assert (second.json()["revision"], second.json()["file"]) == (2, None)
    assert (await enabled.save(subject, original, key)).json() == first.json()
    assert (await enabled.get(f"/documents/{subject}", revision=1)).json() == first.json()
    assert (await enabled.get(f"/documents/{subject}")).json() == second.json()
    assert (await enabled.save(subject, original)).status_code == 409
    assert (await enabled.save(uuid7(), original, key)).status_code == 422
    unknown = await enabled.save(uuid7(), doc(file_id=str(uuid7())))
    assert (unknown.status_code, unknown.json()["error"]["code"]) == (422, "INVALID_REFERENCE")
    for invalid in (
        doc(valid_from="2026-02-01", valid_until="2026-01-31"),
        doc(title=" \t "),
        doc(title="FAKE\x07"),
        doc(category="contract"),
        doc(expected_revision="0"),
    ):
        assert (await enabled.save(uuid7(), invalid)).status_code == 422
    history = (await enabled.get(f"/documents/{subject}/versions", limit=1)).json()
    assert ([r["revision"] for r in history["items"]], history["next_cursor"]) == ([2], 2)
    older = (await enabled.get(f"/documents/{subject}/versions", before=2)).json()
    assert [(r["revision"], r["file_id"]) for r in older["items"]] == [(1, file_id)]
    for missing in (f"/documents/{uuid7()}", f"/documents/{uuid7()}/versions"):
        assert (await enabled.get(missing)).status_code == 404
    assert (await enabled.get(f"/documents/{subject}", revision=3)).status_code == 404
    await enabled.create(title="FAKE 100% Certificate", category="certificate")
    await enabled.create(title="FAKE alpha report", category="report")
    archived = await enabled.create(title="FAKE Archived invoice", archived=True)
    titles = [r["title"] for r in (await enabled.get("/documents")).json()["items"]]
    assert titles == ["FAKE 100% Certificate", "FAKE alpha report", "FAKE Supply v2"]
    assert [r["title"] for r in (await enabled.get("/documents", q="%")).json()["items"]] == [
        "FAKE 100% Certificate"
    ]
    assert [
        r["document_id"] for r in (await enabled.get("/documents", archived=True)).json()["items"]
    ] == [archived["document_id"]]
    page = (await enabled.get("/documents", limit=2)).json()
    rest = (await enabled.get("/documents", limit=2, after=page["next_cursor"])).json()
    assert [r["title"] for r in page["items"] + rest["items"]] == titles
    assert rest["next_cursor"] is None


async def test_download_is_a_verified_attachment_with_a_separate_csp(
    enabled: Documents, app_pool: RuntimePool
) -> None:
    file_id = await enabled.stored(name="Договор FAKE.pdf")
    subject = uuid7()
    assert (await enabled.save(subject, doc(file_id=file_id))).status_code == 200
    assert (await enabled.save(subject, doc(expected_revision=1))).status_code == 200
    response = await enabled.get(f"/documents/{subject}/versions/1/file")
    assert response.status_code == 200, response.text
    assert response.content == PDF
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == (
        "attachment; filename=\"_______ FAKE.pdf\"; filename*=UTF-8''"
        + quote("Договор FAKE.pdf", safe="")
    )
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cross-origin-resource-policy"] == "same-origin"
    assert response.headers["x-file-sha256"] == hashlib.sha256(PDF).hexdigest()
    assert response.headers.get_list("content-security-policy") == [
        "default-src 'none'; sandbox",
        "frame-ancestors 'none'",
    ]
    for missing in (
        f"/documents/{subject}/versions/2/file",
        f"/documents/{subject}/versions/3/file",
        f"/documents/{uuid7()}/versions/1/file",
    ):
        assert (await enabled.get(missing)).status_code == 404
    async with tenant_transaction(app_pool, enabled.business) as conn:
        audits = await (
            await conn.execute(
                "select target_id, details from gba.audit_events "
                "where action = 'document_file.downloaded'"
            )
        ).fetchall()
    assert audits == [(file_id, {"document_id": str(subject), "revision": 1})]


async def test_download_refuses_content_that_fails_its_integrity_check(
    enabled: Documents, owner_conn: psycopg.Connection, app_pool: RuntimePool
) -> None:
    file_id = await enabled.stored()
    subject = uuid7()
    assert (await enabled.save(subject, doc(file_id=file_id))).status_code == 200
    tampered = PDF[:-1] + b" "
    owner_conn.execute("alter table gba.document_files disable trigger document_files_immutable")
    owner_conn.execute("alter table gba.document_files drop constraint document_files_content_hash")
    try:
        with owner_tenant_transaction(owner_conn, enabled.business):
            owner_conn.execute(
                "update gba.document_files set content = %b where id = %s", (tampered, file_id)
            )
        response = await enabled.get(f"/documents/{subject}/versions/1/file")
        assert response.status_code == 500, response.text
        assert response.json()["error"]["code"] == "FILE_INTEGRITY_FAILED"
        assert PDF[:20] not in response.content
    finally:
        with owner_tenant_transaction(owner_conn, enabled.business):
            owner_conn.execute(
                "update gba.document_files set content = %b where id = %s", (PDF, file_id)
            )
        owner_conn.execute(
            "alter table gba.document_files add constraint document_files_content_hash "
            "check (pg_catalog.encode(pg_catalog.sha256(content), 'hex') = sha256)"
        )
        owner_conn.execute("alter table gba.document_files enable trigger document_files_immutable")
    assert (
        await scalar(
            app_pool,
            enabled.business,
            "select count(*) from gba.audit_events where action = 'document_file.downloaded'",
        )
        == 0
    )
    assert (await enabled.get(f"/documents/{subject}/versions/1/file")).content == PDF


async def test_module_disable_keeps_reads_downloads_and_replays_but_stops_new_writes(
    enabled: Documents, app_pool: RuntimePool
) -> None:
    upload_key, save_key, link_key = (str(uuid7()) for _ in range(3))
    file_id, sent = uuid7(), Unread()
    uploaded = await enabled.upload(sent, file_id=file_id, key=upload_key)
    assert (uploaded.status_code, sent.read) == (200, True)
    subject = uuid7()
    saved = await enabled.save(subject, doc(file_id=str(file_id)), save_key)
    assert saved.status_code == 200, saved.text
    counterparty = await enabled.counterparty()
    linked = await enabled.link(
        subject, {"action": "link", "counterparty_id": counterparty}, link_key
    )
    assert linked.status_code == 200, linked.text
    await enabled.config.publish(enabled.user, enabled.business, 1, ["booking_resources"])
    assert (await enabled.get(f"/documents/{subject}")).json() == saved.json()
    assert (await enabled.get("/documents")).json()["items"][0]["document_id"] == str(subject)
    assert (await enabled.get(f"/documents/{subject}/versions")).status_code == 200
    assert (await enabled.get(f"/documents/{subject}/versions/1/file")).content == PDF
    assert (await enabled.get(f"/document-files/{file_id}")).json() == uploaded.json()
    assert (await enabled.get(f"/documents/{subject}/counterparty-links")).status_code == 200
    assert (await enabled.upload(file_id=file_id, key=upload_key)).json() == uploaded.json()
    assert (await enabled.save(subject, doc(file_id=str(file_id)), save_key)).json() == saved.json()
    assert (
        await enabled.link(subject, {"action": "link", "counterparty_id": counterparty}, link_key)
    ).json() == linked.json()
    body = Unread()
    attempts = [
        await enabled.upload(body),
        await enabled.save(uuid7(), doc()),
        await enabled.save(subject, doc(expected_revision=1)),
        await enabled.link(
            subject,
            {"action": "unlink", "counterparty_id": counterparty, "expected_sequence": 1},
        ),
    ]
    assert [(r.status_code, r.json()["error"]["code"]) for r in attempts] == [
        (409, "MODULE_DISABLED")
    ] * 4
    # A new key is refused before the body is read; only a stored key reads it.
    assert body.read is False
    async with tenant_transaction(app_pool, enabled.business) as conn:
        with pytest.raises(psycopg.Error, match="documents module is disabled"):
            async with conn.transaction():
                await conn.execute(
                    "insert into gba.documents (tenant_id, id, created_by) values (%s, %s, %s)",
                    (enabled.business, uuid7(), enabled.user.user_id),
                )


async def test_links_also_need_the_counterparties_module(
    enabled: Documents, app_pool: RuntimePool
) -> None:
    counterparty = await enabled.counterparty()
    subject = str((await enabled.create())["document_id"])
    with verified_modules("documents"):
        await enabled.config.publish(
            enabled.user, enabled.business, 1, ["booking_resources", "documents"]
        )
    refused = await enabled.link(subject, {"action": "link", "counterparty_id": counterparty})
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["details"] == {"module_id": "counterparties"}
    assert (await enabled.create())["revision"] == 1
    async with tenant_transaction(app_pool, enabled.business) as conn:
        with pytest.raises(psycopg.Error, match="counterparties module is disabled"):
            async with conn.transaction():
                await conn.execute(
                    "insert into gba.document_counterparty_links (tenant_id, document_id, "
                    "counterparty_id, sequence, action, decided_by) "
                    "values (%s, %s, %s, 1, 'linked', %s)",
                    (enabled.business, subject, counterparty, enabled.user.user_id),
                )


async def test_counterparty_links_follow_document_and_card_state(
    enabled: Documents, app_pool: RuntimePool
) -> None:
    a = await enabled.counterparty(display_name="FAKE Duplicate")
    b = await enabled.counterparty(display_name="FAKE Survivor")
    subject = str((await enabled.create())["document_id"])
    other = str((await enabled.create(title="FAKE Other"))["document_id"])
    body, key = {"action": "link", "counterparty_id": a}, str(uuid7())
    linked = await enabled.link(subject, body, key)
    assert linked.status_code == 200, linked.text
    assert (linked.json()["link"]["sequence"], linked.json()["link"]["action"]) == (1, "linked")
    assert (await enabled.link(subject, body, key)).json() == linked.json()
    again = await enabled.link(subject, body)
    assert (again.status_code, again.json()["error"]["code"]) == (409, "DOCUMENT_ALREADY_LINKED")
    unknown = await enabled.link(subject, {"action": "link", "counterparty_id": str(uuid7())})
    assert unknown.status_code == 422
    assert (await enabled.link(uuid7(), body)).status_code == 404
    links = (await enabled.get(f"/documents/{subject}/counterparty-links")).json()
    assert [(r["counterparty_id"], r["display_name"]) for r in links["current"]] == [
        (a, "FAKE Duplicate")
    ]
    merge = await enabled.client.post(
        f"{enabled.base}/counterparties/{a}/match-decisions",
        json={
            "decision": "merge",
            "into_id": b,
            "expected_revision": 1,
            "into_expected_revision": 1,
        },
        headers=enabled.headers(),
    )
    assert merge.status_code == 200, merge.text
    aggregate = (await enabled.get(f"/counterparties/{b}/documents")).json()["items"]
    assert [(r["document"]["document_id"], r["counterparty_id"]) for r in aggregate] == [
        (subject, a)
    ]
    merged = await enabled.link(other, body)
    assert (merged.status_code, merged.json()["error"]["code"]) == (
        409,
        "COUNTERPARTY_STATE_INVALID",
    )
    unlink = {"action": "unlink", "counterparty_id": a, "expected_sequence": 2}
    assert (await enabled.link(subject, unlink)).status_code == 409
    unlinked = await enabled.link(subject, {**unlink, "expected_sequence": 1})
    assert unlinked.status_code == 200, unlinked.text
    assert unlinked.json()["link"]["sequence"] == 2
    assert (await enabled.link(subject, {**unlink, "expected_sequence": 2})).status_code == 422
    assert (await enabled.get(f"/counterparties/{b}/documents")).json()["items"] == []
    links = (await enabled.get(f"/documents/{subject}/counterparty-links")).json()
    assert links["current"] == []
    assert [(r["action"], r["sequence"]) for r in links["history"]] == [
        ("unlinked", 2),
        ("linked", 1),
    ]
    assert (await enabled.save(other, doc(expected_revision=1, archived=True))).status_code == 200
    archived = await enabled.link(other, {"action": "link", "counterparty_id": b})
    assert (archived.status_code, archived.json()["error"]["code"]) == (
        409,
        "DOCUMENT_STATE_INVALID",
    )
    assert (await enabled.get(f"/counterparties/{uuid7()}/documents")).status_code == 404
    async with tenant_transaction(app_pool, enabled.business) as conn:
        audits = await (
            await conn.execute(
                "select action, details from gba.audit_events "
                "where action like 'document.counterparty_%%' order by id"
            )
        ).fetchall()
    assert audits == [
        ("document.counterparty_linked", {"counterparty_id": a, "sequence": 1}),
        ("document.counterparty_unlinked", {"counterparty_id": a, "sequence": 2}),
    ]


async def test_counterparty_documents_page_by_link(enabled: Documents) -> None:
    record = await enabled.counterparty()
    subjects = [str((await enabled.create(title=f"FAKE {i}"))["document_id"]) for i in range(3)]
    for subject in subjects:
        response = await enabled.link(subject, {"action": "link", "counterparty_id": record})
        assert response.status_code == 200, response.text
    first = (await enabled.get(f"/counterparties/{record}/documents", limit=2)).json()
    rest = (
        await enabled.get(
            f"/counterparties/{record}/documents", limit=2, after=first["next_cursor"]
        )
    ).json()
    ordered = [r["document"]["document_id"] for r in first["items"] + rest["items"]]
    assert ordered == subjects[::-1]
    assert rest["next_cursor"] is None


async def test_direct_sql_cannot_rewrite_documents_or_forge_links(
    enabled: Documents, owner_conn: psycopg.Connection
) -> None:
    file_id = await enabled.stored()
    subject = str((await enabled.create(file_id=file_id))["document_id"])
    archived = str((await enabled.create(archived=True))["document_id"])
    counterparty = await enabled.counterparty()
    assert (
        await enabled.link(subject, {"action": "link", "counterparty_id": counterparty})
    ).status_code == 200
    forged_link = (
        "insert into gba.document_counterparty_links (tenant_id, document_id, counterparty_id, "
        "sequence, action, decided_by) values (%s, %s, %s, %s, %s, %s)"
    )
    user = enabled.user.user_id
    with owner_tenant_transaction(owner_conn, enabled.business):
        for statement, params in (
            ("update gba.document_files set file_name = 'FAKE rename.pdf'", ()),
            ("delete from gba.document_files", ()),
            ("update gba.document_versions set title = 'FAKE rewrite'", ()),
            ("delete from gba.documents", ()),
            ("update gba.document_counterparty_links set action = 'unlinked'", ()),
            ("delete from gba.document_counterparty_links", ()),
            (
                "insert into gba.document_versions (tenant_id, document_id, revision, title, "
                "category, archived, created_by) values (%s, %s, 3, 'FAKE', 'other', false, %s)",
                (enabled.business, subject, user),
            ),
            (forged_link, (enabled.business, subject, counterparty, 3, "unlinked", user)),
            (forged_link, (enabled.business, subject, counterparty, 2, "linked", user)),
            (forged_link, (enabled.business, archived, counterparty, 1, "linked", user)),
        ):
            with pytest.raises(psycopg.errors.CheckViolation), owner_conn.transaction():
                owner_conn.execute(statement, params)


async def test_competing_commands_have_one_winner(enabled: Documents) -> None:
    subject = uuid7()
    results = await asyncio.gather(*(enabled.save(subject, doc()) for _ in range(2)))
    assert sorted(r.status_code for r in results) == [200, 409]
    file_id = uuid7()
    uploads = await asyncio.gather(
        enabled.upload(file_id=file_id), enabled.upload(png(), media="image/png", file_id=file_id)
    )
    assert sorted(r.status_code for r in uploads) == [200, 409]
    counterparty = await enabled.counterparty()
    body = {"action": "link", "counterparty_id": counterparty}
    links = await asyncio.gather(*(enabled.link(subject, body) for _ in range(2)))
    assert sorted(r.status_code for r in links) == [200, 409]
    key = str(uuid7())
    retries = await asyncio.gather(
        *(
            enabled.save(subject, doc(expected_revision=1, title="FAKE retry"), key)
            for _ in range(2)
        )
    )
    assert [r.status_code for r in retries] == [200, 200]
    assert retries[0].json() == retries[1].json()


async def test_isolation_foreign_files_branch_sessions_and_revocation(
    enabled: Documents,
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager_b: FakeUser,
    idp: FakeIdp,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
) -> None:
    foreign = Documents(client, world.b.tenant_id, manager_b, idp)
    await foreign.enable()
    foreign_file = await foreign.stored()
    refused = await enabled.save(uuid7(), doc(file_id=foreign_file))
    assert (refused.status_code, refused.json()["error"]["code"]) == (422, "INVALID_REFERENCE")
    assert (await enabled.get(f"/document-files/{foreign_file}")).status_code == 404
    subject, key = uuid7(), str(uuid7())
    assert (await enabled.save(subject, doc(), key)).status_code == 200
    assert (await foreign.get(f"/documents/{subject}")).status_code == 404
    async with unscoped_transaction(app_pool) as conn:
        assert (await (await conn.execute("select * from gba.document_versions")).fetchall()) == []
    async with tenant_transaction(app_pool, enabled.business) as conn:
        await conn.execute(
            "select pg_catalog.set_config('gba.location_id', %s, true)", (str(world.a.location_id),)
        )
        for table in (
            "document_files",
            "documents",
            "document_versions",
            "document_counterparty_links",
        ):
            query = sql.SQL("select * from {}").format(sql.Identifier("gba", table))
            assert (await (await conn.execute(query)).fetchall()) == []
    with owner_tenant_transaction(owner_conn, enabled.business):
        owner_conn.execute(
            "update gba.memberships set status = 'revoked' where user_id = %s",
            (enabled.user.user_id,),
        )
    assert (await enabled.save(subject, doc(), key)).status_code == 403


async def test_active_delegation_does_not_admit_document_access(
    enabled: Documents, world: BookingWorld, owner_conn: psycopg.Connection, idp: FakeIdp
) -> None:
    owners = [seed_user(owner_conn, f"FAKE-doc-grant-owner-{uuid7()}") for _ in range(2)]
    for salon, user in zip((world.a, world.b), owners, strict=True):
        add_membership(owner_conn, tenant_id=salon.tenant_id, user_id=user.user_id, role="owner")
    await Parties(enabled.client, idp, world).active_grant(owners[0], owners[1], [owners[1]])
    file_id = await enabled.stored()
    subject = str((await enabled.create(file_id=file_id))["document_id"])
    delegate = Documents(enabled.client, enabled.business, owners[1], idp)
    for suffix in (
        "/documents",
        f"/documents/{subject}",
        f"/documents/{subject}/versions",
        f"/documents/{subject}/versions/1/file",
        f"/documents/{subject}/counterparty-links",
        f"/document-files/{file_id}",
    ):
        assert (await delegate.get(suffix)).status_code == 403, suffix
    for write in (
        await delegate.upload(),
        await delegate.save(subject, doc(expected_revision=1)),
        await delegate.link(subject, {"action": "link", "counterparty_id": str(uuid7())}),
    ):
        assert write.status_code == 403, write.text


@pytest.mark.parametrize(
    ("role", "scoped"), [("artist", False), ("front_desk", False), ("manager", True)]
)
async def test_documents_deny_unapproved_members(
    client: httpx.AsyncClient,
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    idp: FakeIdp,
    role: str,
    scoped: bool,
) -> None:
    user = seed_user(owner_conn, f"FAKE-document-role-{uuid7()}")
    add_membership(
        owner_conn,
        tenant_id=world.a.tenant_id,
        user_id=user.user_id,
        role=role,
        location_id=world.a.location_id if scoped else None,
    )
    docs = Documents(client, world.a.tenant_id, user, idp)
    assert (await docs.get("/documents")).status_code == 403
    assert (await docs.upload()).status_code == 403


async def test_documents_deny_foreign_company_and_platform_support(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager_b: FakeUser,
    owner_conn: psycopg.Connection,
    idp: FakeIdp,
) -> None:
    support = seed_user(owner_conn, f"FAKE-document-support-{uuid7()}")
    grant_platform_admin(owner_conn, user_id=support.user_id, granted_by="FAKE-test")
    for user in (manager_b, support):
        docs = Documents(client, world.a.tenant_id, user, idp)
        assert (await docs.get("/documents")).status_code == 403
        assert (await docs.save(uuid7(), doc())).status_code == 403


@pytest.mark.parametrize(
    "table", ["document_files", "documents", "document_versions", "document_counterparty_links"]
)
async def test_guard_rejects_weakened_document_scope(
    enabled: Documents, owner_conn: psycopg.Connection, table: str
) -> None:
    policy, relation = sql.Identifier(f"{table}_unrestricted_scope"), sql.Identifier("gba", table)
    try:
        owner_conn.execute(
            sql.SQL("alter policy {} on {} using (true) with check (true)").format(policy, relation)
        )
        response = await enabled.get("/documents")
        assert response.status_code == 503, response.text
        assert (await enabled.client.get("/health/ready")).status_code == 503
    finally:
        owner_conn.execute(
            sql.SQL(
                "alter policy {} on {} using (gba.current_location_id() is null) "
                "with check (gba.current_location_id() is null)"
            ).format(policy, relation)
        )
    assert (await enabled.client.get("/health/ready")).status_code == 200


@pytest.mark.parametrize(
    ("table", "trigger", "module", "damage"),
    [
        ("document_files", "document_files_require_module", "documents", "disabled"),
        ("documents", "documents_require_module", "documents", "when_false"),
        ("document_versions", "document_versions_require_module", "documents", "wrong_argument"),
        (
            "document_counterparty_links",
            "document_counterparty_links_require_counterparties",
            "counterparties",
            "wrong_argument",
        ),
        (
            "document_counterparty_links",
            "document_counterparty_links_require_module",
            "documents",
            "dropped",
        ),
    ],
)
async def test_guard_rejects_changed_document_gates(
    client: httpx.AsyncClient,
    owner_conn: psycopg.Connection,
    table: str,
    trigger: str,
    module: str,
    damage: str,
) -> None:
    original = (
        f"create trigger {trigger} before insert on gba.{table} "
        f"for each row execute function gba.require_enabled_module('{module}')"
    )
    try:
        if damage == "disabled":
            owner_conn.execute(f"alter table gba.{table} disable trigger {trigger}")
        else:
            owner_conn.execute(f"drop trigger {trigger} on gba.{table}")
            if damage == "wrong_argument":
                other = "documents" if module == "counterparties" else "counterparties"
                owner_conn.execute(original.replace(f"'{module}'", f"'{other}'"))
            elif damage == "when_false":
                owner_conn.execute(original.replace("for each row", "for each row when (false)"))
        assert (await client.get("/health/ready")).status_code == 503
    finally:
        owner_conn.execute(f"drop trigger if exists {trigger} on gba.{table}")
        owner_conn.execute(original)
    assert (await client.get("/health/ready")).status_code == 200


async def test_identical_retry_after_key_expiry_returns_the_stored_file(
    enabled: Documents, owner_conn: psycopg.Connection
) -> None:
    file_id, key = uuid7(), str(uuid7())
    name = "😀" * 130 + ".pdf"
    first = await enabled.upload(name=name, file_id=file_id, key=key)
    assert first.status_code == 200, first.text
    assert len(first.json()["file_name"]) == 120
    with owner_tenant_transaction(owner_conn, enabled.business):
        owner_conn.execute(
            "update gba.idempotency_keys set expires_at = now() - interval '1 second' "
            "where idempotency_key = %s",
            (key,),
        )
    assert (await enabled.upload(name=name, file_id=file_id, key=key)).json() == first.json()
    changed = await enabled.upload(png(), media="image/png", name="x.png", file_id=file_id)
    assert changed.status_code == 409
