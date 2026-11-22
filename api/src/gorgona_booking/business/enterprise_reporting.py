"""ENTERPRISE-01 Slice 2 (ADR-0041): Consent-based group reporting grants and consolidated
group analytics that strictly preserve Stage 1 ownership boundaries, legal entity attribution,
and currency separation (never summing distinct currencies without explicit FX conversion).
"""

from collections import defaultdict
from typing import Any, Literal
from uuid import UUID

from psycopg import errors
from pydantic import AwareDatetime, Field, field_validator

from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.business import commands
from gorgona_booking.business.contracts import Strict, Versioned
from gorgona_booking.business.enterprise_sso import (
    ANALYTICS_MODULE,
    EnterpriseRevisionConflictError,
    EnterpriseStateError,
    _check_ready,
    _clean_line,
)
from gorgona_booking.business.ledger_contracts import CURRENCY_PATTERN
from gorgona_booking.business.module_gate import module_writes, require_module
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import InvalidReferenceError, NotFoundError

ReportSet = Literal["ledger_summary", "revenue_by_currency", "order_volume", "headcount"]
GrantStatus = Literal["active", "revoked"]


class GroupReportGrantInput(Versioned):
    expected_revision: int = Field(ge=0, le=1_000_000)
    organizer_business_id: UUID
    group_id: UUID
    allowed_report_sets: list[ReportSet] = Field(min_length=1, max_length=4)
    status: GrantStatus = "active"

    @field_validator("allowed_report_sets")
    @classmethod
    def unique_sets(cls, value: list[ReportSet]) -> list[ReportSet]:
        deduped = list(dict.fromkeys(value))
        if not deduped:
            raise ValueError("At least one report set is required")
        return deduped


class GroupReportGrantView(Strict):
    schema_version: Literal[1] = 1
    grant_id: UUID
    owner_business_id: UUID
    organizer_business_id: UUID
    group_id: UUID
    allowed_report_sets: list[ReportSet]
    status: GrantStatus
    revoked_at: AwareDatetime | None
    revision: int
    recorded_by: UUID
    recorded_at: AwareDatetime


class GroupReportGrantList(Strict):
    schema_version: Literal[1] = 1
    items: list[GroupReportGrantView]


class GroupReportSnapshotInput(Versioned):
    organizer_business_id: UUID
    group_id: UUID
    legal_entity_id: UUID
    period_key: str = Field(pattern=r"^[0-9]{4}-[0-9]{2}$")
    currency: str = Field(pattern=CURRENCY_PATTERN)
    report_set: ReportSet
    metric_count: int = Field(default=0, ge=0, le=999_999_999_999)
    metric_amount_minor: int = Field(default=0, ge=-999_999_999_999_999, le=999_999_999_999_999)
    notes: str | None = None

    @field_validator("notes")
    @classmethod
    def valid_notes(cls, value: str | None) -> str | None:
        return None if value is None else _clean_line(value, 500)


class GroupReportSnapshotView(Strict):
    schema_version: Literal[1] = 1
    snapshot_id: UUID
    owner_business_id: UUID
    organizer_business_id: UUID
    group_id: UUID
    legal_entity_id: UUID
    period_key: str
    currency: str
    report_set: ReportSet
    metric_count: int
    metric_amount_minor: int
    notes: str | None
    recorded_by: UUID
    recorded_at: AwareDatetime


class CurrencyTotal(Strict):
    currency: str
    report_set: ReportSet
    total_count: int
    total_amount_minor: int
    contributing_businesses: int


class ConsolidatedGroupReportView(Strict):
    schema_version: Literal[1] = 1
    group_id: UUID
    organizer_business_id: UUID
    period_key: str | None
    entries: list[GroupReportSnapshotView]
    totals_by_currency: list[CurrencyTotal]


def _grant_view(r: tuple[Any, ...]) -> GroupReportGrantView:
    return GroupReportGrantView(
        grant_id=r[0],
        owner_business_id=r[1],
        organizer_business_id=r[2],
        group_id=r[3],
        allowed_report_sets=list(r[4]),
        status=r[5],
        revoked_at=r[6],
        revision=int(r[7]),
        recorded_by=r[8],
        recorded_at=r[9],
    )


def _snapshot_view(r: tuple[Any, ...]) -> GroupReportSnapshotView:
    return GroupReportSnapshotView(
        snapshot_id=r[0],
        owner_business_id=r[1],
        organizer_business_id=r[2],
        group_id=r[3],
        legal_entity_id=r[4],
        period_key=str(r[5]),
        currency=str(r[6]),
        report_set=r[7],
        metric_count=int(r[8]),
        metric_amount_minor=int(r[9]),
        notes=r[10],
        recorded_by=r[11],
        recorded_at=r[12],
    )


