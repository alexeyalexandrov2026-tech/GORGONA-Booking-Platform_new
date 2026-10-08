"""Owner-side 0029 -> 0030 rehearsal with mandatory rollback and no fact writes."""

from dataclasses import dataclass
from typing import Literal

import psycopg

from gorgona_booking.db.migrate import MIGRATION_LOCK_KEY, MigrationError, load_migrations


@dataclass(frozen=True, slots=True)
class H3UpgradeCheck:
    schema_version: Literal[1]
    target_version: Literal[30]
    checksum: str


def check_h3_upgrade(conninfo: str) -> H3UpgradeCheck:
    """Rehearse the packaged 0030, including all-tenant preflight, then roll back.

    This takes the same migration/table locks as a real upgrade. Run only against
    an owner-authorized target during its approved migration window. It cannot
    authorize deployment or reconcile conflicting facts.
    """
    migrations = load_migrations()
    target = next(migration for migration in migrations if migration.version == 30)
    expected = {migration.version: migration.checksum for migration in migrations[:29]}
    with psycopg.connect(conninfo, autocommit=True) as conn:
        role = conn.execute(
            "select rolsuper from pg_catalog.pg_roles where rolname=current_user"
        ).fetchone()
        if role is None or role[0]:
            raise MigrationError("H3 upgrade check requires the dedicated nonsuperuser owner")
        conn.execute("select pg_catalog.pg_advisory_lock(%s)", (MIGRATION_LOCK_KEY,))
        try:
            recorded: dict[int, str] = dict(
                conn.execute("select version,checksum from public.gba_schema_migrations")
            )
            if recorded != expected:
                raise MigrationError("H3 upgrade check requires exactly the approved 0001-0029")
            with conn.transaction(force_rollback=True):
                conn.execute(target.sql.encode("utf-8"))
        finally:
            conn.execute("select pg_catalog.pg_advisory_unlock(%s)", (MIGRATION_LOCK_KEY,))
    return H3UpgradeCheck(schema_version=1, target_version=30, checksum=target.checksum)
