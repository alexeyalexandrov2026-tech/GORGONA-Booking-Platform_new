"""Cloudflare R2 S3-compatible media storage via zero-dependency stdlib AWS SigV4."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import http.client
import logging
import os
import re
import urllib.parse
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid7

from psycopg.rows import dict_row

from gorgona_booking.db.pool import RuntimeConnection

_LOG = logging.getLogger(__name__)
MAX_MEDIA_BYTES = 5 * 1024 * 1024  # 5 MiB
_FILENAME_CLEAN_RE = re.compile(r"[^a-zA-Z0-9._-]+")

MediaKind = Literal["logo", "cover", "service_photo", "gallery"]


def _detect_image_type(data: bytes) -> tuple[str, str]:
    """Validate image magic bytes strictly (PNG, JPEG, WEBP only; SVG blocked for XSS safety)."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ("image/png", "png")
    if data.startswith(b"\xff\xd8\xff"):
        return ("image/jpeg", "jpg")
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ("image/webp", "webp")
    raise ValueError("Unsupported image format. Upload PNG, JPEG, or WEBP only.")


def _r2_config() -> tuple[str, str, str, str] | None:
    endpoint = os.environ.get("GBA_R2_ENDPOINT", "").strip().rstrip("/")
    access_key = os.environ.get("GBA_R2_ACCESS_KEY_ID", "").strip()
    secret_key = os.environ.get("GBA_R2_SECRET_ACCESS_KEY", "").strip()
    bucket = os.environ.get("GBA_R2_BUCKET", "gorgona-media").strip() or "gorgona-media"
    if not endpoint or not access_key or not secret_key:
        return None
    return (endpoint, access_key, secret_key, bucket)


