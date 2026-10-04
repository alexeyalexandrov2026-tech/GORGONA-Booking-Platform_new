"""Configuration versions: draft -> validated -> published -> superseded (ADR-0019).

Commands run under the per-business `business-configuration` advisory lock, which
the database booking trigger takes in shared mode, so a booking is ordered entirely
before or after a publication. Every command checks the latest version and the
expected revision, keeps an idempotent receipt and writes its audit event in the
same transaction.
"""

from typing import Any, Literal
from uuid import UUID

from psycopg.errors import ForeignKeyViolation
from psycopg.types.json import Jsonb

from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.business import commands
from gorgona_booking.business.configuration_contracts import (
    ConfigurationCommand,
    ConfigurationDraftInput,
    ConfigurationPreview,
    ConfigurationProblem,
    ConfigurationValidation,
    ConfigurationVersionList,
    ConfigurationVersionView,
    ConfigurationView,
    ModuleStop,
)
from gorgona_booking.business.modules import (
    BASELINE_MODULE_IDS,
    BOOKING_MODULE,
    MODULE_REGISTRY_VERSION,
    MODULES_BY_ID,
    OPTIONAL_MODULE_IDS,
    ModuleDisabledError,
    effective_modules,
    selection_problems,
)
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, DomainError, InvalidReferenceError, NotFoundError


class ConfigurationStateError(DomainError):
    code = "CONFIGURATION_STATE_INVALID"


class ConfigurationInvalidError(DomainError):
    code = "CONFIGURATION_INVALID"


_SELECT = (
    "select version, state, revision, profile_revision, registry_version, created_at, "
    "validation, validated_at, published_at, superseded_at, superseded_by_version "
    "from gba.business_configuration_versions where tenant_id = %s "
)


async def _views(
    conn: RuntimeConnection, business_id: UUID, rows: list[tuple[Any, ...]]
) -> list[ConfigurationVersionView]:
    if not rows:
        return []
    modules = await (
        await conn.execute(
            "select version, module_id from gba.business_configuration_modules "
            "where tenant_id = %s and version = any(%s) order by module_id",
            (business_id, [row[0] for row in rows]),
        )
    ).fetchall()
    return [
        ConfigurationVersionView(
            business_id=business_id,
            version=row[0],
            state=row[1],
            revision=row[2],
            profile_revision=row[3],
            registry_version=row[4],
            module_ids=tuple(m[1] for m in modules if m[0] == row[0]),
            created_at=row[5],
            validation=ConfigurationValidation.model_validate(row[6]) if row[6] else None,
            validated_at=row[7],
            published_at=row[8],
            superseded_at=row[9],
            superseded_by_version=row[10],
        )
        for row in rows
    ]


async def _one(
    conn: RuntimeConnection, business_id: UUID, condition: str, params: tuple[Any, ...] = ()
) -> ConfigurationVersionView | None:
    row = await (await conn.execute(_SELECT + condition, (business_id, *params))).fetchone()
    views = await _views(conn, business_id, [row] if row else [])
    return views[0] if views else None


async def load_version(
    conn: RuntimeConnection, business_id: UUID, version: int
) -> ConfigurationVersionView | None:
    return await _one(conn, business_id, "and version = %s", (version,))


async def _latest_number(conn: RuntimeConnection, business_id: UUID) -> int:
    row = await (
        await conn.execute(
            "select coalesce(max(version), 0) from gba.business_configuration_versions "
            "where tenant_id = %s",
            (business_id,),
        )
    ).fetchone()
    return int(row[0]) if row else 0


async def load_configuration(conn: RuntimeConnection, business_id: UUID) -> ConfigurationView:
    published = await _one(conn, business_id, "and state = 'published'")
    latest = await _one(conn, business_id, "order by version desc limit 1")
    return ConfigurationView(
        business_id=business_id,
        registry_version=MODULE_REGISTRY_VERSION,
        baseline=published is None,
        published=published,
        latest=latest,
        effective_module_ids=effective_modules(
            published.module_ids if published else BASELINE_MODULE_IDS
        ),
    )


async def list_versions(
    conn: RuntimeConnection, business_id: UUID, *, before: int | None, limit: int
) -> ConfigurationVersionList:
    """Newest first; `before` continues below the last version of the previous page."""
    rows = await (
        await conn.execute(
            _SELECT + "and (%s::integer is null or version < %s) order by version desc limit %s",
            (business_id, before, before, limit + 1),
        )
    ).fetchall()
    items = tuple(await _views(conn, business_id, rows[:limit]))
    return ConfigurationVersionList(
        business_id=business_id,
        items=items,
        next_cursor=items[-1].version if len(rows) > limit else None,
    )


async def _latest_profile_revision(conn: RuntimeConnection, business_id: UUID) -> int | None:
    row = await (
        await conn.execute(
            "select max(revision) from gba.business_profile_versions where tenant_id = %s",
            (business_id,),
        )
    ).fetchone()
    return int(row[0]) if row and row[0] is not None else None


