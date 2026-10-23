"""L9a (package L): the published fee policy for late cancellations and no-shows.

Design docs/plan/PACKAGE_L9_DESIGN_2026-10-23.md decisions 76-77: insert-only versions; a visit
uses the version in force when it was booked. Amounts are computed by visit billing.
"""

from datetime import datetime
from typing import Any, Self
from uuid import UUID

from psycopg.errors import UniqueViolation
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
    model_validator,
)

from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError

_PERCENT = r"^(0|[1-9][0-9]{0,2})\.[0-9]{2}$"
_AMOUNT = r"^(0|[1-9][0-9]{0,9})\.[0-9]{2}$"


class VisitFeePolicyVersionConflictError(ConflictError):
    code = "VISIT_FEE_POLICY_VERSION_CONFLICT"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FeeRule(_Strict):
    """A percentage of the visit's priced total, or a fixed amount in the main currency unit."""

    percent: str | None = Field(default=None, pattern=_PERCENT)
    amount: str | None = Field(default=None, pattern=_AMOUNT)

    @model_validator(mode="after")
    def _one_kind(self) -> Self:
        if (self.percent is None) == (self.amount is None):
            raise ValueError("name either a percentage or an amount")
        if self.percent is not None and _hundredths(self.percent) > 10000:
            raise ValueError("a percentage is at most 100.00")
        return self

    @model_serializer(mode="wrap")
    def _only_named(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        return {k: v for k, v in handler(self).items() if v is not None}

    @property
    def basis_points(self) -> int | None:
        return None if self.percent is None else _hundredths(self.percent)

    @property
    def cents(self) -> int | None:
        return None if self.amount is None else _hundredths(self.amount)


class FeePolicyInput(_Strict):
    expected_version: int = Field(ge=0, le=1_000_000)
    free_cancellation_minutes: int = Field(ge=0, le=525600)
    late_cancellation_fee: FeeRule | None
    no_show_fee: FeeRule | None


class FeePolicyView(BaseModel):
    version: int
    published_at: datetime
    free_cancellation_minutes: int
    late_cancellation_fee: FeeRule | None
    no_show_fee: FeeRule | None


class FeePolicyList(BaseModel):
    versions: list[FeePolicyView]


def _hundredths(text: str) -> int:
    whole, _, fraction = text.partition(".")
    return int(whole) * 100 + int(fraction)


def _text(value: int) -> str:
    return f"{value // 100}.{value % 100:02d}"


def _rule(basis_points: int | None, cents: int | None) -> FeeRule | None:
    if basis_points is not None:
        return FeeRule(percent=_text(basis_points))
    if cents is not None:
        return FeeRule(amount=_text(cents))
    return None


_COLUMNS = (
    "version, published_at, free_cancellation_minutes, late_fee_bp, late_fee_cents, "
    "no_show_fee_bp, no_show_fee_cents"
)


def _view(row: Any) -> FeePolicyView:
    return FeePolicyView(
        version=row[0],
        published_at=row[1],
        free_cancellation_minutes=row[2],
        late_cancellation_fee=_rule(row[3], row[4]),
        no_show_fee=_rule(row[5], row[6]),
    )


async def list_versions(conn: RuntimeConnection) -> FeePolicyList:
    rows = await (
        await conn.execute(
            f"select {_COLUMNS} from gba.visit_fee_policies order by version desc limit 100"  # noqa: S608
        )
    ).fetchall()
    return FeePolicyList(versions=[_view(row) for row in rows])


async def publish(
    conn: RuntimeConnection, tenant_id: UUID, user_id: UUID, body: FeePolicyInput
) -> FeePolicyView:
    """A new version after the expected one (decision 76)."""
    current = await (
        await conn.execute("select coalesce(max(version), 0) from gba.visit_fee_policies")
    ).fetchone()
    if current is None or current[0] != body.expected_version:
        raise VisitFeePolicyVersionConflictError(
            "The fee policy changed; reload it", version=current[0] if current else None
        )
    late, no_show = body.late_cancellation_fee, body.no_show_fee
    try:
        async with conn.transaction():
            row = await (
                await conn.execute(
                    "insert into gba.visit_fee_policies (tenant_id, version, published_by, "  # noqa: S608
                    "free_cancellation_minutes, late_fee_bp, late_fee_cents, no_show_fee_bp, "
                    "no_show_fee_cents) values (%s, %s, %s, %s, %s, %s, %s, %s) "
                    f"returning {_COLUMNS}",
                    (
                        tenant_id,
                        body.expected_version + 1,
                        user_id,
                        body.free_cancellation_minutes,
                        late.basis_points if late else None,
                        late.cents if late else None,
                        no_show.basis_points if no_show else None,
                        no_show.cents if no_show else None,
                    ),
                )
            ).fetchone()
    except UniqueViolation as exc:
        raise VisitFeePolicyVersionConflictError("The fee policy changed; reload it") from exc
    assert row is not None  # noqa: S101 - inserted above
    return _view(row)


async def policy_for_booking(conn: RuntimeConnection, booking_id: UUID) -> FeePolicyView | None:
    """The version in force when the visit was booked (decision 77); none before any."""
    row = await (
        await conn.execute(
            f"select {_COLUMNS} from gba.visit_fee_policies p "  # noqa: S608
            "where p.published_at <= (select b.created_at from gba.bookings b where b.id = %s) "
            "order by p.version desc limit 1",
            (booking_id,),
        )
    ).fetchone()
    return None if row is None else _view(row)
