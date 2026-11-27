"""Per-tenant AES-256-GCM Encrypted Secret Vault for AMARKAL App Hub.

Security invariants:
- Every secret is encrypted with a domain-separated 256-bit key derived from the platform
  master key + tenant_id + connector_id + secret_kind, and authenticated with AES-256-GCM
  Associated Data (AAD) bound to the exact tenant, connector, kind, and key version.
- Cross-tenant ciphertext relocation or tampering fails cryptographic authentication.
- Plaintext secrets are NEVER returned to HTTP clients, audit logs, or portable exports.
- All database access runs strictly under PostgreSQL 18 ENABLE + FORCE ROW LEVEL SECURITY.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from gorgona_booking.db.pool import RuntimeConnection

SecretKind = Literal["byok_ai_key", "oauth_tokens", "plugin_credential"]
VAULT_KEY_VERSION = "v1"


@dataclass(frozen=True)
class EncryptedSecretRecord:
    key_version: str
    nonce_b64: str
    ciphertext_b64: str
    key_hint: str


@dataclass(frozen=True)
class PublicSecretMetadata:
    connector_id: str
    secret_kind: SecretKind
    key_hint: str
    metadata_public: dict[str, Any]
    updated_at: datetime


def mask_secret_hint(raw_secret: str) -> str:
    """Produce a safe non-recoverable hint (e.g., 'sk-a...9f') for UI verification."""
    clean = raw_secret.strip()
    if len(clean) <= 8:
        return "***"
    return f"{clean[:4]}...{clean[-2:]}"


def _master_key_bytes(*, environment: str) -> bytes:
    raw = (
        os.environ.get("GBA_VAULT_MASTER_KEY", "").strip()
        or os.environ.get("GBA_OAUTH_STATE_SECRET", "").strip()
        or os.environ.get("GBA_EDGE_SECRET", "").strip()
    )
    if raw:
        return hashlib.sha256(raw.encode("utf-8")).digest()
    if environment in ("staging", "production"):
        raise RuntimeError(
            "Vault master encryption key (GBA_VAULT_MASTER_KEY) is not configured in production."
        )
    return hashlib.sha256(b"amarkal-local-dev-vault-master-key").digest()


def _derive_tenant_dek(
    *,
    tenant_id: UUID,
    connector_id: str,
    secret_kind: str,
    key_version: str,
    environment: str,
) -> bytes:
    master = _master_key_bytes(environment=environment)
    context = f"amarkal-vault:{key_version}:{tenant_id}:{connector_id}:{secret_kind}".encode()
    return hmac.new(master, context, hashlib.sha256).digest()


def _aad_bytes(
    *,
    tenant_id: UUID,
    connector_id: str,
    secret_kind: str,
    key_version: str,
) -> bytes:
    return f"tid={tenant_id}|cid={connector_id}|kind={secret_kind}|ver={key_version}".encode()


def encrypt_tenant_secret(
    plaintext: str,
    *,
    tenant_id: UUID,
    connector_id: str,
    kind: SecretKind,
    environment: str,
    key_version: str = VAULT_KEY_VERSION,
    hint_source: str | None = None,
) -> EncryptedSecretRecord:
    """Encrypt a tenant secret string using AES-256-GCM with tenant-bound key and AAD."""
    clean = plaintext.strip()
    if not clean:
        raise ValueError("Secret value cannot be empty.")
    if len(clean.encode("utf-8")) > 8192:
        raise ValueError("Secret payload exceeds maximum allowed size.")
    dek = _derive_tenant_dek(
        tenant_id=tenant_id,
        connector_id=connector_id,
        secret_kind=kind,
        key_version=key_version,
        environment=environment,
    )
    aad = _aad_bytes(
        tenant_id=tenant_id,
        connector_id=connector_id,
        secret_kind=kind,
        key_version=key_version,
    )
    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(dek).encrypt(nonce, clean.encode("utf-8"), aad)
    return EncryptedSecretRecord(
        key_version=key_version,
        nonce_b64=base64.urlsafe_b64encode(nonce).decode("ascii"),
        ciphertext_b64=base64.urlsafe_b64encode(ciphertext).decode("ascii"),
        key_hint=mask_secret_hint(hint_source if hint_source is not None else clean),
    )


def decrypt_tenant_secret(
    *,
    nonce_b64: str,
    ciphertext_b64: str,
    tenant_id: UUID,
    connector_id: str,
    kind: SecretKind,
    key_version: str,
    environment: str,
) -> str:
    """Decrypt a tenant secret; raises ValueError if authentication fails."""
    dek = _derive_tenant_dek(
        tenant_id=tenant_id,
        connector_id=connector_id,
        secret_kind=kind,
        key_version=key_version,
        environment=environment,
    )
    aad = _aad_bytes(
        tenant_id=tenant_id,
        connector_id=connector_id,
        secret_kind=kind,
        key_version=key_version,
    )
    try:
        nonce = base64.urlsafe_b64decode(nonce_b64.encode("ascii"))
        ciphertext = base64.urlsafe_b64decode(ciphertext_b64.encode("ascii"))
        plain = AESGCM(dek).decrypt(nonce, ciphertext, aad)
        return plain.decode("utf-8")
    except Exception as exc:
        raise ValueError("Unable to decrypt tenant secret.") from exc


async def upsert_tenant_secret(
    conn: RuntimeConnection,
    *,
    tenant_id: UUID,
    connector_id: str,
    kind: SecretKind,
    plaintext: str,
    metadata_public: dict[str, Any],
    user_id: UUID | None,
    environment: str,
    hint_source: str | None = None,
) -> PublicSecretMetadata:
    """Encrypt and store (or rotate) a secret inside the current FORCE-RLS tenant transaction."""
    enc = encrypt_tenant_secret(
        plaintext,
        tenant_id=tenant_id,
        connector_id=connector_id,
        kind=kind,
        environment=environment,
        hint_source=hint_source,
    )
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            INSERT INTO gba.tenant_connector_secrets
                (tenant_id, connector_id, secret_kind, key_version,
                 nonce_b64, ciphertext_b64, key_hint, metadata_public, updated_by_user_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, connector_id, secret_kind) DO UPDATE SET
                key_version = EXCLUDED.key_version,
                nonce_b64 = EXCLUDED.nonce_b64,
                ciphertext_b64 = EXCLUDED.ciphertext_b64,
                key_hint = EXCLUDED.key_hint,
                metadata_public = EXCLUDED.metadata_public,
                updated_by_user_id = EXCLUDED.updated_by_user_id,
                updated_at = now()
            RETURNING connector_id, secret_kind, key_hint, metadata_public, updated_at
            """,
            (
                tenant_id,
                connector_id,
                kind,
                enc.key_version,
                enc.nonce_b64,
                enc.ciphertext_b64,
                enc.key_hint,
                Jsonb(metadata_public),
                user_id,
            ),
        )
        row = await cur.fetchone()
    if row is None:
        raise RuntimeError("Failed to persist encrypted tenant secret.")
    return PublicSecretMetadata(
        connector_id=str(row["connector_id"]),
        secret_kind=row["secret_kind"],
        key_hint=str(row["key_hint"]),
        metadata_public=dict(row["metadata_public"] or {}),
        updated_at=row["updated_at"],
    )