async def _industries(conn: RuntimeConnection, business_id: UUID, revision: int) -> set[int]:
    rows = await (
        await conn.execute(
            "select industry_id from gba.business_profile_industries "
            "where tenant_id = %s and revision = %s",
            (business_id, revision),
        )
    ).fetchall()
    return {int(row[0]) for row in rows}


async def _check(
    conn: RuntimeConnection,
    business_id: UUID,
    version: ConfigurationVersionView,
    latest_profile: int | None = None,
) -> ConfigurationValidation:
    problems = [
        ConfigurationProblem(code=code, module_id=module_id, message=message)
        for code, module_id, message in selection_problems(version.module_ids)
    ]
    if version.registry_version != MODULE_REGISTRY_VERSION:
        problems.append(
            ConfigurationProblem(
                code="REGISTRY_CHANGED",
                module_id=None,
                message="The module registry changed since this draft; save a new draft",
            )
        )
    warnings = []
    if latest_profile is None:
        latest_profile = await _latest_profile_revision(conn, business_id)
    if latest_profile is not None and latest_profile > version.profile_revision:
        warnings.append(
            ConfigurationProblem(
                code="PROFILE_OUTDATED",
                module_id=None,
                message=f"The draft pins profile revision {version.profile_revision}; "
                f"revision {latest_profile} is newer",
            )
        )
    return ConfigurationValidation(
        registry_version=MODULE_REGISTRY_VERSION,
        problems=tuple(problems),
        warnings=tuple(warnings),
    )


def _refuse(validation: ConfigurationValidation) -> None:
    if validation.problems:
        raise ConfigurationInvalidError(
            "This configuration cannot be used until its problems are fixed",
            problems=[problem.model_dump(mode="json") for problem in validation.problems],
        )


async def preview_version(
    conn: RuntimeConnection, business_id: UUID, version: int
) -> ConfigurationPreview:
    view = await load_version(conn, business_id, version)
    if view is None:
        raise NotFoundError("Configuration version not found")
    published = await _one(conn, business_id, "and state = 'published'")
    current = set(published.module_ids if published else BASELINE_MODULE_IDS)
    selected = set(view.module_ids)
    disabling = tuple(sorted(current - selected))
    industries = await _industries(conn, business_id, view.profile_revision)
    previous = (
        await _industries(conn, business_id, published.profile_revision) if published else set()
    )
    latest_profile = await _latest_profile_revision(conn, business_id)
    check = await _check(conn, business_id, view, latest_profile)
    return ConfigurationPreview(
        business_id=business_id,
        version=version,
        compared_to_version=published.version if published else None,
        enabling=tuple(sorted(selected - current)),
        disabling=disabling,
        stopping=tuple(ModuleStop(module_id=m, stops=MODULES_BY_ID[m].stops) for m in disabling),
        industries_added=tuple(sorted(industries - previous)),
        industries_removed=tuple(sorted(previous - industries)),
        profile_revision=view.profile_revision,
        latest_profile_revision=latest_profile,
        problems=check.problems,
        warnings=check.warnings,
    )


async def _audit(
    conn: RuntimeConnection,
    business_id: UUID,
    actor: str,
    action: str,
    version: int,
    **details: Any,
) -> None:
    await commands.audit(
        conn,
        business_id,
        actor,
        f"business_configuration.{action}",
        "business_configuration",
        str(version),
        {"version": version, **details},
    )


async def save_draft(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    user_id: UUID,
    actor: str,
    key: str,
    body: ConfigurationDraftInput,
) -> ConfigurationVersionView:
    scope = IdempotencyScope(business_id, actor, "business.configuration.draft", key)
    command = body.model_dump(mode="json") | {"module_ids": sorted(body.module_ids)}
    request_hash = commands.fingerprint(command)
    if (
        previous := await commands.claim(conn, scope, request_hash, ConfigurationVersionView)
    ) is not None:
        return previous
    latest = await _latest_number(conn, business_id)
    if latest != body.expected_version:
        raise ConflictError("The configuration changed. Reload it before saving.", version=latest)
    version = latest + 1
    try:
        async with conn.transaction():
            await conn.execute(
                "insert into gba.business_configuration_versions "
                "(tenant_id, version, profile_revision, registry_version, created_by) "
                "values (%s, %s, %s, %s, %s)",
                (business_id, version, body.profile_revision, MODULE_REGISTRY_VERSION, user_id),
            )
    except ForeignKeyViolation as exc:
        raise InvalidReferenceError(
            "Unknown business profile revision", field="profile_revision"
        ) from exc
    for module_id in sorted(body.module_ids):
        await conn.execute(
            "insert into gba.business_configuration_modules (tenant_id, version, module_id) "
            "values (%s, %s, %s)",
            (business_id, version, module_id),
        )
    result = await load_version(conn, business_id, version)
    if result is None:
        raise RuntimeError("Configuration insert did not produce a version")
    await _audit(
        conn,
        business_id,
        actor,
        "drafted",
        version,
        profile_revision=body.profile_revision,
        module_ids=sorted(body.module_ids),
    )
    await commands.complete(conn, scope, result)
    return result


