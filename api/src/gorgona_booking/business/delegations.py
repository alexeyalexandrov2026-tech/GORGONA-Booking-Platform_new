"""Issue, accept, decline and revoke cross-company delegation grants (ADR-0017).

The owner business states the terms; the servicing business accepts them and names its
own delegates. Each command runs in the acting company's context, locks the grant row,
checks the expected revision, writes the acting company's audit event and stores an
idempotent receipt in the same transaction.
"""

import hashlib
import json
from typing import Any, Literal
from uuid import UUID

from psycopg.errors import ForeignKeyViolation, UniqueViolation
from psycopg.types.json import Jsonb

from gorgona_booking.booking import idempotency
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.business.delegation_contracts import (
    DelegateSelection,
    DelegateView,
    DelegationDecision,
    DelegationIssue,
    DelegationList,
    DelegationView,
)
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, DomainError, InvalidReferenceError, NotFoundError

# Longest term an owner may grant at once; renewal is a new, reviewed grant.
MAX_TERM_DAYS = 366

Action = Literal["accept", "decline", "revoke", "delegates"]

_COLUMNS = (
    "g.id, g.owner_tenant_id, g.owner_display_name, g.servicer_tenant_id, "
    "g.servicer_display_name, g.permissions, g.location_id, g.expires_at, g.status, "
    "g.status in ('pending', 'active') and g.expires_at <= pg_catalog.statement_timestamp(), "
    "g.revision, g.revoked_by_side, g.created_at"
)
_ISSUE_FIELDS = {
    "delegation_grants_servicer_tenant_id_fkey": "servicer_business_id",
    "delegation_grants_location_fk": "location_id",
}


class DelegationStateError(DomainError):
    code = "DELEGATION_STATE_INVALID"


def _hash(command: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(command, sort_keys=True).encode()).hexdigest()


async def _delegates(conn: RuntimeConnection, grant_ids: list[UUID]) -> dict[UUID, list[Any]]:
    rows = await (
        await conn.execute(
            "select grant_id, user_id, display_name, added_at from gba.delegation_grant_members "
            "where grant_id = any(%s) and removed_at is null order by display_name, user_id",
            (grant_ids,),
        )
    ).fetchall()
    found: dict[UUID, list[Any]] = {}
    for row in rows:
        found.setdefault(row[0], []).append(row[1:])
    return found


def _view(row: tuple[Any, ...], delegates: list[Any]) -> DelegationView:
    return DelegationView(
        grant_id=row[0],
        owner_business_id=row[1],
        owner_name=row[2],
        servicer_business_id=row[3],
        servicer_name=row[4],
        permissions=tuple(sorted(row[5])),
        location_id=row[6],
        expires_at=row[7],
        status=row[8],
        expired=row[9],
        revision=row[10],
        revoked_by_side=row[11],
        delegates=tuple(
            DelegateView(user_id=d[0], display_name=d[1], added_at=d[2]) for d in delegates
        ),
        created_at=row[12],
    )


async def load_delegation(
    conn: RuntimeConnection, business_id: UUID, grant_id: UUID
) -> DelegationView | None:
    """A grant where `business_id` is a party; delegate visibility is not party access."""
    row = await (
        await conn.execute(
            f"select {_COLUMNS} from gba.delegation_grants g "  # noqa: S608 - fixed columns
            "where g.id = %s and (g.owner_tenant_id = %s or g.servicer_tenant_id = %s)",
            (grant_id, business_id, business_id),
        )
    ).fetchone()
    if row is None:
        return None
    return _view(row, (await _delegates(conn, [grant_id])).get(grant_id, []))


async def list_delegations(
    conn: RuntimeConnection, business_id: UUID, *, after: UUID | None, limit: int
) -> DelegationList:
    rows = await (
        await conn.execute(
            f"select {_COLUMNS} from gba.delegation_grants g "  # noqa: S608 - fixed columns
            "where (g.owner_tenant_id = %s or g.servicer_tenant_id = %s) "
            "and (%s::uuid is null or g.id > %s) order by g.id limit %s",
            (business_id, business_id, after, after, limit + 1),
        )
    ).fetchall()
    page = rows[:limit]
    delegates = await _delegates(conn, [row[0] for row in page])
    items = tuple(_view(row, delegates.get(row[0], [])) for row in page)
    return DelegationList(
        business_id=business_id,
        items=items,
        next_cursor=items[-1].grant_id if len(rows) > limit else None,
    )