async def update_tenant_secret_metadata(
    conn: RuntimeConnection,
    *,
    tenant_id: UUID,
    connector_id: str,
    kind: SecretKind,
    metadata_public: dict[str, Any],
    user_id: UUID | None,
) -> PublicSecretMetadata | None:
    """Update non-secret metadata without rotating the stored encrypted credential."""
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            UPDATE gba.tenant_connector_secrets
            SET metadata_public = %s,
                updated_by_user_id = %s,
                updated_at = now()
            WHERE tenant_id = %s AND connector_id = %s AND secret_kind = %s
            RETURNING connector_id, secret_kind, key_hint, metadata_public, updated_at
            """,
            (Jsonb(metadata_public), user_id, tenant_id, connector_id, kind),
        )
        row = await cur.fetchone()
    if row is None:
        return None
    return PublicSecretMetadata(
        connector_id=str(row["connector_id"]),
        secret_kind=row["secret_kind"],
        key_hint=str(row["key_hint"]),
        metadata_public=dict(row["metadata_public"] or {}),
        updated_at=row["updated_at"],
    )


async def get_tenant_secret_public(
    conn: RuntimeConnection,
    *,
    tenant_id: UUID,
    connector_id: str,
    kind: SecretKind,
) -> PublicSecretMetadata | None:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT connector_id, secret_kind, key_hint, metadata_public, updated_at
            FROM gba.tenant_connector_secrets
            WHERE tenant_id = %s AND connector_id = %s AND secret_kind = %s
            """,
            (tenant_id, connector_id, kind),
        )
        row = await cur.fetchone()
    if row is None:
        return None
    return PublicSecretMetadata(
        connector_id=str(row["connector_id"]),
        secret_kind=row["secret_kind"],
        key_hint=str(row["key_hint"]),
        metadata_public=dict(row["metadata_public"] or {}),
        updated_at=row["updated_at"],
    )


