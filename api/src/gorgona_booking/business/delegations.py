"""Owner grants, serving-business designations and delegated-access lookups (ADR-0016).

Every function runs inside an authorized transaction and filters explicitly by the
business it serves; row-level security remains the boundary underneath.
"""

import hashlib
import json
from typing import Any
from uuid import UUID

from psycopg.errors import ForeignKeyViolation, UniqueViolation
from psycopg.types.json import Jsonb

from gorgona_booking.booking import idempotency
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.business.delegation_contracts import (
    DelegatedAccessView,
    DelegationGrantInput,
    DelegationGrantList,
    DelegationGrantView,
    DelegationRevokeInput,
    GrantDelegateView,
    IncomingDelegateView,
    IncomingDelegationList,
    IncomingDelegationView,
)
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import (
    ConflictError,
    DomainError,
    InvalidReferenceError,
    NotFoundError,
)

_UNUSABLE_SERVING_BUSINESS = "This serving business cannot receive a delegation"

_EFFECTIVE_STATE = (
    "case when v.state = 'revoked' then 'revoked' "
    "when now() < v.valid_from then 'scheduled' "
    "when now() >= v.valid_until then 'expired' else 'active' end"
)
_TERMS = (
    f"v.revision, v.state, {_EFFECTIVE_STATE}, v.purpose, v.permissions, v.location_id, "
    "v.valid_from, v.valid_until"
)
_CURRENT_VERSION = (
    "join lateral (select * from gba.delegation_grant_versions "
    "where tenant_id = g.tenant_id and grant_id = g.id "
    "order by revision desc limit 1) v on true"
)


def grant_lock_key(owner_id: UUID, grant_id: UUID) -> str:
    """Grant writers hold this exclusively; delegated requests hold it shared."""
    return f"gba:delegation-grant:{owner_id}:{grant_id}"


async def lock_grant(
    conn: RuntimeConnection, owner_id: UUID, grant_id: UUID, *, shared: bool
) -> None:
    function = "pg_advisory_xact_lock_shared" if shared else "pg_advisory_xact_lock"
    await conn.execute(
        f"select pg_catalog.{function}(pg_catalog.hashtextextended(%s, 0))",
        (grant_lock_key(owner_id, grant_id),),
    )


def _fingerprint(command: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(command, sort_keys=True).encode()).hexdigest()


def _terms(row: tuple[Any, ...]) -> dict[str, Any]:
    """Map the `_TERMS` columns at the start of `row`."""
    return {
        "revision": row[0],
        "state": row[1],
        "effective_state": row[2],
        "purpose": row[3],
        "permissions": tuple(row[4]),
        "location_id": row[5],
        "valid_from": row[6],
        "valid_until": row[7],
    }


# --- Owner side -----------------------------------------------------------------------------


async def _owner_delegates(
    conn: RuntimeConnection, owner_id: UUID, grant_ids: list[UUID]
) -> dict[UUID, list[GrantDelegateView]]:
    rows = await (
        await conn.execute(
            "select grant_id, id, user_id, created_at from gba.delegation_designations "
            "where grantor_business_id = %s and grant_id = any(%s) and status = 'active' "
            "order by created_at, id",
            (owner_id, grant_ids),
        )
    ).fetchall()
    delegates: dict[UUID, list[GrantDelegateView]] = {}
    for row in rows:
        delegates.setdefault(row[0], []).append(
            GrantDelegateView(designation_id=row[1], user_id=row[2], designated_at=row[3])
        )
    return delegates


async def load_grant(
    conn: RuntimeConnection, owner_id: UUID, grant_id: UUID, *, revision: int | None = None
) -> DelegationGrantView | None:
    row = await (
        await conn.execute(
            f"select {_TERMS}, v.created_at, g.grantee_business_id, "  # noqa: S608 - constants
            "(select max(revision) from gba.delegation_grant_versions "
            " where tenant_id = g.tenant_id and grant_id = g.id) "
            "from gba.delegation_grants g join gba.delegation_grant_versions v "
            "on v.tenant_id = g.tenant_id and v.grant_id = g.id "
            "where g.tenant_id = %s and g.id = %s "
            "and (%s::integer is null or v.revision = %s) "
            "order by v.revision desc limit 1",
            (owner_id, grant_id, revision, revision),
        )
    ).fetchone()
    if row is None:
        return None
    current_revision = row[10]
    delegates = (
        (await _owner_delegates(conn, owner_id, [grant_id])).get(grant_id, [])
        if row[0] == current_revision
        else []
    )
    return DelegationGrantView(
        business_id=owner_id,
        grant_id=grant_id,
        grantee_business_id=row[9],
        current_revision=current_revision,
        created_at=row[8],
        delegates=tuple(delegates),
        **_terms(row),
    )


