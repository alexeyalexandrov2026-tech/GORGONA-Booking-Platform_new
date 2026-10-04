"""Append-only profile revisions, authorized and committed by the caller's transaction."""

import hashlib
import json
from uuid import UUID

from psycopg.types.json import Jsonb

from gorgona_booking.booking import idempotency
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.business.contracts import BusinessProfile, ProfileInput
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError


def profile_request_hash(body: ProfileInput) -> str:
    value = body.model_dump(mode="json")
    value["industry_ids"] = sorted(body.industry_ids)
    value["business_formats"] = sorted(body.business_formats)
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


async def load_profile(conn: RuntimeConnection, business_id: UUID) -> BusinessProfile | None:
    row = await (
        await conn.execute(
            "select revision, catalog_version, custom_activity_name, created_at "
            "from gba.business_profile_versions where tenant_id = %s "
            "order by revision desc limit 1",
            (business_id,),
        )
    ).fetchone()
    if row is None:
        return None
    revision = int(row[0])
    industries = await (
        await conn.execute(
            "select industry_id from gba.business_profile_industries "
            "where tenant_id = %s and revision = %s order by industry_id",
            (business_id, revision),
        )
    ).fetchall()
    formats = await (
        await conn.execute(
            "select format from gba.business_profile_formats "
            "where tenant_id = %s and revision = %s order by format",
            (business_id, revision),
        )
    ).fetchall()
    return BusinessProfile(
        business_id=business_id,
        revision=revision,
        catalog_version=row[1],
        custom_activity_name=row[2],
        created_at=row[3],
        industry_ids=tuple(r[0] for r in industries),
        business_formats=tuple(r[0] for r in formats),
    )


async def save_profile(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    user_id: UUID,
    actor: str,
    key: str,
    body: ProfileInput,
) -> BusinessProfile:
    """Caller holds the business-profile advisory lock before the membership lock.

    Even after the idempotency retention window, an old expected revision cannot
    create another revision. A failure rolls back the claim and all profile rows.
    """
    scope = IdempotencyScope(business_id, actor, "business.profile.save", key)
    request_hash = profile_request_hash(body)
    previous = await idempotency.claim(conn, scope, request_hash)
    if previous is not None:
        if previous.request_hash != request_hash:
            raise IdempotencyKeyReusedError("This key was already used with a different profile")
        return BusinessProfile.model_validate(previous.body)

    current = await load_profile(conn, business_id)
    revision = current.revision if current else 0
    if revision != body.expected_revision:
        raise ConflictError(
            "The business profile changed. Reload it before saving.", revision=revision
        )
    revision += 1
    await conn.execute(
        "insert into gba.business_profile_versions "
        "(tenant_id, revision, catalog_version, custom_activity_name, created_by) "
        "values (%s, %s, %s, %s, %s)",
        (business_id, revision, body.catalog_version, body.custom_activity_name, user_id),
    )
    for industry_id in sorted(body.industry_ids):
        await conn.execute(
            "insert into gba.business_profile_industries (tenant_id, revision, industry_id) "
            "values (%s, %s, %s)",
            (business_id, revision, industry_id),
        )
    for business_format in sorted(body.business_formats):
        await conn.execute(
            "insert into gba.business_profile_formats (tenant_id, revision, format) "
            "values (%s, %s, %s)",
            (business_id, revision, business_format),
        )
    result = await load_profile(conn, business_id)
    if result is None:
        raise RuntimeError("Profile insert did not produce a version")
    await conn.execute(
        "insert into gba.audit_events "
        "(tenant_id, actor, action, target_type, target_id, details, request_id) "
        "values (%s, %s, 'business_profile.created', 'business_profile', %s, %s, "
        "nullif(pg_catalog.current_setting('gba.request_id', true), ''))",
        (
            business_id,
            actor,
            str(revision),
            Jsonb(
                {
                    "revision": revision,
                    "catalog_version": body.catalog_version,
                    "industry_ids": sorted(body.industry_ids),
                    "business_formats": sorted(body.business_formats),
                    "has_custom_activity_name": body.custom_activity_name is not None,
                }
            ),
        ),
    )
    await idempotency.complete(conn, scope, 200, result.model_dump(mode="json"))
    return result