async def get_tenant_secret_decrypted(
    conn: RuntimeConnection,
    *,
    tenant_id: UUID,
    connector_id: str,
    kind: SecretKind,
    environment: str,
) -> tuple[str, dict[str, Any]] | None:
    """Load and decrypt a secret inside a short TX so callers can use it outside the TX."""
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT key_version, nonce_b64, ciphertext_b64, metadata_public
            FROM gba.tenant_connector_secrets
            WHERE tenant_id = %s AND connector_id = %s AND secret_kind = %s
            """,
            (tenant_id, connector_id, kind),
        )
        row = await cur.fetchone()
    if row is None:
        return None
    plaintext = decrypt_tenant_secret(
        nonce_b64=str(row["nonce_b64"]),
        ciphertext_b64=str(row["ciphertext_b64"]),
        tenant_id=tenant_id,
        connector_id=connector_id,
        kind=kind,
        key_version=str(row["key_version"]),
        environment=environment,
    )
    return plaintext, dict(row["metadata_public"] or {})


async def delete_tenant_secret(
    conn: RuntimeConnection,
    *,
    tenant_id: UUID,
    connector_id: str,
    kind: SecretKind | None = None,
) -> bool:
    if kind is None:
        cur = await conn.execute(
            """
            DELETE FROM gba.tenant_connector_secrets
            WHERE tenant_id = %s AND connector_id = %s
            """,
            (tenant_id, connector_id),
        )
    else:
        cur = await conn.execute(
            """
            DELETE FROM gba.tenant_connector_secrets
            WHERE tenant_id = %s AND connector_id = %s AND secret_kind = %s
            """,
            (tenant_id, connector_id, kind),
        )
    return cur.rowcount > 0


async def store_oauth_tokens_in_vault(
    conn: RuntimeConnection,
    *,
    tenant_id: UUID,
    connector_id: str,
    token_data: dict[str, Any],
    user_id: UUID | None,
    environment: str,
) -> PublicSecretMetadata | None:
    """Persist OAuth2 access/refresh tokens encrypted at rest if present in token response."""
    access_token = str(token_data.get("access_token") or "").strip()
    refresh_token = str(token_data.get("refresh_token") or "").strip()
    if not access_token and not refresh_token:
        return None
    secret_blob = json.dumps(
        {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": str(token_data.get("token_type") or "bearer"),
            "expires_in": token_data.get("expires_in"),
        },
        separators=(",", ":"),
    )
    meta = {
        "has_refresh_token": bool(refresh_token),
        "scope": str(token_data.get("scope") or "default")[:240],
        "token_type": str(token_data.get("token_type") or "bearer")[:40],
    }
    return await upsert_tenant_secret(
        conn,
        tenant_id=tenant_id,
        connector_id=connector_id,
        kind="oauth_tokens",
        plaintext=secret_blob,
        metadata_public=meta,
        user_id=user_id,
        environment=environment,
        hint_source=access_token or refresh_token,
    )