async def list_grants(
    conn: RuntimeConnection, owner_id: UUID, *, after: UUID | None, limit: int
) -> DelegationGrantList:
    rows = await (
        await conn.execute(
            f"select {_TERMS}, v.created_at, g.grantee_business_id, g.id "  # noqa: S608
            f"from gba.delegation_grants g {_CURRENT_VERSION} "
            "where g.tenant_id = %s and (%s::uuid is null or g.id > %s) "
            "order by g.id limit %s",
            (owner_id, after, after, limit + 1),
        )
    ).fetchall()
    page = rows[:limit]
    delegates = await _owner_delegates(conn, owner_id, [row[10] for row in page])
    items = tuple(
        DelegationGrantView(
            business_id=owner_id,
            grant_id=row[10],
            grantee_business_id=row[9],
            current_revision=row[0],
            created_at=row[8],
            delegates=tuple(delegates.get(row[10], [])),
            **_terms(row),
        )
        for row in page
    )
    return DelegationGrantList(
        business_id=owner_id,
        items=items,
        next_cursor=items[-1].grant_id if len(rows) > limit else None,
    )


async def _audit(
    conn: RuntimeConnection,
    tenant_id: UUID,
    actor: str,
    action: str,
    grant_id: UUID,
    details: dict[str, Any],
) -> None:
    await conn.execute(
        "insert into gba.audit_events "
        "(tenant_id, actor, action, target_type, target_id, details, request_id) "
        "values (%s, %s, %s, 'delegation_grant', %s, %s, "
        "nullif(pg_catalog.current_setting('gba.request_id', true), ''))",
        (tenant_id, actor, action, str(grant_id), Jsonb(details)),
    )


async def _insert_version(
    conn: RuntimeConnection,
    *,
    owner_id: UUID,
    grant_id: UUID,
    grantee_id: UUID,
    revision: int,
    state: str,
    purpose: str,
    permissions: tuple[str, ...],
    location_id: UUID | None,
    valid_from: object,
    valid_until: object,
    user_id: UUID,
) -> None:
    await conn.execute(
        "insert into gba.delegation_grant_versions (tenant_id, grant_id, grantee_business_id, "
        "revision, state, purpose, permissions, location_id, valid_from, valid_until, "
        "created_by) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            owner_id,
            grant_id,
            grantee_id,
            revision,
            state,
            purpose,
            list(permissions),
            location_id,
            valid_from,
            valid_until,
            user_id,
        ),
    )


