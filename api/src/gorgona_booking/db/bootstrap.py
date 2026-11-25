"""Cluster bootstrap, run once per environment with a superuser DSN.

Creates the NOLOGIN runtime, receipt writer and receipt worker groups, the owner
(migration) login role, the runtime login role, optional writer and worker logins and
the database. It is idempotent and refuses to touch a role that
is a superuser. Passwords are sent pre-hashed (SCRAM), never in clear text.
"""

import re
from dataclasses import dataclass, field

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

RUNTIME_GROUP = "gba_runtime"
RECEIPT_WRITER_GROUP = "gba_receipt_writer"
RECEIPT_WORKER_GROUP = "gba_receipt_worker"
_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
_SAFE_ATTRIBUTES = sql.SQL("NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS")
# Managed PG16+/18 admin roles (Cloud SQL cloudsqlsuperuser, Azure azure_pg_admin) are not
# true SUPERUSERs: PG rejects ALTER ROLE ... NOSUPERUSER when the caller lacks SUPERUSER,
# even on non-superuser targets. We already verify target rolsuper is False before altering.
_MANAGED_ALTER_ATTRIBUTES = sql.SQL("NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS")


class BootstrapError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class BootstrapSpec:
    database: str
    owner_role: str
    owner_password: str = field(repr=False)
    app_role: str
    app_password: str = field(repr=False)
    receipt_writer_role: str | None = None
    receipt_writer_password: str | None = field(default=None, repr=False)
    receipt_worker_role: str | None = None
    receipt_worker_password: str | None = field(default=None, repr=False)

    def validate(self) -> None:
        if (self.receipt_writer_role is None) != (self.receipt_writer_password is None):
            raise BootstrapError("receipt writer role and password must be supplied together")
        if (self.receipt_worker_role is None) != (self.receipt_worker_password is None):
            raise BootstrapError("receipt worker role and password must be supplied together")
        logins = tuple(
            role
            for role in (self.receipt_writer_role, self.receipt_worker_role)
            if role is not None
        )
        for name in (self.database, self.owner_role, self.app_role, *logins):
            if not _IDENTIFIER.fullmatch(name):
                raise BootstrapError(f"invalid identifier: {name!r}")
        roles = (
            self.owner_role,
            self.app_role,
            RUNTIME_GROUP,
            RECEIPT_WRITER_GROUP,
            RECEIPT_WORKER_GROUP,
            *logins,
        )
        if len(set(roles)) != len(roles):
            raise BootstrapError(
                "owner, runtime, receipt writer, worker and groups must all differ"
            )
        passwords = [
            password
            for password in (
                self.owner_password,
                self.app_password,
                self.receipt_writer_password,
                self.receipt_worker_password,
            )
            if password is not None
        ]
        if min(len(password) for password in passwords) < 12:
            raise BootstrapError("role passwords must be at least 12 characters")
        # A shared password would let one credential holder log in as another role.
        if len(set(passwords)) != len(passwords):
            raise BootstrapError(
                "owner, runtime, receipt writer and receipt worker passwords must all differ"
            )


