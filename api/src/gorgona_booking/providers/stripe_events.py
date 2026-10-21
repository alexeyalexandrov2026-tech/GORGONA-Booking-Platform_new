"""Offline signature-first Stripe snapshot decoding; no route, storage or API client.

K6b: an event listed by the Stripe API is decoded by the same strict rules into the same facts;
only its digest (canonical JSON) and its attestation differ from a signed webhook.
"""

import hashlib
import json
import math
import re
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, JsonValue, SecretStr, ValidationError
from stripe import SignatureVerificationError, WebhookSignature

from gorgona_booking.errors import DomainError
from gorgona_booking.providers.stripe_contracts import (
    AccountId,
    ApiVersion,
    EventId,
    SignedStripeEvent,
    StripeCharge,
    StripeEventPolicy,
    StripeEventType,
    StripePaymentIntent,
    StripeRefund,
    StripeResource,
    UnixSecond,
)

MAX_BODY_BYTES = 262_144
# K6b: one `GET /v1/events` page of at most 100 events.
MAX_PAGE_BYTES = 8_388_608
MAX_PAGE_EVENTS = 100
MAX_SIGNATURE_BYTES = 4096
MAX_CLOCK_SKEW_SECONDS = 300
_MAX_SIGNATURES = 8
_TIMESTAMP = re.compile(r"^(0|[1-9][0-9]{0,11})$")
_HEADER_PART = re.compile(r"^[A-Za-z0-9_]+=[A-Za-z0-9]+$")
_SIGNATURE = re.compile(r"^[0-9a-f]{64}$")
_OBJECTS: dict[StripeEventType, Literal["payment_intent", "charge", "refund"]] = {
    "payment_intent.succeeded": "payment_intent",
    "payment_intent.payment_failed": "payment_intent",
    "payment_intent.processing": "payment_intent",
    "payment_intent.canceled": "payment_intent",
    "charge.succeeded": "charge",
    "charge.failed": "charge",
    "charge.pending": "charge",
    "charge.refunded": "charge",
    "refund.created": "refund",
    "refund.updated": "refund",
    "refund.failed": "refund",
}


# K6b: the reconciler asks only for the event types FIN-02 supports.
SUPPORTED_EVENT_TYPES: tuple[StripeEventType, ...] = tuple(_OBJECTS)


class ProviderEventRejectedError(DomainError):
    code = "PROVIDER_EVENT_REJECTED"


class ProviderEventConfigurationError(DomainError):
    code = "PROVIDER_EVENT_CONFIGURATION_INVALID"


class ProviderPageRejectedError(DomainError):
    """K6b: a page of listed events is not a bounded, well-formed Stripe list."""

    code = "PROVIDER_PAGE_REJECTED"


def _rejected(reason: str) -> ProviderEventRejectedError:
    return ProviderEventRejectedError("Provider event was refused", reason=reason)