async def _audit(
    conn: RuntimeConnection,
    business_id: UUID,
    actor: str,
    action: str,
    grant_id: UUID,
    **details: object,
) -> None:
    await conn.execute(
        "insert into gba.audit_events "
        "(tenant_id, actor, action, target_type, target_id, details, request_id) "
        "values (%s, %s, %s, 'delegation_grant', %s, %s, "
        "nullif(pg_catalog.current_setting('gba.request_id', true), ''))",
        (business_id, actor, f"delegation.{action}", str(grant_id), Jsonb(details)),
    )


async def issue_delegation(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    grant_id: UUID,
    user_id: UUID,
    actor: str,
    key: str,
    body: DelegationIssue,
) -> DelegationView:
    """The owner offers limited access; it stays pending until the servicer accepts."""
    scope = IdempotencyScope(business_id, actor, "business.delegation.issue", key)
    fingerprint = _hash({"grant_id": str(grant_id), **body.model_dump(mode="json")})
    previous = await idempotency.claim(conn, scope, fingerprint)
    if previous is not None:
        if previous.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("This key was already used with another command")
        return DelegationView.model_validate(previous.body)
    if body.servicer_business_id == business_id:
        raise DelegationStateError("A business cannot delegate access to itself")
    window = await (
        await conn.execute(
            "select %s > pg_catalog.statement_timestamp() "
            "and %s <= pg_catalog.statement_timestamp() + make_interval(days => %s)",
            (body.expires_at, body.expires_at, MAX_TERM_DAYS),
        )
    ).fetchone()
    if window is None or not window[0]:
        raise DelegationStateError(
            f"Choose an expiry in the future and within {MAX_TERM_DAYS} days"
        )
    owner = await (
        await conn.execute("select display_name from gba.tenants where id = %s", (business_id,))
    ).fetchone()
    if owner is None:
        raise RuntimeError("Authorized business is not visible")
    try:
        async with conn.transaction():
            await conn.execute(
                "insert into gba.delegation_grants (owner_tenant_id, id, servicer_tenant_id, "
                "owner_display_name, permissions, location_id, expires_at, created_by) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    business_id,
                    grant_id,
                    body.servicer_business_id,
                    owner[0],
                    list(body.permissions),
                    body.location_id,
                    body.expires_at,
                    user_id,
                ),
            )
    except UniqueViolation as exc:
        if exc.diag.constraint_name == "delegation_grants_one_open":
            raise ConflictError(
                "This business already has an open delegation. Revoke it before issuing a new one."
            ) from exc
        raise ConflictError("This delegation already exists") from exc
    except ForeignKeyViolation as exc:
        field = _ISSUE_FIELDS.get(exc.diag.constraint_name or "")
        if field is None:
            raise
        raise InvalidReferenceError("Unknown business or location", field=field) from exc
    result = await load_delegation(conn, business_id, grant_id)
    if result is None:
        raise RuntimeError("Delegation insert did not produce a grant")
    await _audit(
        conn,
        business_id,
        actor,
        "issued",
        grant_id,
        servicer_business_id=str(body.servicer_business_id),
        permissions=list(body.permissions),
        location_id=None if body.location_id is None else str(body.location_id),
        expires_at=body.expires_at.isoformat(),
        revision=result.revision,
    )
    await idempotency.complete(conn, scope, 200, result.model_dump(mode="json"))
    return result


async def _named_delegates(
    conn: RuntimeConnection, business_id: UUID, user_ids: tuple[UUID, ...]
) -> dict[UUID, str]:
    rows = await (
        await conn.execute(
            "select m.user_id, u.display_name from gba.memberships m "
            "join gba.users u on u.id = m.user_id "
            "where m.tenant_id = %s and m.user_id = any(%s) "
            "and m.status = 'active' and m.location_id is null",
            (business_id, list(user_ids)),
        )
    ).fetchall()
    found = {row[0]: row[1] for row in rows}
    if set(found) != set(user_ids):
        raise InvalidReferenceError(
            "Delegates must be active company-wide members of your business",
            field="delegate_user_ids",
        )
    return found


