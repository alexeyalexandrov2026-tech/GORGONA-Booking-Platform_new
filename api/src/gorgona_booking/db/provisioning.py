"""Owner-side provisioning. Forced RLS applies to the owner as well, so every write
here runs inside a transaction with explicit tenant context."""

from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from typing import Literal
from uuid import UUID, uuid7

import psycopg


@contextmanager
def owner_tenant_transaction(
    conn: psycopg.Connection, tenant_id: UUID
) -> Iterator[psycopg.Connection]:
    with conn.transaction():
        conn.execute("select pg_catalog.set_config('gba.tenant_id', %s, true)", (str(tenant_id),))
        yield conn


def provision_tenant(
    conn: psycopg.Connection, *, slug: str, display_name: str, hosts: Iterable[str] = ()
) -> UUID:
    tenant_id = uuid7()
    with owner_tenant_transaction(conn, tenant_id):
        conn.execute(
            "insert into gba.tenants (id, slug, display_name) values (%s, %s, %s)",
            (tenant_id, slug, display_name),
        )
        for host in hosts:
            conn.execute(
                "insert into gba.tenant_hosts (host, tenant_id) values (%s, %s)",
                (host.lower(), tenant_id),
            )
    return tenant_id


type AdmissionState = Literal["test_access", "suspended"]


def record_receipt_admission(
    conn: psycopg.Connection,
    tenant_id: UUID,
    connection_id: UUID,
    *,
    state: AdmissionState,
    account_id: str,
    charge: bool,
    refund: bool,
    evidence: str,
) -> int:
    """K0b: the owner records the next admission revision of a receipt connection.

    Test mode and USD only; the database checks the connection, its account and scope, numbers
    the revision and records the session login and time. Returns the new revision.
    """
    with owner_tenant_transaction(conn, tenant_id):
        row = conn.execute(
            "insert into gba.provider_connection_admissions (tenant_id,connection_id,state,"
            "charge_allowed,refund_allowed,account_id,evidence) values (%s,%s,%s,%s,%s,%s,%s) "
            "returning revision",
            (tenant_id, connection_id, state, charge, refund, account_id, evidence),
        ).fetchone()
    if row is None:
        raise RuntimeError("Receipt connection admission was not recorded")
    return int(row[0])


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _set_context(conn: psycopg.Connection, **settings: str) -> None:
    """Transaction-local settings read by RLS policies and audit triggers."""
    for key, value in settings.items():
        conn.execute("select pg_catalog.set_config(%s, %s, true)", (f"gba.{key}", value))


def provision_user(
    conn: psycopg.Connection,
    *,
    display_name: str,
    email: str | None,
    issuer: str,
    subject: str,
    actor: str = "operator",
) -> UUID:
    """Create a user linked to one external identity (operator path)."""
    user_id = uuid7()
    with conn.transaction():
        _set_context(
            conn, user_id=str(user_id), auth_issuer=issuer, auth_subject=subject, actor=actor
        )
        conn.execute(
            "insert into gba.users (id, display_name, email_normalized) values (%s, %s, %s)",
            (user_id, display_name, normalize_email(email) if email else None),
        )
        conn.execute(
            "insert into gba.user_identities (user_id, issuer, subject) values (%s, %s, %s)",
            (user_id, issuer, subject),
        )
    return user_id


def add_membership(
    conn: psycopg.Connection,
    *,
    tenant_id: UUID,
    user_id: UUID,
    role: str,
    location_id: UUID | None = None,
    actor: str = "operator",
) -> UUID:
    with owner_tenant_transaction(conn, tenant_id):
        _set_context(conn, actor=actor)
        row = conn.execute(
            "insert into gba.memberships (tenant_id, user_id, role, location_id) "
            "values (%s, %s, %s, %s) "
            "returning id",
            (tenant_id, user_id, role, location_id),
        ).fetchone()
    assert row is not None  # noqa: S101 - INSERT ... RETURNING always yields a row
    return UUID(str(row[0]))


def grant_platform_admin(conn: psycopg.Connection, *, user_id: UUID, granted_by: str) -> None:
    """Platform roles are granted owner-side only; the runtime role cannot write them."""
    with conn.transaction():
        _set_context(conn, user_id=str(user_id), actor=f"operator:{granted_by}")
        conn.execute(
            "insert into gba.platform_roles (user_id, role, granted_by) "
            "values (%s, 'platform_admin', %s)",
            (user_id, granted_by),
        )


def set_membership_status(
    conn: psycopg.Connection,
    *,
    tenant_id: UUID,
    membership_id: UUID,
    status: str,
    actor: str = "operator",
) -> None:
    with owner_tenant_transaction(conn, tenant_id):
        _set_context(conn, actor=actor)
        conn.execute(
            "update gba.memberships set status = %s where tenant_id = %s and id = %s",
            (status, tenant_id, membership_id),
        )


def set_user_status(
    conn: psycopg.Connection, *, user_id: UUID, status: str, actor: str = "operator"
) -> None:
    with conn.transaction():
        _set_context(conn, user_id=str(user_id), actor=actor)
        conn.execute(
            "update gba.users set status = %s, updated_at = now() where id = %s",
            (status, user_id),
        )
