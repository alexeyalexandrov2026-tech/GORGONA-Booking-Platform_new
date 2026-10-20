"""K0b (E-02): process settings of the receipt ingress and worker; no database, no network.

Every secret here is generated in memory and must never appear in an error, repr or log.
"""

import secrets

import pytest

from gorgona_booking.providers.receipt_processes import (
    DEFAULT_PORT,
    ReceiptProcessError,
    ingress_settings,
    load_key_store,
    worker_settings,
)

WRITER_URL = "postgresql://gba_fake_writer:FAKE-password@127.0.0.1:5432/gba"
WORKER_URL = "postgresql://gba_fake_worker:FAKE-password@127.0.0.1:5432/gba"


def secret() -> str:
    return "whsec_" + secrets.token_urlsafe(32)


def test_named_environment_secrets_load_without_showing_their_values() -> None:
    first, second = secret(), secret()
    store = load_key_store(
        {
            "GBA_RECEIPT_SECRET_REFS": "env:GBA_STRIPE_TEST_WEBHOOK_SECRET, env:GBA_OLD_SECRET",
            "GBA_STRIPE_TEST_WEBHOOK_SECRET": first,
            "GBA_OLD_SECRET": second,
        }
    )
    assert set(store) == {"env:GBA_STRIPE_TEST_WEBHOOK_SECRET", "env:GBA_OLD_SECRET"}
    assert store["env:GBA_STRIPE_TEST_WEBHOOK_SECRET"].get_secret_value() == first
    assert first not in repr(store)
    assert second not in repr(store)


@pytest.mark.parametrize(
    ("refs", "environment"),
    [
        (None, {}),
        ("", {}),
        (" , ", {}),
        ("env:GBA_A,env:GBA_A", {"GBA_A": "x"}),
        ("kv:stripe-webhook", {}),
        ("env:lower_case", {"lower_case": "x"}),
        ("env:GBA_MISSING", {}),
        ("env:GBA_BLANK", {"GBA_BLANK": "   "}),
        ("env:GBA_GOOD,env:GBA_MISSING", {"GBA_GOOD": "SECRET-VALUE"}),
    ],
)
def test_a_missing_or_unsupported_secret_stops_the_process(
    refs: str | None, environment: dict[str, str]
) -> None:
    values = dict(environment)
    if refs is not None:
        values["GBA_RECEIPT_SECRET_REFS"] = refs
    with pytest.raises(ReceiptProcessError) as refused:
        load_key_store(values)
    assert "SECRET-VALUE" not in str(refused.value)


def test_ingress_settings_bind_loopback_only_and_hide_the_database_url() -> None:
    value = secret()
    settings = ingress_settings(
        {
            "GBA_RECEIPT_WRITER_DATABASE_URL": WRITER_URL,
            "GBA_RECEIPT_SECRET_REFS": "env:GBA_STRIPE_TEST_WEBHOOK_SECRET",
            "GBA_STRIPE_TEST_WEBHOOK_SECRET": value,
        }
    )
    assert settings.port == DEFAULT_PORT == 8787
    assert settings.host == "127.0.0.1"
    assert settings.database_url.get_secret_value() == WRITER_URL
    shown = repr(settings) + str(settings)
    assert "FAKE-password" not in shown
    assert value not in shown


@pytest.mark.parametrize(
    "changes",
    [
        {"GBA_RECEIPT_HOST": "0.0.0.0"},  # noqa: S104 - the refusal under test
        {"GBA_RECEIPT_HOST": "localhost"},
        {"GBA_RECEIPT_PORT": "70000"},
        {"GBA_RECEIPT_PORT": "-1"},
        {"GBA_RECEIPT_PORT": "eighty"},
        {"GBA_RECEIPT_WRITER_DATABASE_URL": ""},
    ],
)
def test_ingress_settings_refuse_other_hosts_ports_and_a_missing_database(
    changes: dict[str, str],
) -> None:
    values = {
        "GBA_RECEIPT_WRITER_DATABASE_URL": WRITER_URL,
        "GBA_RECEIPT_SECRET_REFS": "env:GBA_STRIPE_TEST_WEBHOOK_SECRET",
        "GBA_STRIPE_TEST_WEBHOOK_SECRET": secret(),
        **changes,
    }
    with pytest.raises(ReceiptProcessError) as refused:
        ingress_settings(values)
    assert "FAKE-password" not in str(refused.value)


def test_worker_settings_default_to_a_five_second_loop() -> None:
    settings = worker_settings({"GBA_RECEIPT_WORKER_DATABASE_URL": WORKER_URL}, [])
    assert (settings.interval, settings.once) == (5.0, False)
    once = worker_settings({"GBA_RECEIPT_WORKER_DATABASE_URL": WORKER_URL}, ["--once"])
    assert once.once is True
    assert "FAKE-password" not in repr(settings) + str(settings)


@pytest.mark.parametrize(
    "argv", [["--interval", "0"], ["--interval", "301"], ["--interval", "soon"], ["--loud"]]
)
def test_worker_settings_refuse_unbounded_intervals_and_unknown_flags(argv: list[str]) -> None:
    with pytest.raises(ReceiptProcessError):
        worker_settings({"GBA_RECEIPT_WORKER_DATABASE_URL": WORKER_URL}, argv)


def test_worker_settings_need_their_database() -> None:
    with pytest.raises(ReceiptProcessError):
        worker_settings({}, [])