class _Data(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    object: dict[str, JsonValue]


class _Event(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    object: Literal["event"]
    id: EventId
    account: AccountId
    api_version: ApiVersion
    livemode: bool
    created: UnixSecond
    type: StripeEventType
    data: _Data


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _nonfinite(value: str) -> None:
    raise ValueError("Non-finite JSON number")


def _finite_float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Non-finite JSON number")
    return result


def _timestamp(header: str) -> int:
    parts = header.split(",")
    if not all(_HEADER_PART.fullmatch(part) for part in parts):
        raise _rejected("signature")
    timestamps = [part[2:] for part in parts if part.startswith("t=")]
    signatures = [part[3:] for part in parts if part.startswith("v1=")]
    if (
        len(timestamps) != 1
        or not _TIMESTAMP.fullmatch(timestamps[0])
        or not 1 <= len(signatures) <= _MAX_SIGNATURES
        or not all(_SIGNATURE.fullmatch(value) for value in signatures)
    ):
        raise _rejected("signature")
    return int(timestamps[0])


def _resource(event: _Event) -> StripeResource:
    data = event.data.object
    expected = _OBJECTS[event.type]
    if data.get("object") != expected:
        raise ValueError("Mismatched event resource")
    # K5a finding 12: a charge moved only what was captured, never the authorized amount.
    fields: dict[str, object] = {
        "id": data["id"],
        "currency": data["currency"],
        "status": data["status"],
        "amount_minor": data["amount_captured" if expected == "charge" else "amount"],
    }
    if expected == "payment_intent":
        return StripePaymentIntent.model_validate(
            {**fields, "amount_received_minor": data["amount_received"]}
        )
    fields["payment_intent_id"] = data.get("payment_intent")
    if expected == "charge":
        return StripeCharge.model_validate(
            {
                **fields,
                "amount_refunded_minor": data["amount_refunded"],
                "paid": data["paid"],
                "captured": data["captured"],
                "refunded": data["refunded"],
            }
        )
    return StripeRefund.model_validate({**fields, "charge_id": data["charge"]})


def verify_stripe_event(
    payload: bytes,
    signature: str | None,
    *,
    policy: StripeEventPolicy,
    signing_keys: tuple[SecretStr, ...],
    now: datetime | None = None,
) -> SignedStripeEvent:
    """Verify bounded raw bytes, then decode selected test-mode snapshot facts.

    `policy`, keys and optional test clock are trusted caller dependencies, never
    values taken from a request. An ingress caller must independently establish
    verified admission and durable receipt before acknowledging anything. This
    function neither chooses a tenant nor establishes admission or payment state.
    """
    if not 1 <= len(signing_keys) <= 2 or any(
        not 16 <= len(key.get_secret_value()) <= 1024 for key in signing_keys
    ):
        raise ProviderEventConfigurationError("Provider verification is not configured")
    current = now if now is not None else datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ProviderEventConfigurationError("Provider verification needs an aware clock")
    if not isinstance(payload, bytes) or not 1 <= len(payload) <= MAX_BODY_BYTES:
        raise _rejected("body_budget")
    if not isinstance(signature, str) or not 1 <= len(signature) <= MAX_SIGNATURE_BYTES:
        raise _rejected("signature")
    timestamp = _timestamp(signature)
    if abs(int(current.timestamp()) - timestamp) > MAX_CLOCK_SKEW_SECONDS:
        raise _rejected("signature")
    for key in signing_keys:
        try:
            # The SDK verifies the unmodified body; our symmetric freshness check
            # above also refuses future timestamps (the SDK checks only old ones).
            valid = WebhookSignature.verify_header(
                payload, signature, key.get_secret_value(), tolerance=None
            )
        except SignatureVerificationError, UnicodeDecodeError:
            continue
        if valid:
            break
    else:
        raise _rejected("signature") from None
    try:
        value = _strict_json(payload)
    except ValueError, RecursionError:
        raise _rejected("event_shape") from None
    return _decode(value, policy, hashlib.sha256(payload).hexdigest())


def _strict_json(payload: bytes) -> object:
    """Duplicate keys and non-finite numbers are refused, as Stripe never sends them."""
    return json.loads(
        payload.decode("utf-8"),
        object_pairs_hook=_unique_object,
        parse_constant=_nonfinite,
        parse_float=_finite_float,
    )


def decode_event_page(payload: bytes) -> tuple[list[dict[str, object]], bool]:
    """K6b: the events of one bounded `GET /v1/events` page and whether more pages follow."""
    if not isinstance(payload, bytes) or not 1 <= len(payload) <= MAX_PAGE_BYTES:
        raise ProviderPageRejectedError("Provider page was refused", reason="page_budget")
    try:
        value = _strict_json(payload)
    except ValueError, RecursionError:
        raise ProviderPageRejectedError("Provider page was refused", reason="page_shape") from None
    if (
        not isinstance(value, dict)
        or value.get("object") != "list"
        or type(value.get("has_more")) is not bool
        or not isinstance(value.get("data"), list)
        or len(value["data"]) > MAX_PAGE_EVENTS
        or not all(isinstance(item, dict) for item in value["data"])
    ):
        raise ProviderPageRejectedError("Provider page was refused", reason="page_shape")
    return list(value["data"]), value["has_more"]


def retrieved_stripe_event(
    value: dict[str, object], *, policy: StripeEventPolicy, account: str
) -> SignedStripeEvent:
    """K6b: decode one listed event of `account` into the same facts as its webhook.

    The digest is the SHA-256 of the event's canonical JSON. The list API may leave out
    `account`; the request named it, and an `account` that is present must equal it.
    """
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    if len(canonical) > MAX_BODY_BYTES:
        raise _rejected("body_budget")
    if value.get("account", account) != account:
        raise _rejected("event_scope")
    return _decode({**value, "account": account}, policy, hashlib.sha256(canonical).hexdigest())


def _decode(value: object, policy: StripeEventPolicy, digest: str) -> SignedStripeEvent:
    try:
        event = _Event.model_validate(value)
    except ValueError, RecursionError:
        raise _rejected("event_shape") from None
    if event.account != policy.account_id or event.livemode:
        raise _rejected("event_scope")
    if event.api_version != policy.api_version:
        raise _rejected("event_version")
    if event.type not in _OBJECTS:
        raise _rejected("event_type")
    try:
        return SignedStripeEvent(
            namespace=policy.namespace,
            account_id=event.account,
            api_version=event.api_version,
            event_id=event.id,
            event_type=event.type,
            created=event.created,
            resource=_resource(event),
            delivery_sha256=digest,
        )
    except KeyError, ValueError, ValidationError:
        raise _rejected("event_shape") from None
