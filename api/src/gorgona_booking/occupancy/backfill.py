"""Operator step: copy one company's pre-0018 booking allocations into shared occupancy.

Migrations never bypass row security, so the copy runs per company in that
company's context with the owner credential, like onboarding (ADR-0010). It is
safe to repeat; the result must end with no mismatches.
"""

from dataclasses import dataclass
from uuid import UUID

import psycopg

from gorgona_booking.db.provisioning import owner_tenant_transaction


@dataclass(frozen=True, slots=True)
class BackfillResult:
    copied: int
    mismatches: int


class UnknownCompanyError(LookupError):
    pass


def backfill_for_owner(conn: psycopg.Connection, tenant_id: UUID) -> BackfillResult:
    with owner_tenant_transaction(conn, tenant_id):
        if conn.execute("select 1 from gba.tenants where id = %s", (tenant_id,)).fetchone() is None:
            # Row security would otherwise report an unknown company as consistent.
            raise UnknownCompanyError(str(tenant_id))
        copied = conn.execute("select gba.backfill_booking_occupancy()").fetchone()
        drift = conn.execute("select gba.booking_occupancy_mismatches()").fetchone()
    assert copied is not None  # noqa: S101 - an aggregate returns a row
    assert drift is not None  # noqa: S101 - an aggregate returns a row
    return BackfillResult(copied=int(copied[0]), mismatches=int(drift[0]))
