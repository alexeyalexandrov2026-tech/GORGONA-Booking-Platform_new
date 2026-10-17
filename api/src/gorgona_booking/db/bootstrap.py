"""Cluster bootstrap, run once per environment with a superuser DSN.

Creates the NOLOGIN runtime group, the owner (migration) login role, the runtime
login role and the database. It is idempotent and refuses to touch a role that
is a superuser. Passwords are sent pre-hashed (SCRAM), never in clear text.
"""

import re
from dataclasses import dataclass, field

import psycopg
from psycopg import sql

RUNTIME_GROUP = "gba_runtime"
RECEIPT_WRITER_GROUP = "gba_receipt_writer"
_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
_SAFE_ATTRIBUTES = sql.SQL("NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS")


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

    def validate(self) -> None:
        if (self.receipt_writer_role is None) != (self.receipt_writer_password is None):
            raise BootstrapError("receipt writer role and password must be supplied together")
        writer = (self.receipt_writer_role,) if self.receipt_writer_role is not None else ()
        for name in (self.database, self.owner_role, self.app_role, *writer):
            if not _IDENTIFIER.fullmatch(name):
                raise BootstrapError(f"invalid identifier: {name!r}")
        roles = (self.owner_role, self.app_role, RUNTIME_GROUP, RECEIPT_WRITER_GROUP, *writer)
        if len(set(roles)) != len(roles):
            raise BootstrapError("owner, runtime, receipt writer and groups must all differ")
        if min(len(self.owner_password), len(self.app_password)) < 12:
            raise BootstrapError("role passwords must be at least 12 characters")
        if self.receipt_writer_password is not None and len(self.receipt_writer_password) < 12:
            raise BootstrapError("receipt writer password must be at least 12 characters")
        # A shared password would let one credential holder log in as another role.
        passwords = [self.owner_password, self.app_password]
        if self.receipt_writer_password is not None:
            passwords.append(self.receipt_writer_password)
        if len(set(passwords)) != len(passwords):
            raise BootstrapError("owner, runtime and receipt writer passwords must all differ")


def bootstrap(admin_conninfo: str, spec: BootstrapSpec) -> None:
    spec.validate()
    with psycopg.connect(admin_conninfo, autocommit=True) as conn:
        _ensure_role(conn, RUNTIME_GROUP, password=None)
        _ensure_role(conn, RECEIPT_WRITER_GROUP, password=None)
        _ensure_role(conn, spec.owner_role, password=spec.owner_password)
        _ensure_role(conn, spec.app_role, password=spec.app_password)
        if spec.receipt_writer_role is not None:
            _ensure_role(conn, spec.receipt_writer_role, password=spec.receipt_writer_password)
            conn.execute(
                sql.SQL("grant {} to {}").format(
                    sql.Identifier(RECEIPT_WRITER_GROUP), sql.Identifier(spec.receipt_writer_role)
                )
            )
        conn.execute(
            sql.SQL("grant {} to {}").format(
                sql.Identifier(RUNTIME_GROUP), sql.Identifier(spec.app_role)
            )
        )
        forbidden = [
            (spec.app_role, spec.owner_role),
            (spec.owner_role, RUNTIME_GROUP),
            (spec.owner_role, RECEIPT_WRITER_GROUP),
            (spec.app_role, RECEIPT_WRITER_GROUP),
            (RUNTIME_GROUP, RECEIPT_WRITER_GROUP),
            (RECEIPT_WRITER_GROUP, RUNTIME_GROUP),
        ]
        if spec.receipt_writer_role is not None:
            forbidden += [
                (spec.receipt_writer_role, spec.owner_role),
                (spec.receipt_writer_role, RUNTIME_GROUP),
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
            conn.execute(
                sql.SQL("create database {} owner {} encoding 'UTF8' template template0").format(
                    sql.Identifier(spec.database), sql.Identifier(spec.owner_role)
                )
            )
        elif owner[0] != spec.owner_role:
            raise BootstrapError(f"database {spec.database} is owned by {owner[0]}, not the owner")
        conn.execute(
            sql.SQL("revoke all on database {} from public").format(sql.Identifier(spec.database))
        )
        conn.execute(
            sql.SQL("grant connect on database {} to {}").format(
                sql.Identifier(spec.database), sql.Identifier(RUNTIME_GROUP)
            )
        )
        if spec.receipt_writer_role is not None:
            conn.execute(
                sql.SQL("grant connect on database {} to {}").format(
                    sql.Identifier(spec.database), sql.Identifier(spec.receipt_writer_role)
                )
            )


def _ensure_role(conn: psycopg.Connection, name: str, password: str | None) -> None:
    row = conn.execute(
        "select rolsuper from pg_catalog.pg_roles where rolname = %s", (name,)
    ).fetchone()
    if row is not None and row[0]:
        raise BootstrapError(f"role {name} is a superuser; refusing to reuse or alter it")

    statement = sql.SQL("{} role {} {} {}").format(
        sql.SQL("alter" if row is not None else "create"),
        sql.Identifier(name),
        sql.SQL("LOGIN" if password is not None else "NOLOGIN"),
        _SAFE_ATTRIBUTES,
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
