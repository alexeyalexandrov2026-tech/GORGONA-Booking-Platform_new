"""Synthetic signed deliveries prove a local parser, never Stripe admission."""

import copy
import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import SecretStr, ValidationError

from gorgona_booking.providers.stripe_contracts import (
    SignedStripeEvent,
    StripeCharge,
    StripeEventPolicy,
    StripePaymentIntent,
    StripeRefund,
)
from gorgona_booking.providers.stripe_events import (
    MAX_BODY_BYTES,
    MAX_SIGNATURE_BYTES,
    ProviderEventConfigurationError,
    ProviderEventRejectedError,
    verify_stripe_event,
)

NOW = 1_792_000_000
API_VERSION = "2026-09-30.endive"
ACCOUNT = "acct_FAKEmerchant1"


@pytest.fixture
def key() -> SecretStr:
    return SecretStr("whsec_" + secrets.token_urlsafe(32))


@pytest.fixture
def policy() -> StripeEventPolicy:
    return StripeEventPolicy(
        namespace="FAKE-sandbox-one", account_id=ACCOUNT, api_version=API_VERSION
    )


def event(kind: str = "payment_intent.succeeded") -> dict[str, Any]:
    resource: dict[str, Any] = {
        "object": "payment_intent",
        "id": "pi_FAKEpayment1",
        "amount": 1000,
        "amount_received": 1000,
        "currency": "usd",
        "status": "succeeded",
        "metadata": {"private": "FAKE private metadata"},
    }
    if kind.startswith("charge."):
        resource = {
            "object": "charge",
            "id": "ch_FAKEcharge1",
            "amount": 1000,
            "amount_captured": 1000,
            "amount_refunded": 500,
            "currency": "usd",
            "status": "succeeded",
            "paid": True,
            "captured": True,
            "refunded": False,
            "payment_intent": "pi_FAKEpayment1",
            "receipt_email": "fake@example.test",
        }
    if kind.startswith("refund."):
        resource = {
            "object": "refund",
            "id": "re_FAKErefund1",
            "amount": 500,
            "currency": "usd",
            "status": "succeeded",
            "charge": "ch_FAKEcharge1",
            "payment_intent": "pi_FAKEpayment1",
            "metadata": {"private": "FAKE note"},
        }
    return {
        "object": "event",
        "id": "evt_FAKEevent1",
        "account": ACCOUNT,
        "api_version": API_VERSION,
        "livemode": False,
        "created": NOW - 100_000,
        "type": kind,
        "pending_webhooks": 1,
        "request": {"id": "FAKE-request"},
        "data": {"object": resource},
    }


def body(value: Any) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode()


def signed(payload: bytes, key: SecretStr, timestamp: int = NOW) -> str:
    digest = hmac.new(
        key.get_secret_value().encode(),
        str(timestamp).encode() + b"." + payload,
        hashlib.sha256,
    ).hexdigest()
    return f"t={timestamp},v1={digest}"


def decode(
    payload: bytes, header: str | None, policy: StripeEventPolicy, keys: tuple[SecretStr, ...]
) -> SignedStripeEvent:
    return verify_stripe_event(
        payload,
        header,
        policy=policy,
        signing_keys=keys,
        now=datetime.fromtimestamp(NOW, UTC),
    )


@pytest.mark.parametrize(
    ("kind", "model"),
    [
        ("payment_intent.succeeded", StripePaymentIntent),
        ("payment_intent.payment_failed", StripePaymentIntent),
        ("payment_intent.processing", StripePaymentIntent),
        ("payment_intent.canceled", StripePaymentIntent),
        ("charge.succeeded", StripeCharge),
        ("charge.failed", StripeCharge),
        ("charge.pending", StripeCharge),
        ("charge.refunded", StripeCharge),
        ("refund.created", StripeRefund),
        ("refund.updated", StripeRefund),
        ("refund.failed", StripeRefund),
    ],
)
def test_decodes_selected_signed_snapshot_facts_without_private_fields(
    key: SecretStr,
    policy: StripeEventPolicy,
    kind: str,
    model: type[object],
) -> None:
    payload = body(event(kind))
    result = decode(payload, signed(payload, key), policy, (key,))
    assert result.verification == "signature_only"
    assert result.namespace == policy.namespace
    assert result.account_id == ACCOUNT
    assert result.livemode is False
    assert result.event_id == "evt_FAKEevent1"
    assert result.event_type == kind
    assert isinstance(result.resource, model)
    assert result.resource.amount_minor == (500 if kind.startswith("refund.") else 1000)
    assert result.delivery_sha256 == hashlib.sha256(payload).hexdigest()
    assert result.created == NOW - 100_000  # Old event creation is not a stale signature.
    serialized = result.model_dump_json()
    for omitted in (
        "private",
        "fake@example.test",
        "pending_webhooks",
        "FAKE-request",
        "business_id",
        "book_id",
    ):
        assert omitted not in serialized
    with pytest.raises(ValidationError):
        result.__setattr__("namespace", "other")


