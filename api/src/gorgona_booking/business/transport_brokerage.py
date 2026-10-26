"""N1: broker authority and carrier profiles as dated facts (package N, ADR-0034).

Design docs/plan/PACKAGE_N1_DESIGN_2026-10-26.md. A business keeps insert-only versions of its
broker authority, and each carrier (a counterparty) insert-only versions of its profile, each with a
source and the date it was checked. Eligibility is computed for a date, never stored, and names
every failing reason: unknown, expired or stale facts are never eligible.
"""

import hashlib
import json
from datetime import date, datetime, timedelta
from typing import Any, Literal, Self
from uuid import UUID

from psycopg.errors import CheckViolation, ForeignKeyViolation, UniqueViolation
from pydantic import BaseModel, ConfigDict, Field, model_validator

from gorgona_booking.booking import idempotency
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.business.module_gate import TRANSPORT_MODULE, module_writes
from gorgona_booking.business.transport import TransportRevisionConflictError, require_transport
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import InvalidReferenceError

# ADR-0034 decision 3: a fact checked longer ago than this is stale.
CHECK_WINDOW = timedelta(days=90)
_SOURCE = r"^[a-z][a-z0-9_.-]{0,31}$"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _visible(value: str | None) -> None:
    if value is not None and (not value.strip() or any(ord(c) < 32 for c in value)):
        raise ValueError("a number or reference has visible text and no control characters")


class AuthorityInput(_Strict):
    schema_version: Literal[1]
    expected_revision: int = Field(ge=0, le=2_147_483_647)
    jurisdiction: str = Field(pattern=r"^[A-Z]{2}$")
    authority_number: str = Field(min_length=1, max_length=32)
    bond_reference: str = Field(min_length=1, max_length=64)
    status: Literal["active", "withdrawn"]
    effective_from: date
    expires_on: date | None = None
    source: str = Field(pattern=_SOURCE)
    checked_on: date

    @model_validator(mode="after")
    def _facts(self) -> Self:
        _visible(self.authority_number)
        _visible(self.bond_reference)
        if self.expires_on is not None and self.expires_on < self.effective_from:
            raise ValueError("an authority expires on or after it takes effect")
        return self


class AuthorityVersion(BaseModel):
    revision: int
    jurisdiction: str
    authority_number: str
    bond_reference: str
    status: str
    effective_from: date
    expires_on: date | None
    source: str
    checked_on: date
    created_at: datetime


class AuthorityView(BaseModel):
    current: AuthorityVersion | None
    versions: list[AuthorityVersion]


Rating = Literal["satisfactory", "conditional", "unsatisfactory", "unrated"]


class CarrierProfileInput(_Strict):
    schema_version: Literal[1]
    expected_revision: int = Field(ge=0, le=2_147_483_647)
    jurisdiction: str = Field(pattern=r"^[A-Z]{2}$")
    # Unknown values are allowed and make the carrier ineligible (ADR-0034 decision 3).
    authority_number: str | None = Field(default=None, min_length=1, max_length=32)
    liability_expires_on: date | None = None
    cargo_expires_on: date | None = None
    safety_rating: Rating
    source: str = Field(pattern=_SOURCE)
    checked_on: date

    @model_validator(mode="after")
    def _facts(self) -> Self:
        _visible(self.authority_number)
        return self


class ProfileVersion(BaseModel):
    revision: int
    jurisdiction: str
    authority_number: str | None
    liability_expires_on: date | None
    cargo_expires_on: date | None
    safety_rating: str
    source: str
    checked_on: date
    created_at: datetime


class CarrierProfileView(BaseModel):
    counterparty_id: UUID
    current: ProfileVersion | None
    versions: list[ProfileVersion]


class EligibilityView(BaseModel):
    on: date
    eligible: bool
    reasons: list[str]