def bootstrap(admin_conninfo: str, spec: BootstrapSpec) -> None:
    spec.validate()
    with psycopg.connect(admin_conninfo, autocommit=True) as conn:
        caller_row = conn.execute(
            "select current_user, rolsuper from pg_catalog.pg_roles where rolname = current_user"
        ).fetchone()
        admin_user = str(caller_row[0]) if caller_row is not None else ""
        caller_is_superuser = bool(caller_row and caller_row[1])

        _ensure_role(conn, RUNTIME_GROUP, password=None, caller_is_superuser=caller_is_superuser)
        _ensure_role(
            conn, RECEIPT_WRITER_GROUP, password=None, caller_is_superuser=caller_is_superuser
        )
        _ensure_role(
            conn, RECEIPT_WORKER_GROUP, password=None, caller_is_superuser=caller_is_superuser
        )
        _ensure_role(
            conn,
            spec.owner_role,
            password=spec.owner_password,
            caller_is_superuser=caller_is_superuser,
        )
        _ensure_role(
            conn,
            spec.app_role,
            password=spec.app_password,
            caller_is_superuser=caller_is_superuser,
        )
        if spec.receipt_writer_role is not None:
            _ensure_role(
                conn,
                spec.receipt_writer_role,
                password=spec.receipt_writer_password,
                caller_is_superuser=caller_is_superuser,
            )
            conn.execute(
                sql.SQL("grant {} to {}").format(
                    sql.Identifier(RECEIPT_WRITER_GROUP), sql.Identifier(spec.receipt_writer_role)
                )
            )
        if spec.receipt_worker_role is not None:
            _ensure_role(
                conn,
                spec.receipt_worker_role,
                password=spec.receipt_worker_password,
                caller_is_superuser=caller_is_superuser,
            )
            conn.execute(
                sql.SQL("grant {} to {}").format(
                    sql.Identifier(RECEIPT_WORKER_GROUP), sql.Identifier(spec.receipt_worker_role)
                )
            )
        conn.execute(
            sql.SQL("grant {} to {}").format(
                sql.Identifier(RUNTIME_GROUP), sql.Identifier(spec.app_role)
            )
        )
        groups = (RUNTIME_GROUP, RECEIPT_WRITER_GROUP, RECEIPT_WORKER_GROUP)
        forbidden = [
            (spec.app_role, spec.owner_role),
            *((spec.owner_role, group) for group in groups),
            (spec.app_role, RECEIPT_WRITER_GROUP),
            (spec.app_role, RECEIPT_WORKER_GROUP),
            *((one, other) for one in groups for other in groups if one != other),
        ]
        if spec.receipt_writer_role is not None:
            forbidden += [
                (spec.receipt_writer_role, spec.owner_role),
                (spec.receipt_writer_role, RUNTIME_GROUP),
                (spec.receipt_writer_role, RECEIPT_WORKER_GROUP),
            ]
        if spec.receipt_worker_role is not None:
            forbidden += [
                (spec.receipt_worker_role, spec.owner_role),
                (spec.receipt_worker_role, RUNTIME_GROUP),
                (spec.receipt_worker_role, RECEIPT_WRITER_GROUP),
            ]
        for member, role in forbidden:
            if _is_member(conn, member, role):
                raise BootstrapError(f"{member} must not be a member of {role}")

        owner = conn.execute(
            "select pg_catalog.pg_get_userbyid(datdba) from pg_catalog.pg_database "
            "where datname = %s",
            (spec.database,),
        ).fetchone()
        if owner is None:
            # On managed PG16+/18 (Cloud SQL cloudsqlsuperuser / Azure), CREATEROLE grants
            # ADMIN without SET ROLE by default; grant membership so CREATE DATABASE OWNER works.
            if not caller_is_superuser and admin_user and admin_user != spec.owner_role:
                conn.execute(
                    sql.SQL("grant {} to {}").format(
                        sql.Identifier(spec.owner_role), sql.Identifier(admin_user)
                    )
                )
            conn.execute(
                sql.SQL("create database {} owner {} encoding 'UTF8' template template0").format(
                    sql.Identifier(spec.database), sql.Identifier(spec.owner_role)
                )
            )
        elif owner[0] != spec.owner_role:
            raise BootstrapError(f"database {spec.database} is owned by {owner[0]}, not the owner")
        if admin_user and admin_user != spec.owner_role:
            conn.execute(
                sql.SQL("grant connect on database {} to {}").format(
                    sql.Identifier(spec.database), sql.Identifier(admin_user)
                )
            )
        target_dsn = make_conninfo(admin_conninfo, dbname=spec.database)
        with psycopg.connect(target_dsn, autocommit=True) as db_conn:
            # On Azure PostgreSQL 18 Flexible Server, template0's public schema is owned by
            # azuresu/azure_pg_admin rather than pg_database_owner, so the non-superuser owner
            # role needs explicit schema privileges to create public.gba_schema_migrations.
            db_conn.execute(
                sql.SQL("grant usage, create on schema public to {}").format(
                    sql.Identifier(spec.owner_role)
                )
            )
            db_conn.execute("create extension if not exists btree_gist")
        conn.execute(
            sql.SQL("revoke all on database {} from public").format(sql.Identifier(spec.database))
        )
        if admin_user and admin_user != spec.owner_role:
            conn.execute(
                sql.SQL("revoke connect on database {} from {}").format(
                    sql.Identifier(spec.database), sql.Identifier(admin_user)
                )
            )
        conn.execute(
            sql.SQL("grant connect on database {} to {}").format(
                sql.Identifier(spec.database), sql.Identifier(RUNTIME_GROUP)
            )
        )
        for login in (spec.receipt_writer_role, spec.receipt_worker_role):
            if login is not None:
                conn.execute(
                    sql.SQL("grant connect on database {} to {}").format(
                        sql.Identifier(spec.database), sql.Identifier(login)
                    )
                )


def _ensure_role(
    conn: psycopg.Connection,
    name: str,
    password: str | None,
    *,
    caller_is_superuser: bool = True,
) -> None:
    row = conn.execute(
        "select rolsuper from pg_catalog.pg_roles where rolname = %s", (name,)
    ).fetchone()
    if row is not None and row[0]:
        raise BootstrapError(f"role {name} is a superuser; refusing to reuse or alter it")

    exists = row is not None
    attributes = (
        _MANAGED_ALTER_ATTRIBUTES if (exists and not caller_is_superuser) else _SAFE_ATTRIBUTES
    )
    statement = sql.SQL("{} role {} {} {}").format(
        sql.SQL("alter" if exists else "create"),
        sql.Identifier(name),
        sql.SQL("LOGIN" if password is not None else "NOLOGIN"),
        attributes,
    )
    if password is not None:
        hashed = conn.pgconn.encrypt_password(
            password.encode("utf-8"), name.encode("utf-8"), b"scram-sha-256"
        )
        statement = sql.SQL("{} password {}").format(statement, sql.Literal(hashed.decode()))
    conn.execute(statement)


def _is_member(conn: psycopg.Connection, member: str, role: str) -> bool:
    row = conn.execute("select pg_catalog.pg_has_role(%s, %s, 'MEMBER')", (member, role)).fetchone()
    return bool(row and row[0])