def test_delivery_bytes_are_distinct_from_normalized_event_facts(
    key: SecretStr,
    policy: StripeEventPolicy,
) -> None:
    first = event()
    second = copy.deepcopy(first)
    second["pending_webhooks"] = 0
    second["request"] = {"id": "FAKE-different-delivery"}
    second["data"]["object"]["metadata"] = {"other": "FAKE"}
    a, b = body(first), json.dumps(second, indent=2).encode()
    old = decode(a, signed(a, key), policy, (key,))
    new = decode(b, signed(b, key), policy, (key,))
    assert old.delivery_sha256 != new.delivery_sha256
    assert old.facts_sha256 == new.facts_sha256
    second["data"]["object"]["amount"] = 1001
    changed = body(second)
    assert decode(changed, signed(changed, key), policy, (key,)).facts_sha256 != old.facts_sha256


@pytest.mark.parametrize("offset", [-300, 0, 300])
def test_signature_timestamp_window_edges(
    key: SecretStr,
    policy: StripeEventPolicy,
    offset: int,
) -> None:
    payload = body(event())
    assert decode(payload, signed(payload, key, NOW + offset), policy, (key,))


@pytest.mark.parametrize("offset", [-301, 301, -86_400, 86_400])
def test_refuses_stale_and_future_signatures(
    key: SecretStr,
    policy: StripeEventPolicy,
    offset: int,
) -> None:
    payload = body(event())
    with pytest.raises(ProviderEventRejectedError):
        decode(payload, signed(payload, key, NOW + offset), policy, (key,))


def test_wrong_key_modified_body_and_multiple_rotation_signatures(
    key: SecretStr,
    policy: StripeEventPolicy,
) -> None:
    other = SecretStr("whsec_" + secrets.token_urlsafe(32))
    payload = body(event())
    header = signed(payload, key)
    with pytest.raises(ProviderEventRejectedError):
        decode(payload + b" ", header, policy, (key,))
    with pytest.raises(ProviderEventRejectedError):
        decode(payload, header, policy, (other,))
    assert decode(payload, header, policy, (other, key))
    combined = signed(payload, other) + "," + header.split(",", 1)[1]
    assert decode(payload, combined, policy, (key,))


@pytest.mark.parametrize(
    "header",
    [
        None,
        "",
        "v1=" + "0" * 64,
        "t=bad,v1=" + "0" * 64,
        f"t={NOW},v0=" + "0" * 64,
        f"t={NOW},v1=bad",
        f"t={NOW},t={NOW},v1=" + "0" * 64,
        f"t=0{NOW},v1=" + "0" * 64,
        f"t={NOW},v1=" + "0" * 64 + ",bad",
        f"t={NOW}, v1=" + "0" * 64,
        "t=9999999999999999999999,v1=" + "0" * 64,
    ],
)
def test_refuses_ambiguous_or_malformed_headers(
    key: SecretStr,
    policy: StripeEventPolicy,
    header: str | None,
) -> None:
    with pytest.raises(ProviderEventRejectedError):
        decode(body(event()), header, policy, (key,))


def test_enforces_byte_budgets_before_crypto(
    key: SecretStr,
    policy: StripeEventPolicy,
) -> None:
    for payload, header in (
        (b"x" * (MAX_BODY_BYTES + 1), "FAKE"),
        (body(event()), "x" * (MAX_SIGNATURE_BYTES + 1)),
    ):
        with pytest.raises(ProviderEventRejectedError):
            decode(payload, header, policy, (key,))