async def save_grant(
    conn: RuntimeConnection,
    *,
    owner_id: UUID,
    grant_id: UUID,
    user_id: UUID,
    actor: str,
    key: str,
    body: DelegationGrantInput,
) -> DelegationGrantView:
    """Create a grant or append a revision. The caller holds the business delegation lock
    before the membership share lock; this takes the grant lock exclusively."""
    scope = IdempotencyScope(owner_id, actor, "business.delegation_grant.save", key)
    fingerprint = _fingerprint({"grant_id": str(grant_id), **body.model_dump(mode="json")})
    previous = await idempotency.claim(conn, scope, fingerprint)
    if previous is not None:
        if previous.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("This key was already used with another command")
        return DelegationGrantView.model_validate(previous.body)

    await lock_grant(conn, owner_id, grant_id, shared=False)
    current = await load_grant(conn, owner_id, grant_id)
    revision = current.current_revision if current else 0
    if body.expected_revision != revision:
        raise ConflictError("This delegation changed. Reload it before saving.", revision=revision)
    if current is not None and current.state == "revoked":
        raise ConflictError("A revoked delegation cannot change", revision=revision)
    if current is not None and current.grantee_business_id != body.grantee_business_id:
        raise InvalidReferenceError("The serving business of a delegation cannot change")
    if body.grantee_business_id == owner_id:
        raise InvalidReferenceError("A business cannot delegate to itself")
    ends_in_future = await (
        await conn.execute("select %s::timestamptz > now()", (body.valid_until,))
    ).fetchone()
    if ends_in_future is None or ends_in_future[0] is not True:
        raise DomainError("The delegation must end in the future")
    if body.location_id is not None:
        location = await (
            await conn.execute(
                "select 1 from gba.locations where tenant_id = %s and id = %s",
                (owner_id, body.location_id),
            )
        ).fetchone()
        if location is None:
            raise InvalidReferenceError("Unknown location")
    if current is None:
        try:
            async with conn.transaction():
                await conn.execute(
                    "insert into gba.delegation_grants "
                    "(tenant_id, id, grantee_business_id, created_by) values (%s, %s, %s, %s)",
                    (owner_id, grant_id, body.grantee_business_id, user_id),
                )
        except ForeignKeyViolation as exc:
            if exc.diag.constraint_name != "delegation_grants_grantee_business_id_fkey":
                raise
            # Same answer whether the business is unknown or merely not visible here.
            raise InvalidReferenceError(_UNUSABLE_SERVING_BUSINESS) from None
        except UniqueViolation as exc:
            if exc.diag.constraint_name != "delegation_grants_grantee_grant_key":
                raise
            raise ConflictError("Choose another delegation identifier") from None
    revision += 1
    await _insert_version(
        conn,
        owner_id=owner_id,
        grant_id=grant_id,
        grantee_id=body.grantee_business_id,
        revision=revision,
        state="active",
        purpose=body.purpose,
        permissions=body.permissions,
        location_id=body.location_id,
        valid_from=body.valid_from,
        valid_until=body.valid_until,
        user_id=user_id,
    )
    result = await load_grant(conn, owner_id, grant_id)
    if result is None:
        raise RuntimeError("Delegation insert did not produce a revision")
    await _audit(
        conn,
        owner_id,
        actor,
        "delegation_grant.saved",
        grant_id,
        {
            "revision": revision,
            "grantee_business_id": str(body.grantee_business_id),
            "permissions": list(body.permissions),
            "location_id": str(body.location_id) if body.location_id else None,
            "valid_from": body.valid_from.isoformat(),
            "valid_until": body.valid_until.isoformat(),
        },
    )
    await idempotency.complete(conn, scope, 200, result.model_dump(mode="json"))
    return result


async def revoke_grant(
    conn: RuntimeConnection,
    *,
    owner_id: UUID,
    grant_id: UUID,
    user_id: UUID,
    actor: str,
    key: str,
    body: DelegationRevokeInput,
) -> DelegationGrantView:
    """Append a terminal revoked revision. In-flight delegated requests finish first."""
    scope = IdempotencyScope(owner_id, actor, "business.delegation_grant.revoke", key)
    fingerprint = _fingerprint({"grant_id": str(grant_id), **body.model_dump(mode="json")})
    previous = await idempotency.claim(conn, scope, fingerprint)
    if previous is not None:
        if previous.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("This key was already used with another command")
        return DelegationGrantView.model_validate(previous.body)

    await lock_grant(conn, owner_id, grant_id, shared=False)
    current = await load_grant(conn, owner_id, grant_id)
    if current is None:
        raise NotFoundError("Delegation not found")
    if body.expected_revision != current.current_revision:
        raise ConflictError(
            "This delegation changed. Reload it before revoking.",
            revision=current.current_revision,
        )
    if current.state == "revoked":
        raise ConflictError("This delegation is already revoked", revision=current.revision)
    revision = current.current_revision + 1
    await _insert_version(
        conn,
        owner_id=owner_id,
        grant_id=grant_id,
        grantee_id=current.grantee_business_id,
        revision=revision,
        state="revoked",
        purpose=current.purpose,
        permissions=current.permissions,
        location_id=current.location_id,
        valid_from=current.valid_from,
        valid_until=current.valid_until,
        user_id=user_id,
    )
    result = await load_grant(conn, owner_id, grant_id)
    if result is None:
        raise RuntimeError("Delegation revocation did not produce a revision")
    await _audit(
        conn,
        owner_id,
        actor,
        "delegation_grant.revoked",
        grant_id,
        {"revision": revision, "grantee_business_id": str(current.grantee_business_id)},
    )
    await idempotency.complete(conn, scope, 200, result.model_dump(mode="json"))
    return result