async def list_report_grants(
    conn: RuntimeConnection,
    business: UUID,
    *,
    group_id: UUID | None = None,
) -> GroupReportGrantList:
    await require_module(conn, business, ANALYTICS_MODULE)
    rows = await (
        await conn.execute(
            "select id, tenant_id, organizer_tenant_id, group_id, allowed_report_sets, status, "
            "revoked_at, revision, recorded_by, recorded_at "
            "from gba.enterprise_group_report_grants "
            "where (tenant_id = %s or organizer_tenant_id = %s) "
            "and (%s::uuid is null or group_id = %s) order by recorded_at desc, id",
            (business, business, group_id, group_id),
        )
    ).fetchall()
    return GroupReportGrantList(items=[_grant_view(r) for r in rows])


async def save_report_grant(
    conn: RuntimeConnection,
    business: UUID,
    grant_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: GroupReportGrantInput,
) -> GroupReportGrantView:
    """Member business grants, updates, or revokes which report sets a group organizer may read."""
    _check_ready()
    await require_module(conn, business, ANALYTICS_MODULE)
    scope = IdempotencyScope(business, actor, "enterprise.group_report.grant.save", key)
    replay = await commands.claim(
        conn,
        scope,
        commands.fingerprint({"grant_id": str(grant_id), **body.model_dump(mode="json")}),
        GroupReportGrantView,
    )
    if replay is not None:
        return replay

    # Verify this business is an active member of the target group
    member = await (
        await conn.execute(
            "select 1 from gba.business_group_members "
            "where organizer_tenant_id = %s and group_id = %s and member_tenant_id = %s "
            "and status = 'active'",
            (body.organizer_business_id, body.group_id, business),
        )
    ).fetchone()
    if member is None:
        raise EnterpriseStateError(
            "Business must be an active member of the group before granting report consent"
        )

    async with module_writes(ANALYTICS_MODULE):
        existing = await (
            await conn.execute(
                "select revision, status from gba.enterprise_group_report_grants "
                "where tenant_id = %s and id = %s for update",
                (business, grant_id),
            )
        ).fetchone()
        try:
            if existing is None:
                if body.expected_revision != 0:
                    raise EnterpriseRevisionConflictError(
                        "Report grant does not exist yet; expected_revision must be 0"
                    )
                await conn.execute(
                    "insert into gba.enterprise_group_report_grants ("
                    "id, tenant_id, organizer_tenant_id, group_id, allowed_report_sets, status, "
                    "revoked_at, revision, recorded_by"
                    ") values (%s, %s, %s, %s, %s, %s, "
                    "case when %s = 'revoked' then now() else null end, 1, %s)",
                    (
                        grant_id,
                        business,
                        body.organizer_business_id,
                        body.group_id,
                        list(body.allowed_report_sets),
                        body.status,
                        body.status,
                        user_id,
                    ),
                )
            else:
                if body.expected_revision != int(existing[0]):
                    raise EnterpriseRevisionConflictError("Report grant revision mismatch")
                await conn.execute(
                    "update gba.enterprise_group_report_grants set allowed_report_sets = %s, "
                    "status = %s, revoked_at = case when %s = 'revoked' then now() else null end, "
                    "revision = revision + 1, recorded_by = %s, recorded_at = now() "
                    "where tenant_id = %s and id = %s",
                    (
                        list(body.allowed_report_sets),
                        body.status,
                        body.status,
                        user_id,
                        business,
                        grant_id,
                    ),
                )
        except errors.UniqueViolation as exc:
            raise EnterpriseRevisionConflictError(
                "A report grant already exists for this group"
            ) from exc
        except errors.ForeignKeyViolation as exc:
            raise InvalidReferenceError("Referenced group not found") from exc

        row = await (
            await conn.execute(
                "select id, tenant_id, organizer_tenant_id, group_id, allowed_report_sets, "
                "status, revoked_at, revision, recorded_by, recorded_at "
                "from gba.enterprise_group_report_grants where tenant_id = %s and id = %s",
                (business, grant_id),
            )
        ).fetchone()
        if row is None:
            raise NotFoundError("Saved report grant not found")
        view = _grant_view(row)
        await commands.complete(conn, scope, view)
        return view