@pytest.mark.parametrize(
    "patch",
    [
        {"account": "acct_FAKEother"},
        {"account": None},
        {"account": ""},
        {"livemode": True},
        {"livemode": 0},
        {"livemode": "false"},
        {"api_version": "2020-01-01"},
        {"api_version": None},
        {"object": "other"},
        {"id": "pi_WRONGkind"},
        {"created": True},
        {"created": -1},
        {"created": 1.5},
        {"type": "customer.created"},
        {"type": "v1.billing.meter.error_report_triggered"},
    ],
)
def test_signed_does_not_mean_admitted_account_mode_or_version(
    key: SecretStr,
    policy: StripeEventPolicy,
    patch: dict[str, Any],
) -> None:
    payload = body({**event(), **patch})
    with pytest.raises(ProviderEventRejectedError):
        decode(payload, signed(payload, key), policy, (key,))


@pytest.mark.parametrize(
    ("kind", "patch"),
    [
        ("payment_intent.succeeded", {"amount": True}),
        ("payment_intent.succeeded", {"amount": "1000"}),
        ("payment_intent.succeeded", {"amount": 1.0}),
        ("payment_intent.succeeded", {"amount": -1}),
        ("payment_intent.succeeded", {"amount": 10**18}),
        ("payment_intent.succeeded", {"amount_received": False}),
        ("payment_intent.succeeded", {"currency": "USD"}),
        ("payment_intent.succeeded", {"status": "unknown"}),
        ("payment_intent.succeeded", {"id": "ch_WRONGkind"}),
        ("charge.refunded", {"object": "refund"}),
        ("charge.refunded", {"paid": 1}),
        ("charge.refunded", {"payment_intent": "FAKE"}),
        ("refund.updated", {"charge": None}),
        ("refund.updated", {"amount": -1}),
        ("refund.updated", {"status": "unknown"}),
    ],
)
def test_refuses_ambiguous_money_and_resource_contracts(
    key: SecretStr,
    policy: StripeEventPolicy,
    kind: str,
    patch: dict[str, Any],
) -> None:
    value = event(kind)
    value["data"]["object"].update(patch)
    payload = body(value)
    with pytest.raises(ProviderEventRejectedError):
        decode(payload, signed(payload, key), policy, (key,))


@pytest.mark.parametrize(
    "payload",
    [
        b"not-json",
        b"[]",
        b"null",
        b"{}",
        b'"event"',
        b"\xff",
        b'{"object":"event","object":"event"}',
        b'{"value":NaN}',
        b'{"value":Infinity}',
        b'{"value":-Infinity}',
        b"[" * 1100 + b"0" + b"]" * 1100,
    ],
)
def test_malformed_signed_payloads_have_sanitized_domain_errors(
    key: SecretStr,
    policy: StripeEventPolicy,
    payload: bytes,
) -> None:
    with pytest.raises(ProviderEventRejectedError) as caught:
        decode(payload, signed(payload, key), policy, (key,))
    assert str(caught.value) == "Provider event was refused"
    assert "payload" not in caught.value.details
    assert "signature" not in caught.value.details


def test_duplicate_nested_keys_and_missing_required_facts_are_refused(
    key: SecretStr,
    policy: StripeEventPolicy,
) -> None:
    payload = body(event()).replace(b'"amount":1000', b'"amount":1000,"amount":1000')
    with pytest.raises(ProviderEventRejectedError):
        decode(payload, signed(payload, key), policy, (key,))
    value = event()
    del value["data"]["object"]["amount_received"]
    payload = body(value)
    with pytest.raises(ProviderEventRejectedError):
        decode(payload, signed(payload, key), policy, (key,))


def test_a_charge_counts_only_its_captured_amount(
    key: SecretStr,
    policy: StripeEventPolicy,
) -> None:
    # K5a finding 12: a partial capture is the captured amount, never the authorized one.
    value = event("charge.succeeded")
    value["data"]["object"].update(amount=1000, amount_captured=600)
    payload = body(value)
    result = decode(payload, signed(payload, key), policy, (key,))
    assert isinstance(result.resource, StripeCharge)
    assert result.resource.amount_minor == 600
    for patch in ({"amount_captured": None}, {"amount_captured": "600"}, {"amount_captured": -1}):
        value = event("charge.succeeded")
        value["data"]["object"].update(patch)
        payload = body(value)
        with pytest.raises(ProviderEventRejectedError):
            decode(payload, signed(payload, key), policy, (key,))
    value = event("charge.succeeded")
    del value["data"]["object"]["amount_captured"]
    payload = body(value)
    with pytest.raises(ProviderEventRejectedError):
        decode(payload, signed(payload, key), policy, (key,))


