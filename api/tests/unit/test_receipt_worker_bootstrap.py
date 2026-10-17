"""K2a: the receipt worker login is explicit, disjoint from every other role and safe to show."""

from dataclasses import replace
from typing import TypedDict

import pytest

from gorgona_booking.db import cli
from gorgona_booking.db.bootstrap import (
    RECEIPT_WORKER_GROUP,
    BootstrapError,
    BootstrapSpec,
    bootstrap,
)

# Nothing listens on port 1: a connection attempt would fail with a psycopg error instead.
UNREACHABLE = "postgresql://gba_nobody@127.0.0.1:1/postgres?connect_timeout=1"
SHARED = "FAKE-shared-password"


class Overrides(TypedDict, total=False):
    owner_role: str
    app_role: str
    receipt_writer_role: str | None
    receipt_worker_role: str | None
    receipt_worker_password: str | None


def spec() -> BootstrapSpec:
    return BootstrapSpec(
        database="gba_test",
        owner_role="gba_owner",
        owner_password="FAKE-owner-password",
        app_role="gba_app",
        app_password="FAKE-app-password",
        receipt_writer_role="gba_writer",
        receipt_writer_password="FAKE-writer-password",
        receipt_worker_role="gba_worker",
        receipt_worker_password="FAKE-worker-password",
    )


def test_worker_group_name_and_password_are_never_shown() -> None:
    assert RECEIPT_WORKER_GROUP == "gba_receipt_worker"
    value = spec()
    assert value.receipt_worker_password is not None
    assert value.receipt_worker_password not in repr(value)


@pytest.mark.parametrize(
    "overrides",
    [
        {"receipt_worker_role": None},
        {"receipt_worker_password": None},
        {"receipt_worker_role": "gba_receipt_worker"},
        {"receipt_worker_role": "gba_writer"},
        {"receipt_worker_role": "gba_app"},
        {"receipt_worker_role": "gba_runtime"},
        {"owner_role": "gba_receipt_worker"},
        {"app_role": "gba_receipt_worker"},
        {"receipt_writer_role": "gba_receipt_worker"},
        {"receipt_worker_password": "short"},
        {"receipt_worker_role": "Bad-Name"},
    ],
)
def test_invalid_worker_configuration_is_refused(overrides: Overrides) -> None:
    with pytest.raises(BootstrapError):
        replace(spec(), **overrides).validate()


def test_existing_bootstrap_callers_do_not_create_a_worker_login() -> None:
    value = replace(spec(), receipt_worker_role=None, receipt_worker_password=None)
    value.validate()
    assert value.receipt_worker_role is None


@pytest.mark.parametrize(
    "fields",
    [
        ("owner_password", "receipt_worker_password"),
        ("app_password", "receipt_worker_password"),
        ("receipt_writer_password", "receipt_worker_password"),
    ],
)
def test_worker_password_equal_to_another_is_refused_before_any_connection(
    fields: tuple[str, str],
) -> None:
    value = replace(spec(), **dict.fromkeys(fields, SHARED))
    with pytest.raises(BootstrapError, match="differ") as refused:
        bootstrap(UNREACHABLE, value)
    assert SHARED not in str(refused.value)


@pytest.mark.parametrize(
    "worker",
    [
        {"GBA_RECEIPT_WORKER_ROLE": "gba_worker"},
        {"GBA_RECEIPT_WORKER_PASSWORD": "FAKE-worker-password"},
    ],
)
def test_cli_needs_both_worker_variables(
    monkeypatch: pytest.MonkeyPatch, worker: dict[str, str]
) -> None:
    for name, value in {
        "GBA_ADMIN_DATABASE_URL": UNREACHABLE,
        "GBA_OWNER_PASSWORD": "FAKE-owner-password",
        "GBA_APP_PASSWORD": "FAKE-app-password",
        **worker,
    }.items():
        monkeypatch.setenv(name, value)
    for name in {
        "GBA_RECEIPT_WORKER_ROLE",
        "GBA_RECEIPT_WORKER_PASSWORD",
        "GBA_RECEIPT_WRITER_ROLE",
        "GBA_RECEIPT_WRITER_PASSWORD",
    } - set(worker):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(BootstrapError, match="together"):
        cli.main(["bootstrap"])
