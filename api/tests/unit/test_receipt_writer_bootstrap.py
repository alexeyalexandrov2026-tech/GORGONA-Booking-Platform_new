"""Writer configuration is explicit, disjoint and safe to represent in diagnostics."""

from dataclasses import replace
from typing import TypedDict

import pytest

from gorgona_booking.db import cli
from gorgona_booking.db.bootstrap import BootstrapError, BootstrapSpec, bootstrap


class Overrides(TypedDict, total=False):
    owner_role: str
    receipt_writer_role: str | None
    receipt_writer_password: str | None


def spec() -> BootstrapSpec:
    return BootstrapSpec(
        database="gba_test",
        owner_role="gba_owner",
        owner_password="FAKE-owner-password",
        app_role="gba_app",
        app_password="FAKE-app-password",
        receipt_writer_role="gba_writer",
        receipt_writer_password="FAKE-writer-password",
    )


def test_role_passwords_are_never_in_bootstrap_representation() -> None:
    value = spec()
    shown = repr(value)
    assert value.owner_password not in shown
    assert value.app_password not in shown
    assert value.receipt_writer_password is not None
    assert value.receipt_writer_password not in shown


@pytest.mark.parametrize(
    "overrides",
    [
        {"receipt_writer_role": None},
        {"receipt_writer_password": None},
        {"receipt_writer_role": "gba_runtime"},
        {"owner_role": "gba_receipt_writer"},
        {"receipt_writer_role": "gba_app"},
        {"receipt_writer_password": "short"},
    ],
)
def test_invalid_writer_configuration_is_refused(overrides: Overrides) -> None:
    with pytest.raises(BootstrapError):
        replace(spec(), **overrides).validate()


def test_existing_bootstrap_callers_do_not_create_a_writer_login() -> None:
    value = replace(spec(), receipt_writer_role=None, receipt_writer_password=None)
    value.validate()
    assert value.receipt_writer_role is None


# K1f / IR-06 ------------------------------------------------------------------

# Nothing listens on port 1: a connection attempt would fail with a psycopg error instead.
UNREACHABLE = "postgresql://gba_nobody@127.0.0.1:1/postgres?connect_timeout=1"
SHARED = "FAKE-shared-password"


@pytest.mark.parametrize(
    "fields",
    [
        ("owner_password", "app_password"),
        ("owner_password", "receipt_writer_password"),
        ("app_password", "receipt_writer_password"),
    ],
)
def test_equal_role_passwords_are_refused_before_any_connection(fields: tuple[str, str]) -> None:
    value = replace(spec(), **dict.fromkeys(fields, SHARED))
    with pytest.raises(BootstrapError, match="differ") as refused:
        bootstrap(UNREACHABLE, value)
    assert SHARED not in str(refused.value)


@pytest.mark.parametrize(
    "writer",
    [
        {"GBA_RECEIPT_WRITER_ROLE": "gba_writer"},
        {"GBA_RECEIPT_WRITER_PASSWORD": "FAKE-writer-password"},
    ],
)
def test_cli_needs_both_writer_variables(
    monkeypatch: pytest.MonkeyPatch, writer: dict[str, str]
) -> None:
    for name, value in {
        "GBA_ADMIN_DATABASE_URL": UNREACHABLE,
        "GBA_OWNER_PASSWORD": "FAKE-owner-password",
        "GBA_APP_PASSWORD": "FAKE-app-password",
        **writer,
    }.items():
        monkeypatch.setenv(name, value)
    for name in {"GBA_RECEIPT_WRITER_ROLE", "GBA_RECEIPT_WRITER_PASSWORD"} - set(writer):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(BootstrapError, match="together"):
        cli.main(["bootstrap"])