async def _target(
    conn: RuntimeConnection,
    business_id: UUID,
    version: int,
    body: ConfigurationCommand,
    state: Literal["draft", "validated"],
) -> ConfigurationVersionView:
    row = await (
        await conn.execute(
            "select version from gba.business_configuration_versions "
            "where tenant_id = %s and version = %s for update",
            (business_id, version),
        )
    ).fetchone()
    current = await load_version(conn, business_id, version) if row else None
    if current is None:
        raise NotFoundError("Configuration version not found")
    latest = await _latest_number(conn, business_id)
    if latest != version:
        raise ConflictError(
            "A newer configuration version exists. Reload it before continuing.", version=latest
        )
    if body.expected_revision != current.revision:
        raise ConflictError(
            "This configuration version changed. Reload it before continuing.",
            revision=current.revision,
        )
    if current.state != state:
        raise ConfigurationStateError(f"Only a {state} configuration can take this step")
    return current


async def validate_version(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    version: int,
    user_id: UUID,
    actor: str,
    key: str,
    body: ConfigurationCommand,
) -> ConfigurationVersionView:
    scope = IdempotencyScope(business_id, actor, "business.configuration.validate", key)
    request_hash = commands.fingerprint({"version": version, **body.model_dump(mode="json")})
    if (
        previous := await commands.claim(conn, scope, request_hash, ConfigurationVersionView)
    ) is not None:
        return previous
    current = await _target(conn, business_id, version, body, "draft")
    validation = await _check(conn, business_id, current)
    _refuse(validation)
    await conn.execute(
        "update gba.business_configuration_versions set state = 'validated', "
        "revision = revision + 1, validated_by = %s, validated_at = now(), validation = %s "
        "where tenant_id = %s and version = %s",
        (user_id, Jsonb(validation.model_dump(mode="json")), business_id, version),
    )
    result = await load_version(conn, business_id, version)
    if result is None:
        raise RuntimeError("Configuration disappeared during validation")
    await _audit(
        conn,
        business_id,
        actor,
        "validated",
        version,
        revision=result.revision,
        warnings=[warning.code for warning in validation.warnings],
    )
    await commands.complete(conn, scope, result)
    return result


async def publish_version(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    version: int,
    user_id: UUID,
    actor: str,
    key: str,
    body: ConfigurationCommand,
) -> ConfigurationVersionView:
    """Re-validate under the lock, supersede the previous version, then publish."""
    scope = IdempotencyScope(business_id, actor, "business.configuration.publish", key)
    request_hash = commands.fingerprint({"version": version, **body.model_dump(mode="json")})
    if (
        previous := await commands.claim(conn, scope, request_hash, ConfigurationVersionView)
    ) is not None:
        return previous
    current = await _target(conn, business_id, version, body, "validated")
    _refuse(await _check(conn, business_id, current))
    published = await _one(conn, business_id, "and state = 'published' for update")
    if published is not None:
        await conn.execute(
            "update gba.business_configuration_versions set state = 'superseded', "
            "revision = revision + 1, superseded_by_version = %s, superseded_at = now() "
            "where tenant_id = %s and version = %s",
            (version, business_id, published.version),
        )
    await conn.execute(
        "update gba.business_configuration_versions set state = 'published', "
        "revision = revision + 1, published_by = %s, published_at = now() "
        "where tenant_id = %s and version = %s",
        (user_id, business_id, version),
    )
    for module_id in sorted(OPTIONAL_MODULE_IDS):
        await conn.execute(
            "insert into gba.business_module_states as s "
            "(tenant_id, module_id, enabled, configuration_version, updated_by) "
            "values (%s, %s, %s, %s, %s) on conflict (tenant_id, module_id) do update set "
            "enabled = excluded.enabled, configuration_version = excluded.configuration_version, "
            "revision = s.revision + 1, updated_by = excluded.updated_by, updated_at = now()",
            (business_id, module_id, module_id in current.module_ids, version, user_id),
        )
    result = await load_version(conn, business_id, version)
    if result is None:
        raise RuntimeError("Configuration disappeared during publication")
    before = set(published.module_ids if published else BASELINE_MODULE_IDS)
    await _audit(
        conn,
        business_id,
        actor,
        "published",
        version,
        previous_version=published.version if published else None,
        enabled=sorted(set(current.module_ids) - before),
        disabled=sorted(before - set(current.module_ids)),
    )
    await commands.complete(conn, scope, result)
    return result


async def module_enabled(conn: RuntimeConnection, business_id: UUID, module_id: str) -> bool:
    """The published state, or the implicit baseline before a first publication."""
    row = await (
        await conn.execute(
            "select enabled from gba.business_module_states "
            "where tenant_id = %s and module_id = %s",
            (business_id, module_id),
        )
    ).fetchone()
    if row is None:
        return module_id in BASELINE_MODULE_IDS
    return bool(row[0])


async def require_booking_enabled(conn: RuntimeConnection, business_id: UUID) -> None:
    if not await module_enabled(conn, business_id, BOOKING_MODULE):
        raise ModuleDisabledError("Booking is turned off in this business's configuration")
