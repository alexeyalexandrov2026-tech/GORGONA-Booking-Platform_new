"""An operator invites; only the independent participant's owner may consent."""

import hashlib
import json
from uuid import UUID

from psycopg.errors import ForeignKeyViolation, UniqueViolation

from gorgona_booking.booking import idempotency
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.business.group_contracts import (
    ConsentInput,
    InvitationInput,
    InvitationList,
    InvitationView,
)
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, InvalidReferenceError, NotFoundError


async def lock_invitation(conn: RuntimeConnection, invitation_id: UUID, *, shared: bool) -> None:
    function = "pg_advisory_xact_lock_shared" if shared else "pg_advisory_xact_lock"
    await conn.execute(
        f"select pg_catalog.{function}(pg_catalog.hashtextextended(%s, 0))",
        (f"gba:group-invitation:{invitation_id}",),
    )


async def list_invitations(
    conn: RuntimeConnection,
    business_id: UUID,
    *,
    group_id: UUID | None,
    incoming: bool,
    after: UUID | None,
    limit: int,
    invitation_id: UUID | None = None,
) -> InvitationList:
    rows = await (
        await conn.execute(
            "select i.id, i.tenant_id, i.participant_business_id, i.group_id, i.state, i.revision, "
            "i.created_at, g.name, c.state, coalesce(c.revision, 0) "
            "from gba.company_group_invitations i join lateral (select name "
            "from gba.company_group_versions where tenant_id = i.tenant_id "
            "and group_id = i.group_id "
            "order by revision desc limit 1) g on true "
            "left join lateral (select state, revision from gba.company_group_consents "
            "where tenant_id = i.participant_business_id and invitation_id = i.id "
            "order by revision desc limit 1) c on true "
            "where ((%s and i.participant_business_id = %s) or (not %s and i.tenant_id = %s)) "
            "and (%s::uuid is null or i.group_id = %s) and (%s::uuid is null or i.id = %s) "
            "and (%s::uuid is null or i.id > %s) order by i.id limit %s",
            (
                incoming,
                business_id,
                incoming,
                business_id,
                group_id,
                group_id,
                invitation_id,
                invitation_id,
                after,
                after,
                limit + 1,
            ),
        )
    ).fetchall()
    items = tuple(
        InvitationView(
            business_id=business_id,
            invitation_id=r[0],
            operator_business_id=r[1],
            participant_business_id=r[2],
            group_id=r[3],
            state=r[4],
            revision=r[5],
            created_at=r[6],
            group_name=r[7],
            consent_state=r[8],
            consent_revision=r[9],
        )
        for r in rows[:limit]
    )
    return InvitationList(
        business_id=business_id,
        items=items,
        next_cursor=items[-1].invitation_id if len(rows) > limit else None,
    )


async def load_invitation(
    conn: RuntimeConnection,
    business_id: UUID,
    invitation_id: UUID,
    *,
    incoming: bool,
    group_id: UUID | None = None,
) -> InvitationView:
    page = await list_invitations(
        conn,
        business_id,
        group_id=group_id,
        incoming=incoming,
        after=None,
        limit=1,
        invitation_id=invitation_id,
    )
    if not page.items:
        raise NotFoundError("Group invitation not found")
    return page.items[0]


async def receipt(
    conn: RuntimeConnection,
    scope: IdempotencyScope,
    invitation_id: UUID,
    body: InvitationInput | ConsentInput,
    *,
    group_id: UUID | None = None,
) -> InvitationView | None:
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "invitation_id": str(invitation_id),
                "group_id": str(group_id) if group_id else None,
                **body.model_dump(mode="json"),
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    previous = await idempotency.claim(conn, scope, fingerprint)
    if previous is not None:
        if previous.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("This key belongs to another group command")
        return InvitationView.model_validate(previous.body)
    return None


