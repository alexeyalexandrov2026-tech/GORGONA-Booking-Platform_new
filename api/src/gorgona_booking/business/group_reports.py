"""Live operational counts; no data copy, payment, ledger or revenue assertion."""

from datetime import datetime, timedelta
from uuid import UUID

from gorgona_booking.auth.principal import Principal
from gorgona_booking.business.company_groups import load_group
from gorgona_booking.business.group_contracts import (
    BookingReportRow,
    GroupBookingReport,
    ReportSource,
)
from gorgona_booking.business.group_membership import load_invitation, lock_invitation
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import DatabaseUnavailableError, InvalidReferenceError, NotFoundError
from gorgona_booking.tenancy.authorization import (
    clear_group_report_context,
    group_report_delegation,
)


async def booking_report(
    conn: RuntimeConnection,
    principal: Principal,
    operator_id: UUID,
    group_id: UUID,
    *,
    from_at: datetime,
    until_at: datetime,
    after: UUID | None,
    limit: int,
) -> GroupBookingReport:
    if until_at <= from_at or until_at - from_at > timedelta(days=366):
        raise InvalidReferenceError("Choose a positive report period of at most 366 days")
    row = await (await conn.execute("select current_setting('transaction_isolation')")).fetchone()
    if row != ("read committed",):
        raise DatabaseUnavailableError("Group reports require READ COMMITTED")
    if await load_group(conn, operator_id, group_id) is None:
        raise NotFoundError("Group not found")
    # Page the invitation identities, not only currently permitted data. No hidden joins
    # broaden membership; latest invitation and consent are re-read after each shared lock.
    invitations = await (
        await conn.execute(
            "select id from gba.company_group_invitations where tenant_id = %s and group_id = %s "
            "and state = 'active' and (%s::uuid is null or id > %s) order by id limit %s",
            (operator_id, group_id, after, after, limit + 1),
        )
    ).fetchall()
    result: list[BookingReportRow] = []
    sources: list[ReportSource] = []
    excluded: list[UUID] = []
    for (invitation_id,) in invitations[:limit]:
        await lock_invitation(conn, invitation_id, shared=True)
        invitation = await load_invitation(
            conn, operator_id, invitation_id, incoming=False, group_id=group_id
        )
        if invitation.state != "active" or invitation.consent_state != "accepted":
            continue
        try:
            access = await group_report_delegation(
                conn, principal, invitation.participant_business_id, operator_id
            )
            if access is None:
                excluded.append(invitation.participant_business_id)
                continue
            if access.delegation is None:
                raise RuntimeError("Group reporting requires verified delegation")
            sources.append(
                ReportSource(
                    owner_business_id=invitation.participant_business_id,
                    grant_id=access.delegation.grant_id,
                    grant_revision=access.delegation.revision,
                    location_id=access.location_id,
                )
            )
            counts = await (
                await conn.execute(
                    "select location_id, status, count(*) from gba.bookings "
                    "where tenant_id = %s and starts_at >= %s and starts_at < %s "
                    "group by location_id, status order by location_id, status",
                    (invitation.participant_business_id, from_at, until_at),
                )
            ).fetchall()
            result.extend(
                BookingReportRow(
                    owner_business_id=invitation.participant_business_id,
                    location_id=r[0],
                    status=r[1],
                    booking_count=r[2],
                )
                for r in counts
            )
        finally:
            await clear_group_report_context(conn, principal, operator_id)
    return GroupBookingReport(
        business_id=operator_id,
        group_id=group_id,
        from_at=from_at,
        until_at=until_at,
        items=tuple(result),
        sources=tuple(sources),
        excluded_business_ids=tuple(excluded),
        next_cursor=invitations[limit - 1][0] if len(invitations) > limit else None,
    )