# --- Serving-business side ---------------------------------------------------------------


async def _incoming_delegates(
    conn: RuntimeConnection, serving_id: UUID, grant_ids: list[UUID]
) -> dict[UUID, list[IncomingDelegateView]]:
    rows = await (
        await conn.execute(
            "select d.grant_id, d.id, d.membership_id, d.user_id, u.display_name, d.created_at "
            "from gba.delegation_designations d left join gba.users u on u.id = d.user_id "
            "where d.tenant_id = %s and d.grant_id = any(%s) and d.status = 'active' "
            "order by d.created_at, d.id",
            (serving_id, grant_ids),
        )
    ).fetchall()
    delegates: dict[UUID, list[IncomingDelegateView]] = {}
    for row in rows:
        delegates.setdefault(row[0], []).append(
            IncomingDelegateView(
                designation_id=row[1],
                membership_id=row[2],
                user_id=row[3],
                display_name=row[4],
                designated_at=row[5],
            )
        )
    return delegates


async def _incoming_rows(
    conn: RuntimeConnection,
    serving_id: UUID,
    *,
    grant_id: UUID | None = None,
    after: UUID | None = None,
    limit: int = 1,
) -> list[tuple[Any, ...]]:
    return await (
        await conn.execute(
            f"select {_TERMS}, g.tenant_id, g.id "  # noqa: S608 - constants
            f"from gba.delegation_grants g {_CURRENT_VERSION} "
            "where g.grantee_business_id = %s and (%s::uuid is null or g.id = %s) "
            "and (%s::uuid is null or g.id > %s) order by g.id limit %s",
            (serving_id, grant_id, grant_id, after, after, limit),
        )
    ).fetchall()


def _incoming_view(
    serving_id: UUID, row: tuple[Any, ...], delegates: dict[UUID, list[IncomingDelegateView]]
) -> IncomingDelegationView:
    return IncomingDelegationView(
        business_id=serving_id,
        grant_id=row[9],
        grantor_business_id=row[8],
        delegates=tuple(delegates.get(row[9], [])),
        **_terms(row),
    )


async def list_incoming(
    conn: RuntimeConnection, serving_id: UUID, *, after: UUID | None, limit: int
) -> IncomingDelegationList:
    rows = await _incoming_rows(conn, serving_id, after=after, limit=limit + 1)
    page = rows[:limit]
    delegates = await _incoming_delegates(conn, serving_id, [row[9] for row in page])
    items = tuple(_incoming_view(serving_id, row, delegates) for row in page)
    return IncomingDelegationList(
        business_id=serving_id,
        items=items,
        next_cursor=items[-1].grant_id if len(rows) > limit else None,
    )


async def load_incoming(
    conn: RuntimeConnection, serving_id: UUID, grant_id: UUID
) -> IncomingDelegationView | None:
    rows = await _incoming_rows(conn, serving_id, grant_id=grant_id)
    if not rows:
        return None
    delegates = await _incoming_delegates(conn, serving_id, [grant_id])
    return _incoming_view(serving_id, rows[0], delegates)


async def _designation_command(
    conn: RuntimeConnection,
    *,
    serving_id: UUID,
    grant_id: UUID,
    membership_id: UUID,
    actor: str,
    key: str,
    operation: str,
) -> tuple[IdempotencyScope, IncomingDelegationView | None]:
    scope = IdempotencyScope(serving_id, actor, operation, key)
    fingerprint = _fingerprint({"grant_id": str(grant_id), "membership_id": str(membership_id)})
    previous = await idempotency.claim(conn, scope, fingerprint)
    if previous is None:
        return scope, None
    if previous.request_hash != fingerprint:
        raise IdempotencyKeyReusedError("This key was already used with another command")
    return scope, IncomingDelegationView.model_validate(previous.body)