async def invite(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    group_id: UUID,
    invitation_id: UUID,
    user_id: UUID,
    actor: str,
    key: str,
    body: InvitationInput,
) -> InvitationView:
    # The path's group must be included in the command fingerprint too.
    scope = IdempotencyScope(business_id, actor, "group.invite", key)
    previous = await receipt(conn, scope, invitation_id, body, group_id=group_id)
    if previous is not None:
        return previous
    if body.participant_business_id == business_id:
        raise InvalidReferenceError("Invite an independent business")
    try:
        async with conn.transaction():
            await conn.execute(
                "insert into gba.company_group_invitations "
                "(tenant_id, id, group_id, participant_business_id, created_by) "
                "values (%s, %s, %s, %s, %s)",
                (business_id, invitation_id, group_id, body.participant_business_id, user_id),
            )
    except ForeignKeyViolation:
        raise InvalidReferenceError("Choose an existing group and participant business") from None
    except UniqueViolation:
        raise ConflictError(
            "This invitation or an active invitation to this business already exists"
        ) from None
    result = await load_invitation(
        conn, business_id, invitation_id, incoming=False, group_id=group_id
    )
    await idempotency.complete(conn, scope, 200, result.model_dump(mode="json"))
    return result


async def consent(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    invitation_id: UUID,
    user_id: UUID,
    actor: str,
    key: str,
    body: ConsentInput,
) -> InvitationView:
    scope = IdempotencyScope(business_id, actor, "group.consent", key)
    previous = await receipt(conn, scope, invitation_id, body)
    if previous is not None:
        return previous
    await lock_invitation(conn, invitation_id, shared=False)
    current = await load_invitation(conn, business_id, invitation_id, incoming=True)
    if current.consent_revision != body.expected_revision:
        raise ConflictError(
            "Consent changed. Reload before confirming.", revision=current.consent_revision
        )
    if current.consent_state == "withdrawn":
        raise ConflictError("Withdrawn consent is final. A new invitation is required")
    if body.state != ("accepted" if current.consent_revision == 0 else "withdrawn"):
        raise ConflictError("Accept an invitation once; then withdraw if necessary")
    if body.state == "accepted" and current.state != "active":
        raise ConflictError("The operator withdrew this invitation")
    await conn.execute(
        "insert into gba.company_group_consents "
        "(tenant_id, operator_business_id, invitation_id, revision, state, created_by) "
        "values (%s, %s, %s, %s, %s, %s)",
        (
            business_id,
            current.operator_business_id,
            invitation_id,
            current.consent_revision + 1,
            body.state,
            user_id,
        ),
    )
    result = await load_invitation(conn, business_id, invitation_id, incoming=True)
    await idempotency.complete(conn, scope, 200, result.model_dump(mode="json"))
    return result


async def withdraw_invitation(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    group_id: UUID,
    invitation_id: UUID,
    actor: str,
    key: str,
    body: ConsentInput,
) -> InvitationView:
    if body.state != "withdrawn":
        raise InvalidReferenceError(
            "An operator can withdraw an invitation; only its recipient may consent"
        )
    scope = IdempotencyScope(business_id, actor, "group.withdraw", key)
    previous = await receipt(conn, scope, invitation_id, body, group_id=group_id)
    if previous is not None:
        return previous
    await lock_invitation(conn, invitation_id, shared=False)
    current = await load_invitation(
        conn, business_id, invitation_id, incoming=False, group_id=group_id
    )
    if current.state != "active" or current.revision != body.expected_revision:
        raise ConflictError(
            "Invitation changed. Reload it before withdrawing", revision=current.revision
        )
    await conn.execute(
        "update gba.company_group_invitations set state = 'withdrawn', revision = 2 "
        "where tenant_id = %s and group_id = %s and id = %s",
        (business_id, group_id, invitation_id),
    )
    result = await load_invitation(
        conn, business_id, invitation_id, incoming=False, group_id=group_id
    )
    await idempotency.complete(conn, scope, 200, result.model_dump(mode="json"))
    return result