def _fingerprint(subject: object, body: BaseModel) -> str:
    return hashlib.sha256(
        json.dumps(
            {"subject": str(subject), "body": body.model_dump(mode="json")},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def _stale(checked_on: date, on: date) -> bool:
    return on > checked_on + CHECK_WINDOW


# Broker authority ----------------------------------------------------------------------


_AUTHORITY = (
    "select revision, jurisdiction, authority_number, bond_reference, status, effective_from, "
    "expires_on, source, checked_on, created_at from gba.transport_broker_authorities "
    "order by revision"
)


async def load_authority(conn: RuntimeConnection) -> AuthorityView:
    rows = await (await conn.execute(_AUTHORITY)).fetchall()
    versions = [
        AuthorityVersion(
            revision=row[0],
            jurisdiction=row[1],
            authority_number=row[2],
            bond_reference=row[3],
            status=row[4],
            effective_from=row[5],
            expires_on=row[6],
            source=row[7],
            checked_on=row[8],
            created_at=row[9],
        )
        for row in rows
    ]
    return AuthorityView(current=versions[-1] if versions else None, versions=versions)


def authority_eligibility(view: AuthorityView, on: date) -> EligibilityView:
    """May the business tender on this date (ADR-0034 decision 3)?"""
    current = view.current
    reasons: list[str] = []
    if current is None:
        reasons.append("no_authority")
    else:
        if current.status == "withdrawn":
            reasons.append("withdrawn")
        if on < current.effective_from:
            reasons.append("not_effective")
        if current.expires_on is not None and on > current.expires_on:
            reasons.append("expired")
        if _stale(current.checked_on, on):
            reasons.append("stale_check")
    return EligibilityView(on=on, eligible=not reasons, reasons=reasons)


async def save_authority(
    conn: RuntimeConnection,
    business: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: AuthorityInput,
) -> AuthorityView:
    """A new version of the business's broker authority, with the expected revision."""
    await require_transport(conn, business)
    scope = IdempotencyScope(business, actor, "transport.broker_authority", key)
    fingerprint = _fingerprint(business, body)
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None:
        if stored.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("Key was used for another request")
        return await load_authority(conn)
    view = await load_authority(conn)
    current = view.current.revision if view.current else 0
    if body.expected_revision != current:
        raise TransportRevisionConflictError(
            "The broker authority changed meanwhile",
            expected=body.expected_revision,
            current=current,
        )
    try:
        async with module_writes(TRANSPORT_MODULE), conn.transaction():
            await conn.execute(
                "insert into gba.transport_broker_authorities (tenant_id, revision, jurisdiction, "
                "authority_number, bond_reference, status, effective_from, expires_on, source, "
                "checked_on, created_by) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    business,
                    current + 1,
                    body.jurisdiction,
                    body.authority_number.strip(),
                    body.bond_reference.strip(),
                    body.status,
                    body.effective_from,
                    body.expires_on,
                    body.source,
                    body.checked_on,
                    user_id,
                ),
            )
    except (CheckViolation, UniqueViolation) as exc:
        raise TransportRevisionConflictError("The broker authority changed meanwhile") from exc
    view = await load_authority(conn)
    await idempotency.complete(conn, scope, 200, {"revision": current + 1})
    return view


# Carrier profiles -----------------------------------------------------------------------


_PROFILE = (
    "select revision, jurisdiction, authority_number, liability_expires_on, cargo_expires_on, "
    "safety_rating, source, checked_on, created_at from gba.transport_carrier_profiles "
    "where counterparty_id = %s order by revision"
)


async def _counterparty_exists(conn: RuntimeConnection, counterparty: UUID) -> bool:
    row = await (
        await conn.execute("select 1 from gba.counterparties where id = %s", (counterparty,))
    ).fetchone()
    return row is not None


async def load_profile(conn: RuntimeConnection, counterparty: UUID) -> CarrierProfileView | None:
    if not await _counterparty_exists(conn, counterparty):
        return None
    rows: list[Any] = await (await conn.execute(_PROFILE, (counterparty,))).fetchall()
    versions = [
        ProfileVersion(
            revision=row[0],
            jurisdiction=row[1],
            authority_number=row[2],
            liability_expires_on=row[3],
            cargo_expires_on=row[4],
            safety_rating=row[5],
            source=row[6],
            checked_on=row[7],
            created_at=row[8],
        )
        for row in rows
    ]
    return CarrierProfileView(
        counterparty_id=counterparty,
        current=versions[-1] if versions else None,
        versions=versions,
    )


def carrier_eligibility(view: CarrierProfileView, on: date) -> EligibilityView:
    """May the carrier be tendered to on this date (ADR-0034 decision 3)?"""
    current = view.current
    reasons: list[str] = []
    if current is None:
        reasons.append("no_profile")
    else:
        if current.authority_number is None:
            reasons.append("unknown_authority")
        for name, expires in (
            ("liability", current.liability_expires_on),
            ("cargo", current.cargo_expires_on),
        ):
            if expires is None:
                reasons.append(f"{name}_unknown")
            elif on > expires:
                reasons.append(f"{name}_expired")
        if current.safety_rating == "unsatisfactory":
            reasons.append("unsatisfactory")
        if _stale(current.checked_on, on):
            reasons.append("stale_check")
    return EligibilityView(on=on, eligible=not reasons, reasons=reasons)


async def save_profile(
    conn: RuntimeConnection,
    business: UUID,
    counterparty: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: CarrierProfileInput,
) -> CarrierProfileView | None:
    """A new version of a carrier's profile, with the expected revision; None for no carrier."""
    await require_transport(conn, business)
    scope = IdempotencyScope(business, actor, "transport.carrier_profile", key)
    fingerprint = _fingerprint(counterparty, body)
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None:
        if stored.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("Key was used for another request")
        return await load_profile(conn, counterparty)
    view = await load_profile(conn, counterparty)
    if view is None:
        return None
    current = view.current.revision if view.current else 0
    if body.expected_revision != current:
        raise TransportRevisionConflictError(
            "The carrier profile changed meanwhile",
            expected=body.expected_revision,
            current=current,
        )
    try:
        async with module_writes(TRANSPORT_MODULE), conn.transaction():
            await conn.execute(
                "insert into gba.transport_carrier_profiles (tenant_id, counterparty_id, revision, "
                "jurisdiction, authority_number, liability_expires_on, cargo_expires_on, "
                "safety_rating, source, checked_on, created_by) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    business,
                    counterparty,
                    current + 1,
                    body.jurisdiction,
                    body.authority_number.strip() if body.authority_number else None,
                    body.liability_expires_on,
                    body.cargo_expires_on,
                    body.safety_rating,
                    body.source,
                    body.checked_on,
                    user_id,
                ),
            )
    except ForeignKeyViolation as exc:
        raise InvalidReferenceError("Unknown carrier", field="counterparty_id") from exc
    except (CheckViolation, UniqueViolation) as exc:
        raise TransportRevisionConflictError("The carrier profile changed meanwhile") from exc
    view = await load_profile(conn, counterparty)
    await idempotency.complete(conn, scope, 200, {"revision": current + 1})
    return view