async def publish_report_snapshot(
    conn: RuntimeConnection,
    business: UUID,
    snapshot_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: GroupReportSnapshotInput,
) -> GroupReportSnapshotView:
    """Member business publishes an aggregate report snapshot attributed to its own legal entity
    and currency; visibility to the group organizer is strictly gated by RLS + active grant.
    """
    _check_ready()
    await require_module(conn, business, ANALYTICS_MODULE)
    scope = IdempotencyScope(business, actor, "enterprise.group_report.snapshot.save", key)
    replay = await commands.claim(
        conn,
        scope,
        commands.fingerprint({"snapshot_id": str(snapshot_id), **body.model_dump(mode="json")}),
        GroupReportSnapshotView,
    )
    if replay is not None:
        return replay

    async with module_writes(ANALYTICS_MODULE):
        try:
            await conn.execute(
                "insert into gba.enterprise_group_report_snapshots ("
                "id, tenant_id, organizer_tenant_id, group_id, legal_entity_id, period_key, "
                "currency, report_set, metric_count, metric_amount_minor, notes, recorded_by"
                ") values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "on conflict (tenant_id, group_id, legal_entity_id, "
                "period_key, currency, report_set) "
                "do update set metric_count = excluded.metric_count, "
                "metric_amount_minor = excluded.metric_amount_minor, "
                "notes = excluded.notes, recorded_by = excluded.recorded_by, recorded_at = now()",
                (
                    snapshot_id,
                    business,
                    body.organizer_business_id,
                    body.group_id,
                    body.legal_entity_id,
                    body.period_key,
                    body.currency,
                    body.report_set,
                    body.metric_count,
                    body.metric_amount_minor,
                    body.notes,
                    user_id,
                ),
            )
        except errors.ForeignKeyViolation as exc:
            raise InvalidReferenceError(
                "Referenced group, legal entity, or currency not found"
            ) from exc

        row = await (
            await conn.execute(
                "select id, tenant_id, organizer_tenant_id, group_id, legal_entity_id, "
                "period_key, currency, report_set, metric_count, metric_amount_minor, notes, "
                "recorded_by, recorded_at from gba.enterprise_group_report_snapshots "
                "where tenant_id = %s and group_id = %s and legal_entity_id = %s "
                "and period_key = %s and currency = %s and report_set = %s",
                (
                    business,
                    body.group_id,
                    body.legal_entity_id,
                    body.period_key,
                    body.currency,
                    body.report_set,
                ),
            )
        ).fetchone()
        if row is None:
            raise NotFoundError("Published snapshot not found")
        view = _snapshot_view(row)
        await commands.complete(conn, scope, view)
        return view


async def get_consolidated_group_report(
    conn: RuntimeConnection,
    business: UUID,
    group_id: UUID,
    *,
    period_key: str | None = None,
) -> ConsolidatedGroupReportView:
    """Return ONLY consented report snapshots for active members of a group owned by `business`,
    strictly separated by currency and attributed to each owner business and legal entity.
    """
    await require_module(conn, business, ANALYTICS_MODULE)
    grp = await (
        await conn.execute(
            "select 1 from gba.business_groups where organizer_tenant_id = %s and id = %s",
            (business, group_id),
        )
    ).fetchone()
    if grp is None:
        raise NotFoundError("Group not found for this organizer business")

    rows = await (
        await conn.execute(
            "select id, tenant_id, organizer_tenant_id, group_id, legal_entity_id, "
            "period_key, currency, report_set, metric_count, metric_amount_minor, notes, "
            "recorded_by, recorded_at from gba.enterprise_group_report_snapshots "
            "where organizer_tenant_id = %s and group_id = %s "
            "and (%s::text is null or period_key = %s) "
            "order by currency, report_set, tenant_id, legal_entity_id",
            (business, group_id, period_key, period_key),
        )
    ).fetchall()
    entries = [_snapshot_view(r) for r in rows]

    # Aggregate strictly by (currency, report_set) — never mix distinct currencies!
    bucket_counts: dict[tuple[str, ReportSet], int] = defaultdict(int)
    bucket_amounts: dict[tuple[str, ReportSet], int] = defaultdict(int)
    bucket_owners: dict[tuple[str, ReportSet], set[UUID]] = defaultdict(set)
    for e in entries:
        k = (e.currency, e.report_set)
        bucket_counts[k] += e.metric_count
        bucket_amounts[k] += e.metric_amount_minor
        bucket_owners[k].add(e.owner_business_id)

    totals = [
        CurrencyTotal(
            currency=curr,
            report_set=rset,
            total_count=bucket_counts[(curr, rset)],
            total_amount_minor=bucket_amounts[(curr, rset)],
            contributing_businesses=len(bucket_owners[(curr, rset)]),
        )
        for curr, rset in sorted(bucket_counts.keys())
    ]
    return ConsolidatedGroupReportView(
        group_id=group_id,
        organizer_business_id=business,
        period_key=period_key,
        entries=entries,
        totals_by_currency=totals,
    )
