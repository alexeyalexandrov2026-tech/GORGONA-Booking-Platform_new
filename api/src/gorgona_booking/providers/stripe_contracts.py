"""Versioned, minimal snapshot facts. A valid signature is not payment admission."""

import hashlib
import json
from typing import Annotated, Literal, Self

from pydantic import Field, StrictInt, field_validator, model_validator

from gorgona_booking.business.contracts import Strict, Versioned

type Namespace = Annotated[str, Field(strict=True, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$")]
type AccountId = Annotated[str, Field(strict=True, pattern=r"^acct_[A-Za-z0-9]{1,100}$")]
type IntentId = Annotated[str, Field(strict=True, pattern=r"^pi_[A-Za-z0-9]{1,100}$")]
type ChargeId = Annotated[str, Field(strict=True, pattern=r"^ch_[A-Za-z0-9]{1,100}$")]
type RefundId = Annotated[str, Field(strict=True, pattern=r"^re_[A-Za-z0-9]{1,100}$")]
type EventId = Annotated[str, Field(strict=True, pattern=r"^evt_[A-Za-z0-9]{1,100}$")]
type ApiVersion = Annotated[
    str, Field(strict=True, pattern=r"^\d{4}-\d{2}-\d{2}\.[a-z][a-z0-9-]{0,39}$")
]
type MinorAmount = Annotated[StrictInt, Field(ge=0, le=999_999_999_999_999_999)]
type Currency = Annotated[str, Field(strict=True, pattern=r"^[a-z]{3}$")]
type UnixSecond = Annotated[StrictInt, Field(ge=0, le=253_402_300_799)]
type Sha256 = Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{64}$")]
type StripeEventType = Literal[
    "payment_intent.succeeded",
    "payment_intent.payment_failed",
    "payment_intent.processing",
    "payment_intent.canceled",
    "charge.succeeded",
    "charge.failed",
    "charge.pending",
    "charge.refunded",
    "refund.created",
    "refund.updated",
    "refund.failed",
]


class StripeEventPolicy(Versioned):
    """Expected decoder scope supplied by trusted code; no admission assertion."""

    namespace: Namespace
    account_id: AccountId
    api_version: ApiVersion


class StripePaymentIntent(Strict):
    object: Literal["payment_intent"] = "payment_intent"
    id: IntentId
    amount_minor: MinorAmount
    amount_received_minor: MinorAmount
    currency: Currency
    status: Literal[
        "requires_payment_method",
        "requires_confirmation",
        "requires_action",
        "processing",
        "requires_capture",
        "canceled",
        "succeeded",
    ]


class StripeCharge(Strict):
    object: Literal["charge"] = "charge"
    id: ChargeId
    payment_intent_id: IntentId | None
    amount_minor: MinorAmount
    amount_refunded_minor: MinorAmount
    currency: Currency
    status: Literal["succeeded", "pending", "failed"]
    paid: Annotated[bool, Field(strict=True)]
    captured: Annotated[bool, Field(strict=True)]
    refunded: Annotated[bool, Field(strict=True)]


class StripeRefund(Strict):
    object: Literal["refund"] = "refund"
    id: RefundId
    charge_id: ChargeId
    payment_intent_id: IntentId | None
    amount_minor: MinorAmount
    currency: Currency
    status: Literal["pending", "requires_action", "succeeded", "failed", "canceled"]


type StripeResource = Annotated[
    StripePaymentIntent | StripeCharge | StripeRefund, Field(discriminator="object")
]


class SignedStripeEvent(Versioned):
    """Signature-checked test snapshot, without tenant or financial authority.

    No raw payload, customer fields, metadata, secret or header is retained. The
    facts hash compares one event's selected immutable facts, not financial effects
    across different event IDs/resources. K2 must supply that operation identity.
    """

    provider: Literal["stripe_connect"] = "stripe_connect"
    format: Literal["snapshot"] = "snapshot"
    verification: Literal["signature_only"] = "signature_only"
    namespace: Namespace
    account_id: AccountId
    livemode: Literal[False] = False
    api_version: ApiVersion
    event_id: EventId
    event_type: StripeEventType
    created: UnixSecond
    resource: StripeResource
    delivery_sha256: Sha256

    @field_validator("livemode", mode="before")
    @classmethod
    def test_mode_only(cls, value: object) -> object:
        if type(value) is not bool or value:
            raise ValueError("Only an explicit false test-mode flag is supported")
        return value

    @model_validator(mode="after")
    def matching_resource(self) -> Self:
        if self.event_type.split(".", 1)[0] != self.resource.object:
            raise ValueError("The event and resource kinds must match")
        return self

    @property
    def facts_sha256(self) -> str:
        facts = self.model_dump(mode="json", exclude={"delivery_sha256"})
        return hashlib.sha256(
            json.dumps(facts, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