def _sigv4_headers(
    *,
    method: str,
    host: str,
    canonical_uri: str,
    payload_hash: str,
    access_key: str,
    secret_key: str,
    content_type: str | None = None,
) -> dict[str, str]:
    now = datetime.now(UTC)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    region = "auto"
    service = "s3"

    hdrs: dict[str, str] = {
        "host": host,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
    }
    if content_type:
        hdrs["content-type"] = content_type
    sorted_keys = sorted(hdrs.keys())
    canonical_headers = "".join(f"{k}:{hdrs[k]}\n" for k in sorted_keys)
    signed_headers = ";".join(sorted_keys)
    canonical_request = "\n".join(
        [method, canonical_uri, "", canonical_headers, signed_headers, payload_hash]
    )
    credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            credential_scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )

    def _sign(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    k_date = _sign(f"AWS4{secret_key}".encode(), date_stamp)
    k_region = _sign(k_date, region)
    k_service = _sign(k_region, service)
    k_signing = _sign(k_service, "aws4_request")
    signature = hmac.new(k_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    out = {
        "Host": host,
        "x-amz-date": amz_date,
        "x-amz-content-sha256": payload_hash,
        "Authorization": (
            f"AWS4-HMAC-SHA256 Credential={access_key}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        ),
    }
    if content_type:
        out["Content-Type"] = content_type
    return out


def _r2_request_sync(
    method: str,
    object_key: str,
    data: bytes = b"",
    content_type: str | None = None,
) -> tuple[int, bytes] | None:
    cfg = _r2_config()
    if cfg is None:
        return None
    endpoint, access_key, secret_key, bucket = cfg
    parsed = urllib.parse.urlparse(endpoint)
    host = parsed.netloc
    encoded_key = urllib.parse.quote(object_key, safe="/")
    canonical_uri = f"/{bucket}/{encoded_key}"
    payload_hash = hashlib.sha256(data).hexdigest()
    headers = _sigv4_headers(
        method=method,
        host=host,
        canonical_uri=canonical_uri,
        payload_hash=payload_hash,
        access_key=access_key,
        secret_key=secret_key,
        content_type=content_type,
    )
    conn = http.client.HTTPSConnection(host, 443, timeout=15.0)
    try:
        conn.request(method, canonical_uri, body=data if method == "PUT" else None, headers=headers)
        resp = conn.getresponse()
        body = resp.read()
        return (resp.status, body)
    except Exception as exc:
        _LOG.warning("Cloudflare R2 %s failed: %s", method, type(exc).__name__)
        return None
    finally:
        conn.close()


async def upload_media_asset(
    conn: RuntimeConnection,
    *,
    tenant_id: UUID,
    kind: MediaKind,
    filename: str,
    data: bytes,
    user_id: UUID | None,
) -> dict[str, Any]:
    if not data or len(data) > MAX_MEDIA_BYTES:
        raise ValueError(f"File must be between 1 byte and {MAX_MEDIA_BYTES // (1024 * 1024)} MiB")
    content_type, ext = _detect_image_type(data)
    asset_id = uuid7()
    clean_name = _FILENAME_CLEAN_RE.sub("_", filename.strip())[:120] or f"{kind}.{ext}"
    object_key = f"tenants/{tenant_id}/{kind}/{asset_id}.{ext}"
    sha256 = hashlib.sha256(data).hexdigest()

    r2_res = await asyncio.to_thread(_r2_request_sync, "PUT", object_key, data, content_type)
    if r2_res is not None and r2_res[0] in (200, 201):
        backend = "r2"
        inline_blob: bytes | None = None
    else:
        backend = "inline"
        inline_blob = data

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            INSERT INTO gba.media_assets
                (id, tenant_id, kind, object_key, filename, content_type, size_bytes,
                 sha256, storage_backend, inline_data, uploaded_by_user_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, kind, object_key, filename, content_type, size_bytes, sha256,
                      storage_backend, created_at
            """,
            (
                asset_id,
                tenant_id,
                kind,
                object_key,
                clean_name,
                content_type,
                len(data),
                sha256,
                backend,
                inline_blob,
                user_id,
            ),
        )
        row = await cur.fetchone()
    assert row is not None  # noqa: S101
    return dict(row)


async def list_media_assets(
    conn: RuntimeConnection, *, tenant_id: UUID, kind: str | None = None
) -> list[dict[str, Any]]:
    async with conn.cursor(row_factory=dict_row) as cur:
        if kind:
            await cur.execute(
                """
                SELECT id, kind, object_key, filename, content_type, size_bytes, sha256,
                       storage_backend, created_at
                FROM gba.media_assets
                WHERE tenant_id = %s AND kind = %s
                ORDER BY created_at DESC
                LIMIT 50
                """,
                (tenant_id, kind),
            )
        else:
            await cur.execute(
                """
                SELECT id, kind, object_key, filename, content_type, size_bytes, sha256,
                       storage_backend, created_at
                FROM gba.media_assets
                WHERE tenant_id = %s
                ORDER BY created_at DESC
                LIMIT 50
                """,
                (tenant_id,),
            )
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def read_media_asset_bytes(
    conn: RuntimeConnection, *, tenant_id: UUID, asset_id: UUID
) -> tuple[str, bytes] | None:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT object_key, content_type, storage_backend, inline_data
            FROM gba.media_assets
            WHERE tenant_id = %s AND id = %s
            """,
            (tenant_id, asset_id),
        )
        row = await cur.fetchone()
    if row is None:
        return None
    ctype = str(row["content_type"])
    if row["storage_backend"] == "r2":
        r2_res = await asyncio.to_thread(_r2_request_sync, "GET", str(row["object_key"]))
        if r2_res is not None and r2_res[0] == 200:
            return (ctype, r2_res[1])
        return None
    blob = row["inline_data"]
    if blob is None:
        return None
    return (ctype, bytes(blob))


async def delete_media_asset(conn: RuntimeConnection, *, tenant_id: UUID, asset_id: UUID) -> bool:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            DELETE FROM gba.media_assets
            WHERE tenant_id = %s AND id = %s
            RETURNING object_key, storage_backend
            """,
            (tenant_id, asset_id),
        )
        row = await cur.fetchone()
    if row is None:
        return False
    if row["storage_backend"] == "r2":
        await asyncio.to_thread(_r2_request_sync, "DELETE", str(row["object_key"]))
    return True