async def change_delegation(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    grant_id: UUID,
    action: Action,
    user_id: UUID,
    actor: str,
    key: str,
    body: DelegationDecision,
) -> DelegationView:
    """Apply one party's decision. Caller holds the acting company's delegation lock."""
    scope = IdempotencyScope(business_id, actor, f"business.delegation.{action}", key)
    fingerprint = _hash(
        {"grant_id": str(grant_id), "action": action, **body.model_dump(mode="json")}
    )
    previous = await idempotency.claim(conn, scope, fingerprint)
    if previous is not None:
        if previous.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("This key was already used with another command")
        return DelegationView.model_validate(previous.body)

    row = await (
        await conn.execute(
            "select g.owner_tenant_id, g.status, g.revision, "
            "g.expires_at <= pg_catalog.statement_timestamp() "
            "from gba.delegation_grants g "
            "where g.id = %s and (g.owner_tenant_id = %s or g.servicer_tenant_id = %s) "
            "for update",
            (grant_id, business_id, business_id),
        )
    ).fetchone()
    if row is None:
        raise NotFoundError("Delegation not found")
    owner_id, status, revision, expired = row
    side = "owner" if owner_id == business_id else "servicer"
    if body.expected_revision != revision:
        raise ConflictError(
            "This delegation changed. Reload it before deciding.", revision=revision
        )
    allowed = {
        "accept": side == "servicer" and status == "pending" and not expired,
        "decline": side == "servicer" and status == "pending",
        "revoke": status == "active" or (status == "pending" and side == "owner"),
        "delegates": side == "servicer" and status == "active" and not expired,
    }[action]
    if not allowed:
        raise DelegationStateError(
            "This delegation cannot be changed this way by your business in its current state"
        )

    details: dict[str, object] = {"side": side, "revision": revision + 1}
    if action == "accept":
        if not isinstance(body, DelegateSelection):
            raise TypeError("Acceptance names delegates")
        names = await _named_delegates(conn, business_id, body.delegate_user_ids)
        servicer = await (
            await conn.execute("select display_name from gba.tenants where id = %s", (business_id,))
        ).fetchone()
        await conn.execute(
            "update gba.delegation_grants set status = 'active', revision = revision + 1, "
            "servicer_display_name = %s, decided_by = %s, decided_at = now() "
            "where owner_tenant_id = %s and id = %s",
            (servicer[0] if servicer else None, user_id, owner_id, grant_id),
        )
        await _add_delegates(conn, owner_id, grant_id, business_id, user_id, names)
        details["delegate_user_ids"] = [str(item) for item in body.delegate_user_ids]
    elif action == "decline":
        await conn.execute(
            "update gba.delegation_grants set status = 'declined', revision = revision + 1, "
            "decided_by = %s, decided_at = now() where owner_tenant_id = %s and id = %s",
            (user_id, owner_id, grant_id),
        )
    elif action == "revoke":
        await conn.execute(
            "update gba.delegation_grants set status = 'revoked', revision = revision + 1, "
            "revoked_by = %s, revoked_at = now(), revoked_by_side = %s "
            "where owner_tenant_id = %s and id = %s",
            (user_id, side, owner_id, grant_id),
        )
    else:
        if not isinstance(body, DelegateSelection):
            raise TypeError("A delegate change names delegates")
        names = await _named_delegates(conn, business_id, body.delegate_user_ids)
        current = {
            item[0]
            for item in await (
                await conn.execute(
                    "select user_id from gba.delegation_grant_members "
                    "where owner_tenant_id = %s and grant_id = %s and removed_at is null "
                    "for update",
                    (owner_id, grant_id),
                )
            ).fetchall()
        }
        removed = sorted(current - set(names))
        await conn.execute(
            "update gba.delegation_grant_members set removed_by = %s, removed_at = now() "
            "where owner_tenant_id = %s and grant_id = %s and removed_at is null "
            "and user_id = any(%s)",
            (user_id, owner_id, grant_id, removed),
        )
        await _add_delegates(
            conn,
            owner_id,
            grant_id,
            business_id,
            user_id,
            {item: name for item, name in names.items() if item not in current},
        )
        await conn.execute(
            "update gba.delegation_grants set revision = revision + 1 "
            "where owner_tenant_id = %s and id = %s",
            (owner_id, grant_id),
        )
        details["delegate_user_ids"] = [str(item) for item in body.delegate_user_ids]
        details["removed_user_ids"] = [str(item) for item in removed]
    result = await load_delegation(conn, business_id, grant_id)
    if result is None:
        raise RuntimeError("Delegation disappeared during a decision")
    await _audit(conn, business_id, actor, _AUDIT_ACTIONS[action], grant_id, **details)
    await idempotency.complete(conn, scope, 200, result.model_dump(mode="json"))
    return result


_AUDIT_ACTIONS: dict[Action, str] = {
    "accept": "accepted",
    "decline": "declined",
    "revoke": "revoked",
    "delegates": "delegates_changed",
}


async def _add_delegates(
    conn: RuntimeConnection,
    owner_id: UUID,
    grant_id: UUID,
    servicer_id: UUID,
    user_id: UUID,
    names: dict[UUID, str],
) -> None:
    for delegate_id, name in sorted(names.items()):
        await conn.execute(
            "insert into gba.delegation_grant_members (owner_tenant_id, grant_id, "
            "servicer_tenant_id, user_id, display_name, added_by) "
            "values (%s, %s, %s, %s, %s, %s)",
            (owner_id, grant_id, servicer_id, delegate_id, name, user_id),
        )
