"""Unit tests for Cloud SQL / managed PG18 non-superuser bootstrap compatibility."""

from __future__ import annotations

from typing import Any

import pytest

from gorgona_booking.db.bootstrap import BootstrapError, _ensure_role


class _FakePgConn:
    def encrypt_password(self, password: bytes, user: bytes, algorithm: bytes) -> bytes:
        return b"SCRAM-SHA-256$4096:fake$hash"


class _FakeResult:
    def __init__(self, row: tuple[Any, ...] | None) -> None:
        self._row = row

    def fetchone(self) -> tuple[Any, ...] | None:
        return self._row


class _FakeConn:
    def __init__(self, existing_row: tuple[Any, ...] | None) -> None:
        self._existing_row = existing_row
        self.pgconn = _FakePgConn()
        self.executed: list[str] = []

    def execute(self, statement: Any, params: Any = None) -> _FakeResult:
        if isinstance(statement, str):
            self.executed.append(statement)
            return _FakeResult(self._existing_row)
        rendered = statement.as_string(None)
        self.executed.append(rendered)
        return _FakeResult(None)


def test_ensure_role_alter_omits_nosuperuser_for_managed_non_superuser_admin() -> None:
    conn = _FakeConn(existing_row=(False,))
    _ensure_role(conn, "gba_runtime", password=None, caller_is_superuser=False)  # type: ignore[arg-type]
    ddl = conn.executed[-1]
    assert ddl.startswith('alter role "gba_runtime" NOLOGIN')
    assert "NOSUPERUSER" not in ddl
    assert "NOBYPASSRLS" in ddl


def test_ensure_role_create_keeps_nosuperuser_even_for_managed_admin() -> None:
    conn = _FakeConn(existing_row=None)
    _ensure_role(conn, "gba_runtime", password=None, caller_is_superuser=False)  # type: ignore[arg-type]
    ddl = conn.executed[-1]
    assert ddl.startswith('create role "gba_runtime" NOLOGIN')
    assert "NOSUPERUSER" in ddl
    assert "NOBYPASSRLS" in ddl


def test_ensure_role_alter_keeps_nosuperuser_for_true_superuser() -> None:
    conn = _FakeConn(existing_row=(False,))
    _ensure_role(conn, "gba_owner", password="FAKE-owner-password-123", caller_is_superuser=True)  # type: ignore[arg-type]
    ddl = conn.executed[-1]
    assert "NOSUPERUSER" in ddl
    assert "SCRAM-SHA-256" in ddl


def test_ensure_role_refuses_superuser_target_even_for_managed_admin() -> None:
    conn = _FakeConn(existing_row=(True,))
    with pytest.raises(BootstrapError, match="superuser"):
        _ensure_role(conn, "postgres", password=None, caller_is_superuser=False)  # type: ignore[arg-type]
