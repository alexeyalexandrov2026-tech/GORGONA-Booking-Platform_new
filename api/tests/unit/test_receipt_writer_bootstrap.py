"""Writer configuration is explicit, disjoint and safe to represent in diagnostics."""

from dataclasses import replace
from typing import TypedDict

import pytest

from gorgona_booking.db.bootstrap import BootstrapError, BootstrapSpec


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