async def designate(
    conn: RuntimeConnection,
    *,
    serving_id: UUID,
    grant_id: UUID,
    membership_id: UUID,
    user_id: UUID,
    actor: str,
    key: str,
) -> IncomingDelegationView:
    """Let one active member of the serving business use a grant addressed to it."""
    scope, replay = await _designation_command(
        conn,
        serving_id=serving_id,
        grant_id=grant_id,
        membership_id=membership_id,
        actor=actor,
        key=key,
        operation="business.delegation.designate",
    )
    if replay is not None:
        return replay
    grant = await load_incoming(conn, serving_id, grant_id)
    if grant is None:
        raise NotFoundError("Delegation not found")
    if grant.effective_state in ("revoked", "expired"):
        raise ConflictError("This delegation can no longer be used")
    member = await (
        await conn.execute(
            "select user_id, status from gba.memberships where tenant_id = %s and id = %s",
            (serving_id, membership_id),
        )
    ).fetchone()
    if member is None:
        raise NotFoundError("Member not found")
    if member[1] != "active":
        raise ConflictError("Only an active member can be designated")
    if not any(item.membership_id == membership_id for item in grant.delegates):
        try:
            async with conn.transaction():
                await conn.execute(
                    "insert into gba.delegation_designations (tenant_id, grantor_business_id, "
                    "grant_id, membership_id, user_id, created_by) "
                    "values (%s, %s, %s, %s, %s, %s)",
                    (
                        serving_id,
                        grant.grantor_business_id,
                        grant_id,
                        membership_id,
                        member[0],
                        user_id,
                    ),
                )
        except UniqueViolation as exc:
            if exc.diag.constraint_name != "delegation_designations_one_active":
                raise
    result = await load_incoming(conn, serving_id, grant_id)
    if result is None:
        raise RuntimeError("Designated delegation disappeared")
    await idempotency.complete(conn, scope, 200, result.model_dump(mode="json"))
    return result


async def remove_designation(
    conn: RuntimeConnection,
    *,
    serving_id: UUID,
    grant_id: UUID,
    membership_id: UUID,
    user_id: UUID,
    actor: str,
    key: str,
) -> IncomingDelegationView:
    """Stop one member from using a grant; history and audit are kept."""
    scope, replay = await _designation_command(
        conn,
        serving_id=serving_id,
        grant_id=grant_id,
        membership_id=membership_id,
        actor=actor,
        key=key,
        operation="business.delegation.remove",
    )
    if replay is not None:
        return replay
    if await load_incoming(conn, serving_id, grant_id) is None:
        raise NotFoundError("Delegation not found")
    removed = await (
        await conn.execute(
            "update gba.delegation_designations "
            "set status = 'removed', removed_by = %s, removed_at = now() "
            "where tenant_id = %s and grant_id = %s and membership_id = %s and status = 'active' "
            "returning id",
            (user_id, serving_id, grant_id, membership_id),
        )
    ).fetchone()
    if removed is None:
        raise NotFoundError("This member is not designated for the delegation")
    result = await load_incoming(conn, serving_id, grant_id)
    if result is None:
        raise RuntimeError("Delegation disappeared during removal")
    await idempotency.complete(conn, scope, 200, result.model_dump(mode="json"))
    return result


# --- The designated person ---------------------------------------------------------------


async def delegated_access(
    conn: RuntimeConnection, user_id: UUID
) -> tuple[DelegatedAccessView, ...]:
    """Grants the caller can currently use. Runs with user context only, no tenant."""
    rows = await (
        await conn.execute(
            f"select g.tenant_id, d.tenant_id, g.id, {_TERMS} "  # noqa: S608 - constants
            "from gba.delegation_designations d "
            "join gba.memberships m on m.tenant_id = d.tenant_id and m.id = d.membership_id "
            "and m.user_id = d.user_id and m.status = 'active' "
            "join gba.delegation_grants g on g.tenant_id = d.grantor_business_id "
            f"and g.id = d.grant_id {_CURRENT_VERSION} "
            "where d.user_id = %s and d.status = 'active' and v.state = 'active' "
            "and v.valid_from <= now() and now() < v.valid_until "
            # A membership in the owner business takes precedence over any delegation.
            "and not exists (select 1 from gba.memberships own "
            "where own.tenant_id = g.tenant_id and own.user_id = d.user_id "
            "and own.status <> 'revoked') "
            "order by g.tenant_id, (v.location_id is not null), g.id",
            (user_id,),
        )
    ).fetchall()
    return tuple(
        DelegatedAccessView(
            business_id=row[0],
            serving_business_id=row[1],
            grant_id=row[2],
            revision=row[3],
            purpose=row[6],
            permissions=tuple(row[7]),
            location_id=row[8],
            valid_until=row[10],
        )
        for row in rows
    )