def test_configuration_is_bounded_and_never_accepts_naive_clock(
    key: SecretStr,
    policy: StripeEventPolicy,
) -> None:
    payload = body(event())
    for keys in ((), (key, key, key), (SecretStr(""),)):
        with pytest.raises(ProviderEventConfigurationError):
            decode(payload, signed(payload, key), policy, keys)
    with pytest.raises(ProviderEventConfigurationError):
        verify_stripe_event(
            payload,
            signed(payload, key),
            policy=policy,
            signing_keys=(key,),
            now=datetime(2026, 10, 15),  # noqa: DTZ001 - intentional invalid clock
        )
    assert key.get_secret_value() not in repr(key)
    for patch in ({"account_id": "bad"}, {"namespace": ""}, {"api_version": "latest"}):
        with pytest.raises(ValidationError):
            StripeEventPolicy.model_validate({**policy.model_dump(), **patch})


@pytest.mark.parametrize("value", [0, "false", True])
def test_normalized_contract_requires_a_real_false_mode(
    key: SecretStr,
    policy: StripeEventPolicy,
    value: object,
) -> None:
    payload = body(event())
    normalized = decode(payload, signed(payload, key), policy, (key,)).model_dump()
    with pytest.raises(ValidationError):
        SignedStripeEvent.model_validate({**normalized, "livemode": value})


def test_normalized_contract_has_a_finite_event_type(
    key: SecretStr,
    policy: StripeEventPolicy,
) -> None:
    payload = body(event())
    normalized = decode(payload, signed(payload, key), policy, (key,)).model_dump()
    with pytest.raises(ValidationError):
        SignedStripeEvent.model_validate({**normalized, "event_type": "customer.created"})
    with pytest.raises(ValidationError):
        SignedStripeEvent.model_validate({**normalized, "event_type": "refund.created"})


def test_nonfinite_overflow_is_refused_even_in_an_ignored_field(
    key: SecretStr,
    policy: StripeEventPolicy,
) -> None:
    payload = body(event())[:-1] + b',"ignored":1e400}'
    with pytest.raises(ProviderEventRejectedError):
        decode(payload, signed(payload, key), policy, (key,))


def test_bad_signature_never_reaches_json_parsing(
    key: SecretStr,
    policy: StripeEventPolicy,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = body(event())

    def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("Unauthenticated bytes must not reach JSON parsing")

    monkeypatch.setattr(json, "loads", forbidden)
    with pytest.raises(ProviderEventRejectedError):
        decode(payload, f"t={NOW},v1=" + "0" * 64, policy, (key,))


def test_parser_never_opens_a_network_connection(
    key: SecretStr,
    policy: StripeEventPolicy,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import socket

    def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("Signature verification and decoding must stay offline")

    monkeypatch.setattr(socket, "socket", forbidden)
    payload = body(event())
    assert decode(payload, signed(payload, key), policy, (key,))


def test_exact_body_budget_and_unicode_bytes(
    key: SecretStr,
    policy: StripeEventPolicy,
) -> None:
    value = event()
    value["padding"] = ""
    value["data"]["object"]["metadata"] = {"note": "FAKE café"}
    empty = json.dumps(value, ensure_ascii=False).encode()
    value["padding"] = "x" * (MAX_BODY_BYTES - len(empty))
    payload = json.dumps(value, ensure_ascii=False).encode()
    assert len(payload) == MAX_BODY_BYTES
    result = decode(payload, signed(payload, key), policy, (key,))
    assert "café" not in result.model_dump_json()
    assert "padding" not in result.model_dump_json()


@pytest.mark.parametrize("amount", [0, 1, 999_999_999_999_999_999])
@pytest.mark.parametrize("currency", ["usd", "jpy", "kwd"])
def test_preserves_integer_units_without_currency_conversion_or_posting(
    key: SecretStr,
    policy: StripeEventPolicy,
    amount: int,
    currency: str,
) -> None:
    value = event()
    value["data"]["object"].update(amount=amount, amount_received=amount, currency=currency)
    payload = body(value)
    result = decode(payload, signed(payload, key), policy, (key,))
    assert result.resource.amount_minor == amount
    assert result.resource.currency == currency


@pytest.mark.parametrize("encoding", ["utf-16-le", "utf-16-be", "utf-32-le", "utf-32-be"])
def test_signed_json_must_use_utf8(
    key: SecretStr,
    policy: StripeEventPolicy,
    encoding: str,
) -> None:
    payload = json.dumps(event()).encode(encoding)
    with pytest.raises(ProviderEventRejectedError):
        decode(payload, signed(payload, key), policy, (key,))
