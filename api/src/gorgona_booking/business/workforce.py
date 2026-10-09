"""I1 commands reuse business receipts/audit and shared resource locks/occupancy."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from uuid import UUID, uuid7

import psycopg

from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.repository import lock_resource_schedule
from gorgona_booking.business import commands, modules
from gorgona_booking.business.module_gate import module_writes, require_module
from gorgona_booking.business.readiness_registry import at_least
from gorgona_booking.business.workforce_contracts import (
    AssignmentInput,
    ProfileInput,
    ProfileList,
    ProfileView,
    ShiftInput,
    ShiftList,
    ShiftView,
    SkillHistory,
    SkillInput,
    SkillList,
    SkillView,
    StaffSkillInput,
    StaffSkillView,
    WorkforceReceipt,
)
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, DomainError, InvalidReferenceError, NotFoundError


class WorkforceNotReadyError(ConflictError):
    code = "MODULE_NOT_READY"


class WorkforceConflictError(ConflictError):
    code = "WORKFORCE_CONFLICT"


class WorkforceSkillError(DomainError):
    code = "WORKFORCE_SKILL_REQUIRED"


async def require_workforce(conn: RuntimeConnection, business: UUID) -> None:
    current = modules.MODULES_BY_ID["workforce"]
    if not current.enableable or not at_least(current.readiness, modules.MINIMUM_READINESS):
        raise WorkforceNotReadyError("Workforce has not been accepted", module_id="workforce")
    await require_module(conn, business, "workforce")
    for dependency in current.depends_on:
        if modules.MODULES_BY_ID[dependency].kind == modules.ModuleKind.OPTIONAL:
            await require_module(conn, business, dependency)


@asynccontextmanager
async def _writes(conn: RuntimeConnection, business: UUID) -> AsyncIterator[None]:
    await require_workforce(conn, business)
    try:
        async with conn.transaction(), module_writes("workforce"):
            yield
            # Surface deferred integrity failures before returning the API result.
            await conn.execute("set constraints all immediate")
            await conn.execute("set constraints all deferred")
    except psycopg.errors.ExclusionViolation as exc:
        raise WorkforceConflictError("The employee already has an overlapping shift") from exc
    except psycopg.errors.UniqueViolation as exc:
        raise WorkforceConflictError("This workforce record already exists") from exc
    except psycopg.errors.ForeignKeyViolation as exc:
        raise InvalidReferenceError("A workforce reference is unavailable") from exc
    except psycopg.DatabaseError as exc:
        if exc.sqlstate == "GBW01":
            raise WorkforceConflictError("The workforce revision has changed") from exc
        if exc.sqlstate == "GBW02":
            raise WorkforceSkillError(
                "A required skill is not effective at the shift start"
            ) from exc
        if exc.sqlstate == "23514":
            raise InvalidReferenceError("This workforce state or reference is invalid") from exc
        raise


async def load_profile(conn: RuntimeConnection, business: UUID, profile: UUID) -> ProfileView:
    row = await (
        await conn.execute(
            "select p.membership_id,p.resource_id,p.location_id,m.user_id "
            "from gba.staff_profiles p "
            "join gba.memberships m on m.tenant_id=p.tenant_id and m.id=p.membership_id "
            "where p.tenant_id=%s and p.id=%s",
            (business, profile),
        )
    ).fetchone()
    if row is None:
        raise NotFoundError("Staff profile not found")
    return ProfileView(
        business_id=business,
        profile_id=profile,
        membership_id=row[0],
        resource_id=row[1],
        location_id=row[2],
        user_id=row[3],
    )


async def save_profile(
    conn: RuntimeConnection,
    business: UUID,
    profile: UUID,
    user: UUID,
    actor: str,
    key: str,
    body: ProfileInput,
) -> ProfileView:
    async with _writes(conn, business):
        scope = IdempotencyScope(business, actor, "workforce.profile", key)
        receipt = await commands.claim(
            conn,
            scope,
            commands.fingerprint({"id": str(profile), **body.model_dump(mode="json")}),
            WorkforceReceipt,
        )
        if receipt is not None:
            return await load_profile(conn, business, receipt.subject_id)
        membership = await (
            await conn.execute(
                "select user_id from gba.memberships where tenant_id=%s and "
                "id=%s and status='active'",
                (business, body.membership_id),
            )
        ).fetchone()
        if membership is None:
            raise InvalidReferenceError("An active membership is required")
        staff_user = UUID(str(membership[0]))
        await conn.execute(
            "select pg_advisory_xact_lock(hashtextextended(%s,0))",
            (f"gba:staff-profile:{business}:{staff_user}",),
        )
        owned = await (
            await conn.execute(
                "select resource_id,location_id from gba.staff_resource_owners "
                "where tenant_id=%s and user_id=%s",
                (business, staff_user),
            )
        ).fetchone()
        if owned is not None and owned[1] != body.location_id:
            raise WorkforceConflictError("This employee already has another home branch")
        resource = UUID(str(owned[0])) if owned is not None else uuid7()
        if owned is None:
            await conn.execute(
                "insert into gba.resources (tenant_id,id,location_id,kind,display_name) "
                "values (%s,%s,%s,'staff',%s)",
                (business, resource, body.location_id, f"Staff {staff_user}"),
            )
            await conn.execute(
                "insert into gba.staff_resource_owners "
                "(tenant_id,user_id,resource_id,location_id,created_by) values (%s,%s,%s,%s,%s)",
                (business, staff_user, resource, body.location_id, user),
            )
        await conn.execute(
            "insert into gba.staff_profiles "
            "(tenant_id,id,membership_id,user_id,resource_id,location_id,created_by) "
            "values (%s,%s,%s,%s,%s,%s,%s)",
            (business, profile, body.membership_id, staff_user, resource, body.location_id, user),
        )
        await _finish(conn, business, actor, "profile", scope, WorkforceReceipt(subject_id=profile))
        return await load_profile(conn, business, profile)


async def load_skill(
    conn: RuntimeConnection, business: UUID, skill: UUID, revision: int | None = None
) -> SkillView:
    row = await (
        await conn.execute(
            "select s.code,v.revision,v.name,v.archived from gba.work_skills s "
            "join gba.work_skill_versions v on v.tenant_id=s.tenant_id and v.skill_id=s.id "
            "where s.tenant_id=%s and s.id=%s and (%s::integer is null or v.revision=%s) "
            "order by v.revision desc limit 1",
            (business, skill, revision, revision),
        )
    ).fetchone()
    if row is None:
        raise NotFoundError("Skill not found")
    return SkillView(
        business_id=business,
        skill_id=skill,
        code=row[0],
        revision=row[1],
        name=row[2],
        archived=row[3],
    )


async def save_skill(
    conn: RuntimeConnection,
    business: UUID,
    skill: UUID,
    user: UUID,
    actor: str,
    key: str,
    body: SkillInput,
) -> SkillView:
    async with _writes(conn, business):
        scope = IdempotencyScope(business, actor, "workforce.skill", key)
        receipt = await commands.claim(
            conn,
            scope,
            commands.fingerprint({"id": str(skill), **body.model_dump(mode="json")}),
            WorkforceReceipt,
        )
        if receipt is not None:
            return await load_skill(conn, business, skill, receipt.revision)
        if body.expected_revision == 0:
            await conn.execute(
                "insert into gba.work_skills (tenant_id,id,code) values (%s,%s,%s)",
                (business, skill, body.code),
            )
        else:
            current = await load_skill(conn, business, skill)
            if current.code != body.code:
                raise InvalidReferenceError("A skill keeps its code")
        revision = body.expected_revision + 1
        await conn.execute(
            "insert into gba.work_skill_versions "
            "(tenant_id,skill_id,revision,name,archived,created_by) "
            "values (%s,%s,%s,%s,%s,%s)",
            (business, skill, revision, body.name, body.archived, user),
        )
        await _finish(
            conn,
            business,
            actor,
            "skill",
            scope,
            WorkforceReceipt(subject_id=skill, revision=revision),
        )
        return await load_skill(conn, business, skill, revision)


async def save_staff_skill(
    conn: RuntimeConnection,
    business: UUID,
    profile: UUID,
    skill: UUID,
    user: UUID,
    actor: str,
    key: str,
    body: StaffSkillInput,
) -> StaffSkillView:
    async with _writes(conn, business):
        scope = IdempotencyScope(business, actor, "workforce.staff_skill", key)
        receipt = await commands.claim(
            conn,
            scope,
            commands.fingerprint(
                {"id": str(profile), "skill_id": str(skill), **body.model_dump(mode="json")}
            ),
            WorkforceReceipt,
        )
        revision = body.expected_revision + 1
        if receipt is None:
            await load_profile(conn, business, profile)
            await load_skill(conn, business, skill)
            await conn.execute(
                "insert into gba.staff_skill_events "
                "(tenant_id,profile_id,skill_id,revision,effective_at,granted,created_by) "
                "values (%s,%s,%s,%s,%s,%s,%s)",
                (business, profile, skill, revision, body.effective_at, body.granted, user),
            )
            await _finish(
                conn,
                business,
                actor,
                "staff_skill",
                scope,
                WorkforceReceipt(subject_id=profile, revision=revision, skill_id=skill),
            )
        return await load_staff_skill(conn, business, profile, skill, revision)


async def load_staff_skill(
    conn: RuntimeConnection, business: UUID, profile: UUID, skill: UUID, revision: int
) -> StaffSkillView:
    row = await (
        await conn.execute(
            "select effective_at,granted from gba.staff_skill_events "
            "where tenant_id=%s and profile_id=%s and skill_id=%s "
            "and revision=%s",
            (business, profile, skill, revision),
        )
    ).fetchone()
    if row is None:
        raise NotFoundError("Staff skill event not found")
    return StaffSkillView(
        business_id=business,
        profile_id=profile,
        skill_id=skill,
        revision=revision,
        effective_at=row[0],
        granted=row[1],
    )


async def load_shift(
    conn: RuntimeConnection, business: UUID, shift: UUID, revision: int | None = None
) -> ShiftView:
    row = await (
        await conn.execute(
            "select s.location_id,v.revision,v.position,v.starts_at,v.ends_at,v.required_skill_ids,"
            "v.status,v.profile_id,a.id from gba.work_shifts s join gba.work_shift_versions v "
            "on v.tenant_id=s.tenant_id and v.shift_id=s.id left join gba.shift_assignments a "
            "on a.tenant_id=v.tenant_id and a.shift_id=v.shift_id and a.shift_revision=v.revision "
            "where s.tenant_id=%s and s.id=%s and (%s::integer is null or v.revision=%s) "
            "order by v.revision desc limit 1",
            (business, shift, revision, revision),
        )
    ).fetchone()
    if row is None:
        raise NotFoundError("Shift not found")
    return ShiftView(
        business_id=business,
        shift_id=shift,
        location_id=row[0],
        revision=row[1],
        position=row[2],
        starts_at=row[3],
        ends_at=row[4],
        required_skill_ids=tuple(row[5]),
        status=row[6],
        staff_profile_id=row[7],
        assignment_id=row[8],
    )


async def save_shift(
    conn: RuntimeConnection,
    business: UUID,
    shift: UUID,
    user: UUID,
    actor: str,
    key: str,
    body: ShiftInput,
) -> ShiftView:
    async with _writes(conn, business):
        scope = IdempotencyScope(business, actor, "workforce.shift", key)
        receipt = await commands.claim(
            conn,
            scope,
            commands.fingerprint({"id": str(shift), **body.model_dump(mode="json")}),
            WorkforceReceipt,
        )
        if receipt is not None:
            return await load_shift(conn, business, shift, receipt.revision)
        previous: ShiftView | None = None
        if body.expected_revision:
            previous = await load_shift(conn, business, shift)
            if previous.location_id != body.location_id:
                raise InvalidReferenceError("A shift keeps its branch")
        profiles = {
            x
            for x in (body.staff_profile_id, previous.staff_profile_id if previous else None)
            if x is not None
        }
        resources = [await load_profile(conn, business, p) for p in profiles]
        for resource in sorted(p.resource_id for p in resources):
            await lock_resource_schedule(conn, business, resource)
        if body.expected_revision == 0:
            await conn.execute(
                "insert into gba.work_shifts (tenant_id,id,location_id) values (%s,%s,%s)",
                (business, shift, body.location_id),
            )
        revision = body.expected_revision + 1
        await conn.execute(
            "insert into gba.work_shift_versions "
            "(tenant_id,shift_id,revision,position,starts_at,ends_at,required_skill_ids,"
            "status,profile_id,created_by) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                business,
                shift,
                revision,
                body.position,
                body.starts_at,
                body.ends_at,
                list(body.required_skill_ids),
                body.status,
                body.staff_profile_id,
                user,
            ),
        )
        await _finish(
            conn,
            business,
            actor,
            "shift",
            scope,
            WorkforceReceipt(subject_id=shift, revision=revision),
        )
        return await load_shift(conn, business, shift, revision)


async def assign(
    conn: RuntimeConnection,
    business: UUID,
    shift: UUID,
    user: UUID,
    actor: str,
    key: str,
    body: AssignmentInput,
) -> ShiftView:
    current = await load_shift(conn, business, shift, body.expected_revision)
    if current.status == "cancelled":
        raise WorkforceConflictError("A cancelled shift cannot be assigned")
    command = ShiftInput(
        expected_revision=body.expected_revision,
        location_id=current.location_id,
        position=current.position,
        starts_at=current.starts_at,
        ends_at=current.ends_at,
        required_skill_ids=current.required_skill_ids,
        status="published",
        staff_profile_id=body.staff_profile_id,
    )
    return await save_shift(conn, business, shift, user, actor, key, command)


async def _finish(
    conn: RuntimeConnection,
    business: UUID,
    actor: str,
    kind: str,
    scope: IdempotencyScope,
    receipt: WorkforceReceipt,
) -> None:
    await commands.audit(
        conn,
        business,
        actor,
        f"workforce.{kind}",
        kind,
        str(receipt.subject_id),
        {"revision": receipt.revision},
    )
    await commands.complete(conn, scope, receipt)


async def list_profiles(
    conn: RuntimeConnection, business: UUID, after: UUID | None, limit: int
) -> ProfileList:
    rows = await (
        await conn.execute(
            "select p.id,p.membership_id,p.resource_id,p.location_id,m.user_id "
            "from gba.staff_profiles p join gba.memberships m "
            "on m.tenant_id=p.tenant_id and m.id=p.membership_id where p.tenant_id=%s "
            "and (%s::uuid is null or p.id>%s) order by p.id limit %s",
            (business, after, after, limit + 1),
        )
    ).fetchall()
    items = tuple(
        ProfileView(
            business_id=business,
            profile_id=r[0],
            membership_id=r[1],
            resource_id=r[2],
            location_id=r[3],
            user_id=r[4],
        )
        for r in rows[:limit]
    )
    return ProfileList(items=items, next_cursor=items[-1].profile_id if len(rows) > limit else None)


async def list_skills(
    conn: RuntimeConnection, business: UUID, after: UUID | None, limit: int
) -> SkillList:
    rows = await (
        await conn.execute(
            "select s.id,s.code,v.revision,v.name,v.archived from gba.work_skills s "
            "join lateral (select revision,name,archived from gba.work_skill_versions "
            "where tenant_id=s.tenant_id and skill_id=s.id order by revision "
            "desc limit 1) v on true "
            "where s.tenant_id=%s and (%s::uuid is null or s.id>%s) order by s.id limit %s",
            (business, after, after, limit + 1),
        )
    ).fetchall()
    items = tuple(
        SkillView(
            business_id=business, skill_id=r[0], code=r[1], revision=r[2], name=r[3], archived=r[4]
        )
        for r in rows[:limit]
    )
    return SkillList(items=items, next_cursor=items[-1].skill_id if len(rows) > limit else None)


async def skill_history(
    conn: RuntimeConnection, business: UUID, profile: UUID, skill: UUID, after: int, limit: int
) -> SkillHistory:
    await load_profile(conn, business, profile)
    rows = await (
        await conn.execute(
            "select revision,effective_at,granted from "
            "gba.staff_skill_events where tenant_id=%s and profile_id=%s "
            "and skill_id=%s and revision>%s order by revision limit %s",
            (business, profile, skill, after, limit + 1),
        )
    ).fetchall()
    items = tuple(
        StaffSkillView(
            business_id=business,
            profile_id=profile,
            skill_id=skill,
            revision=r[0],
            effective_at=r[1],
            granted=r[2],
        )
        for r in rows[:limit]
    )
    return SkillHistory(
        items=items, next_revision=items[-1].revision if len(rows) > limit else None
    )


async def list_shifts(
    conn: RuntimeConnection,
    business: UUID,
    starts: datetime,
    ends: datetime,
    after: UUID | None,
    limit: int,
    user: UUID | None,
) -> ShiftList:
    rows = await (
        await conn.execute(
            "select s.id,s.location_id,v.revision,v.position,v.starts_at,v.ends_at,"
            "v.required_skill_ids,v.status,v.profile_id,a.id from gba.work_shifts s join lateral "
            "(select "
            "revision,position,starts_at,ends_at,required_skill_ids,profile_i"
            "d,status from gba.work_shift_versions "
            "where tenant_id=s.tenant_id and shift_id=s.id order by revision "
            "desc limit 1) v on true "
            "left join gba.staff_profiles p on p.tenant_id=s.tenant_id and p.id=v.profile_id "
            "left join gba.memberships m on m.tenant_id=p.tenant_id and m.id=p.membership_id "
            "left join gba.shift_assignments a on a.tenant_id=s.tenant_id "
            "and a.shift_id=s.id and a.shift_revision=v.revision "
            "where s.tenant_id=%s and v.starts_at<%s and v.ends_at>%s "
            "and (%s::uuid is null or s.id>%s) "
            "and (%s::uuid is null or m.user_id=%s) order by s.id limit %s",
            (business, ends, starts, after, after, user, user, limit + 1),
        )
    ).fetchall()
    items = tuple(
        ShiftView(
            business_id=business,
            shift_id=r[0],
            location_id=r[1],
            revision=r[2],
            position=r[3],
            starts_at=r[4],
            ends_at=r[5],
            required_skill_ids=tuple(r[6]),
            status=r[7],
            staff_profile_id=r[8],
            assignment_id=r[9],
        )
        for r in rows[:limit]
    )
    return ShiftList(items=items, next_cursor=items[-1].shift_id if len(rows) > limit else None)
