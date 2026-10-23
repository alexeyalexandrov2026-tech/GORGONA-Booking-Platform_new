"""L5: commission plans and the commission accrual of a paid visit (package L, BEAUTY-01).

Design docs/plan/PACKAGE_L5_DESIGN_2026-10-22.md. A plan per specialist gives a percentage or a
fixed amount per service (or as the default); once the visit invoice is fully paid, one FIN-03
payable manual accrual to the payee holds the commission lines and, with a tips account, the tips.
"""

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Self
from uuid import UUID, uuid7

from pydantic import BaseModel, ConfigDict, Field, model_validator

from gorgona_booking.booking import idempotency
from gorgona_booking.booking import repository as repo
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.business import credit_notes, financial_documents, ledger
from gorgona_booking.business.commission_reversals import reversal_plan
from gorgona_booking.business.financial_contracts import (
    CreditDraftInput,
    CreditIssueInput,
    CreditLineInput,
    InvoiceDocumentView,
    InvoiceDraftInput,
    InvoiceLineInput,
)
from gorgona_booking.business.module_gate import require_module
from gorgona_booking.business.visit_billing import catalog_minor, load_visit_invoice
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, DomainError, InvalidReferenceError, NotFoundError

_PERCENT = r"^(0|[1-9][0-9]{0,2})(\.[0-9]{1,2})?$"
_AMOUNT = r"^(0|[1-9][0-9]{0,11})(\.[0-9]{1,3})?$"


class CommissionPlanRevisionError(ConflictError):
    code = "COMMISSION_PLAN_REVISION_CONFLICT"


class CommissionPlanMissingError(ConflictError):
    code = "COMMISSION_PLAN_MISSING"


class CommissionPlanNotFoundError(NotFoundError):
    """L7b2a: reading the plan of a specialist who has none."""

    code = "COMMISSION_PLAN_MISSING"


class VisitNotCommissionedError(NotFoundError):
    """L7b2a: reading the commission of a visit that has none."""

    code = "VISIT_NOT_COMMISSIONED"


class CommissionCurrencyError(ConflictError):
    code = "COMMISSION_CURRENCY_MISMATCH"


class CommissionAmountError(DomainError):
    code = "COMMISSION_AMOUNT_INVALID"


class VisitNotPaidError(ConflictError):
    code = "VISIT_NOT_PAID"


class VisitInvoiceCreditedError(ConflictError):
    code = "VISIT_INVOICE_CREDITED"


class VisitCommissionNotIssuedError(ConflictError):
    """L9 decision 82: the commission accrual is issued before it is reversed."""

    code = "VISIT_COMMISSION_NOT_ISSUED"


class VisitNothingToReverseError(ConflictError):
    code = "VISIT_NOTHING_TO_REVERSE"


class VisitNotCommissionableError(ConflictError):
    code = "VISIT_NOT_COMMISSIONABLE"


class VisitAlreadyCommissionedError(ConflictError):
    code = "VISIT_ALREADY_COMMISSIONED"


class NothingToAccrueError(ConflictError):
    code = "COMMISSION_NOTHING_TO_ACCRUE"


class TipsAccountNotLiabilityError(DomainError):
    code = "TIPS_ACCOUNT_NOT_LIABILITY"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RuleInput(_Strict):
    # Null: the default rule for every service without its own.
    service_id: UUID | None = None
    percent: str | None = Field(default=None, pattern=_PERCENT)
    amount: str | None = Field(default=None, pattern=_AMOUNT)

    @model_validator(mode="after")
    def one_kind(self) -> Self:
        if (self.percent is None) == (self.amount is None):
            raise ValueError("A rule is either a percentage or a fixed amount")
        if self.percent is not None and Decimal(self.percent) > 100:
            raise ValueError("A percentage is at most 100")
        return self


class PlanInput(_Strict):
    expected_revision: int = Field(ge=0)
    counterparty_id: UUID
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    rules: list[RuleInput] = Field(max_length=50)

    @model_validator(mode="after")
    def one_rule_per_service(self) -> Self:
        services = [rule.service_id for rule in self.rules]
        if len(set(services)) != len(services):
            raise ValueError("A service, or the default, has one rule")
        return self


class RuleView(BaseModel):
    service_id: UUID | None
    percent: str | None
    amount: str | None


class PlanView(BaseModel):
    resource_id: UUID
    counterparty_id: UUID
    currency: str
    revision: int
    updated_at: datetime
    rules: list[RuleView]


class CommissionInput(_Strict):
    expense_account_id: UUID
    payable_account_id: UUID
    # A liability that holds the tips of the visit invoice; its tips move to the payee.
    tips_account_id: UUID | None = None
    accrual_date: date
    number: str = Field(min_length=1, max_length=64)
    title: str = Field(default="Commission", min_length=1, max_length=200)


class ReversalInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    credit_date: date
    number: str = Field(min_length=1, max_length=64)
    # Needed exactly when part of the commission was already paid to the payee.
    refund_control_account_id: UUID | None = None


class ReversalView(BaseModel):
    refund_document_id: UUID
    # None when the refund touched no service line.
    reversal_document_id: UUID | None
    amount: str


class VisitCommissionView(BaseModel):
    booking_id: UUID
    book_id: UUID
    document_id: UUID
    accrual: InvoiceDocumentView
    # Decision 30: the tips held for the specialist on the named liability account.
    tips_account_id: UUID | None
    tips: str
    # L9 decisions 82-83: the reversals after refunds and what is still to reverse.
    reversals: list[ReversalView] = Field(default_factory=list)
    to_reverse: str = "0"


def _money(minor: int, units: int) -> str:
    whole, fraction = divmod(minor, 10**units)
    return str(whole) if units == 0 else f"{whole}.{fraction:0{units}d}"


def _minor(text: str, units: int) -> int:
    whole, _, fraction = text.partition(".")
    if len(fraction) > units:
        raise CommissionAmountError(f"At most {units} decimal places are accepted here")
    scale: int = 10**units
    return int(whole) * scale + int(fraction.ljust(units, "0") or "0")


def _percent(basis_points: int) -> str:
    return f"{basis_points // 100}.{basis_points % 100:02d}"


async def _units(conn: RuntimeConnection, currency: str) -> int:
    row = await (
        await conn.execute("select minor_units from gba.currencies where code = %s", (currency,))
    ).fetchone()
    if row is None:
        raise InvalidReferenceError("Unknown currency", field="currency")
    return int(row[0])


async def load_plan(conn: RuntimeConnection, resource_id: UUID) -> PlanView | None:
    head = await (
        await conn.execute(
            "select counterparty_id, currency, revision, updated_at from gba.commission_plans "
            "where resource_id = %s",
            (resource_id,),
        )
    ).fetchone()
    if head is None:
        return None
    units = await _units(conn, head[1])
    rows = await (
        await conn.execute(
            "select service_id, percent_bp, amount_minor from gba.commission_rules "
            "where resource_id = %s order by position",
            (resource_id,),
        )
    ).fetchall()
    return PlanView(
        resource_id=resource_id,
        counterparty_id=head[0],
        currency=head[1],
        revision=head[2],
        updated_at=head[3],
        rules=[
            RuleView(
                service_id=r[0],
                percent=None if r[1] is None else _percent(int(r[1])),
                amount=None if r[2] is None else _money(int(r[2]), units),
            )
            for r in rows
        ],
    )


async def save_plan(
    conn: RuntimeConnection, tenant_id: UUID, resource_id: UUID, user_id: UUID, body: PlanInput
) -> PlanView:
    """Replace a specialist's whole plan with the expected revision (decision 28)."""
    # L8 decision 64: commission plans belong to the workforce module.
    await require_module(conn, tenant_id, "workforce")
    artist = await (
        await conn.execute(
            "select 1 from gba.resources where id = %s and kind = 'artist'", (resource_id,)
        )
    ).fetchone()
    if artist is None:
        raise NotFoundError("Specialist not found", resource_id=str(resource_id))
    current = await (
        await conn.execute(
            "select revision from gba.commission_plans where resource_id = %s for update",
            (resource_id,),
        )
    ).fetchone()
    actual = 0 if current is None else int(current[0])
    if actual != body.expected_revision:
        raise CommissionPlanRevisionError(
            "The plan changed since it was read; reload it", revision=actual
        )
    units = await _units(conn, body.currency)
    rules = [
        (
            rule.service_id,
            None if rule.percent is None else _minor(rule.percent, 2),
            None if rule.amount is None else _minor(rule.amount, units),
        )
        for rule in body.rules
    ]
    # L8 decision 66: references are refused in plain words before anything is written.
    payee = await (
        await conn.execute(
            "select 1 from gba.counterparties where id = %s", (body.counterparty_id,)
        )
    ).fetchone()
    if payee is None:
        raise InvalidReferenceError("Unknown payee", field="counterparty_id")
    named = sorted({str(rule.service_id) for rule in body.rules if rule.service_id is not None})
    if named:
        found = await (
            await conn.execute(
                "select count(*) from gba.services where id = any(%s::uuid[])", (named,)
            )
        ).fetchone()
        if found is None or int(found[0]) != len(named):
            raise InvalidReferenceError("Unknown service in a rule", field="rules")
    if current is None:
        # A first save racing another one waits on its row and then finds the plan taken.
        created = await (
            await conn.execute(
                "insert into gba.commission_plans (tenant_id, resource_id, counterparty_id, "
                "currency, revision, updated_by) values (%s, %s, %s, %s, 1, %s) "
                "on conflict (tenant_id, resource_id) do nothing returning resource_id",
                (tenant_id, resource_id, body.counterparty_id, body.currency, user_id),
            )
        ).fetchone()
        if created is None:
            raise CommissionPlanRevisionError(
                "The plan changed since it was read; reload it", revision=1
            )
    else:
        await conn.execute(
            "update gba.commission_plans set counterparty_id = %s, currency = %s, "
            "revision = revision + 1, updated_by = %s, updated_at = now() where resource_id = %s",
            (body.counterparty_id, body.currency, user_id, resource_id),
        )
    await conn.execute("delete from gba.commission_rules where resource_id = %s", (resource_id,))
    for position, (service, basis_points, minor) in enumerate(rules, start=1):
        await conn.execute(
            "insert into gba.commission_rules (tenant_id, resource_id, position, service_id, "
            "percent_bp, amount_minor) values (%s, %s, %s, %s, %s, %s)",
            (tenant_id, resource_id, position, service, basis_points, minor),
        )
    view = await load_plan(conn, resource_id)
    assert view is not None  # noqa: S101 - saved above
    return view


def _groups(quote: dict[str, Any], units: int) -> list[tuple[dict[str, Any], int]]:
    """Each variant line of the quote with the price of its own add-ons (L2c order).

    Amounts are the currency's minor units, converted exactly from the catalog's hundredths
    (L8 decision 55).
    """
    groups: list[tuple[dict[str, Any], int]] = []
    for line in quote.get("lines") or []:
        price = catalog_minor(int(line["price_cents"]), units)
        if line.get("kind") == "variant":
            groups.append((line, price))
        elif groups:
            variant, base = groups[-1]
            groups[-1] = (variant, base + price)
    return groups


async def _commission_lines(
    conn: RuntimeConnection,
    quote: dict[str, Any],
    plan: tuple[UUID, str],
    units: int,
    body: CommissionInput,
) -> list[InvoiceLineInput]:
    rules: dict[UUID | None, tuple[int | None, int | None]] = {
        row[0]: (row[1], row[2])
        for row in await (
            await conn.execute(
                "select service_id, percent_bp, amount_minor from gba.commission_rules "
                "where resource_id = %s",
                (plan[0],),
            )
        ).fetchall()
    }
    lines: list[InvoiceLineInput] = []
    for variant, base in _groups(quote, units):
        service = await (
            await conn.execute(
                "select service_id from gba.service_variants where id = %s", (variant["id"],)
            )
        ).fetchone()
        rule = rules.get(service[0] if service else None) or rules.get(None)
        if rule is None:
            continue
        basis_points, fixed = rule
        # A percentage rounds half up to the currency's minor units (decision 29).
        minor = fixed if fixed is not None else (2 * base * (basis_points or 0) + 10000) // 20000
        if minor > 0:
            lines.append(
                InvoiceLineInput(
                    line_id=uuid7(),
                    counter_account_id=body.expense_account_id,
                    description=f"Commission: {variant['name']}",
                    amount=_money(minor, units),
                )
            )
    return lines


async def accrue_commission(
    conn: RuntimeConnection,
    tenant_id: UUID,
    booking_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: CommissionInput,
) -> VisitCommissionView:
    """One payable accrual of a fully paid visit to its specialist's payee (decisions 29-31)."""
    # L8 decision 64: accruing a commission needs the workforce module.
    await require_module(conn, tenant_id, "workforce")
    scope = IdempotencyScope(tenant_id, actor, "visit.commission", key)
    fingerprint = hashlib.sha256(
        json.dumps(
            {"booking_id": str(booking_id), "body": body.model_dump(mode="json")},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None:
        if stored.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("Key was used for another request")
        view = await load_commission(conn, tenant_id, booking_id)
        if view is None:
            raise NotFoundError("Commission not found", booking_id=str(booking_id))
        return view
    booking = await (
        await conn.execute(
            "select quote, status from gba.bookings where id = %s for update", (booking_id,)
        )
    ).fetchone()
    if booking is None:
        raise NotFoundError("Booking not found", booking_id=str(booking_id))
    if booking[1] != "CONFIRMED":
        # L8 decision 54: a cancelled visit's fee earns no commission.
        raise VisitNotCommissionableError(
            "Only a confirmed visit earns a commission", status=booking[1]
        )
    if await load_commission(conn, tenant_id, booking_id) is not None:
        raise VisitAlreadyCommissionedError("This visit already has its commission")
    billed = await load_visit_invoice(conn, tenant_id, booking_id)
    obligation = billed.obligation if billed is not None else None
    if billed is None or obligation is None:
        raise VisitNotPaidError("The visit invoice is not issued yet")
    # L9 decision 85: a prepaid redemption settles the visit; a refund is reversed afterwards.
    if Decimal(obligation.available) != 0 or Decimal(obligation.reserved) != 0:
        raise VisitNotPaidError(
            "The visit invoice is not fully paid", available=obligation.available
        )
    specialist = await repo.primary_resource_id(conn, booking_id)
    plan = await (
        await conn.execute(
            "select resource_id, currency, counterparty_id from gba.commission_plans "
            "where resource_id = %s",
            (specialist,),
        )
    ).fetchone()
    if plan is None:
        raise CommissionPlanMissingError("The specialist has no commission plan")
    invoice = billed.invoice
    if plan[1] != invoice.currency:
        raise CommissionCurrencyError("The plan and the visit use different currencies")
    lines = await _commission_lines(conn, booking[0], (plan[0], plan[1]), invoice.minor_units, body)
    if body.tips_account_id is not None:
        account = await ledger.load_account(conn, tenant_id, billed.book_id, body.tips_account_id)
        if account is None or account.type != "liability":
            raise TipsAccountNotLiabilityError("Tips are held on a liability account")
    tips = sum(
        _minor(line.amount, invoice.minor_units)
        for line in invoice.lines
        if body.tips_account_id is not None and line.counter_account_id == body.tips_account_id
    )
    if not lines:
        raise NothingToAccrueError("Nothing is owed to the specialist for this visit")
    party = await (
        await conn.execute(
            "select max(revision) from gba.counterparty_versions where counterparty_id = %s",
            (plan[2],),
        )
    ).fetchone()
    if party is None or party[0] is None:
        raise InvalidReferenceError("Unknown payee", field="counterparty_id")
    document = uuid7()
    await financial_documents.save_draft(
        conn,
        business_id=tenant_id,
        book_id=billed.book_id,
        document_id=document,
        user_id=user_id,
        actor=actor,
        key=key,
        body=InvoiceDraftInput(
            expected_revision=0,
            direction="payable",
            counterparty_id=plan[2],
            counterparty_revision=int(party[0]),
            currency=invoice.currency,
            invoice_date=body.accrual_date,
            control_account_id=body.payable_account_id,
            title=body.title,
            number=body.number,
            lines=tuple(lines),
        ),
        kind="manual_accrual",
    )
    await conn.execute(
        "insert into gba.visit_commissions (tenant_id, booking_id, book_id, document_id, "
        "tips_account_id, tips_minor, created_by) values (%s, %s, %s, %s, %s, %s, %s)",
        (tenant_id, booking_id, billed.book_id, document, body.tips_account_id, tips, user_id),
    )
    view = await load_commission(conn, tenant_id, booking_id)
    assert view is not None  # noqa: S101 - linked above
    await idempotency.complete(conn, scope, 200, {"booking_id": str(booking_id)})
    return view


async def load_commission(
    conn: RuntimeConnection, tenant_id: UUID, booking_id: UUID
) -> VisitCommissionView | None:
    link = await (
        await conn.execute(
            "select book_id, document_id, tips_account_id, tips_minor from gba.visit_commissions "
            "where booking_id = %s",
            (booking_id,),
        )
    ).fetchone()
    if link is None:
        return None
    accrual = await financial_documents.load_invoice(
        conn, tenant_id, link[0], link[1], kind="manual_accrual"
    )
    if accrual is None:
        raise NotFoundError("Accrual not found", document_id=str(link[1]))
    units = accrual.minor_units
    recorded = await (
        await conn.execute(
            "select refund_document_id, reversal_document_id, amount_minor "
            "from gba.visit_commission_reversals where booking_id = %s "
            "order by created_at, refund_document_id",
            (booking_id,),
        )
    ).fetchall()
    plan = await reversal_plan(conn, tenant_id, booking_id, link[0], accrual)
    return VisitCommissionView(
        booking_id=booking_id,
        book_id=link[0],
        document_id=link[1],
        accrual=accrual,
        tips_account_id=link[2],
        tips=_money(int(link[3]), units),
        reversals=[
            ReversalView(
                refund_document_id=row[0],
                reversal_document_id=row[1],
                amount=_money(int(row[2]), units),
            )
            for row in recorded
        ],
        to_reverse=_money(sum(sum(deltas.values()) for _, deltas in plan), units),
    )


async def reverse_commission(
    conn: RuntimeConnection,
    tenant_id: UUID,
    booking_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: ReversalInput,
) -> VisitCommissionView:
    """One FIN-03 credit note of the accrual for the refunds not yet reversed (L9 decision 82)."""
    await require_module(conn, tenant_id, "workforce")
    scope = IdempotencyScope(tenant_id, actor, "visit.commission.reversal", key)
    fingerprint = hashlib.sha256(
        json.dumps(
            {"booking_id": str(booking_id), "body": body.model_dump(mode="json")},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None:
        if stored.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("Key was used for another request")
        view = await load_commission(conn, tenant_id, booking_id)
        if view is None:
            raise NotFoundError("Commission not found", booking_id=str(booking_id))
        return view
    # Two reversals of one visit wait here; the second finds nothing left (decision 84).
    locked = await (
        await conn.execute("select 1 from gba.bookings where id = %s for update", (booking_id,))
    ).fetchone()
    if locked is None:
        raise NotFoundError("Booking not found", booking_id=str(booking_id))
    view = await load_commission(conn, tenant_id, booking_id)
    if view is None:
        raise VisitNotCommissionedError("This visit has no commission", booking_id=str(booking_id))
    accrual = view.accrual
    if accrual.obligation_id is None:
        raise VisitCommissionNotIssuedError("Issue the commission accrual before reversing it")
    plan = await reversal_plan(conn, tenant_id, booking_id, view.book_id, accrual)
    if not plan:
        raise VisitNothingToReverseError("No refund of this visit is left to reverse")
    units = accrual.minor_units
    totals: dict[UUID, int] = {}
    for _, deltas in plan:
        for line, delta in deltas.items():
            totals[line] = totals.get(line, 0) + delta
    reversal: UUID | None = None
    if totals:
        reversal = uuid7()
        by_id = {line.line_id: line for line in accrual.lines}
        party = await (
            await conn.execute(
                "select max(revision) from gba.counterparty_versions where counterparty_id = %s",
                (accrual.counterparty_id,),
            )
        ).fetchone()
        if party is None or party[0] is None:
            raise InvalidReferenceError("Unknown payee", field="counterparty_id")
        await credit_notes.save_draft(
            conn,
            business_id=tenant_id,
            book_id=view.book_id,
            document_id=reversal,
            user_id=user_id,
            actor=actor,
            key=key,
            body=CreditDraftInput(
                expected_revision=0,
                credited_obligation_id=accrual.obligation_id,
                counterparty_revision=int(party[0]),
                credit_date=body.credit_date,
                title="Commission reversal",
                number=body.number,
                lines=tuple(
                    CreditLineInput(
                        line_id=uuid7(),
                        credited_line_id=line,
                        counter_account_id=by_id[line].counter_account_id,
                        description=f"Reversal of {by_id[line].description}",
                        amount=_money(amount, units),
                    )
                    for line, amount in totals.items()
                ),
            ),
        )
        await credit_notes.issue_credit(
            conn,
            business_id=tenant_id,
            book_id=view.book_id,
            document_id=reversal,
            user_id=user_id,
            actor=actor,
            key=key,
            body=CreditIssueInput(
                expected_revision=1,
                entry_date=body.credit_date,
                attestation="confirmed_account_treatment",
                refund_control_account_id=body.refund_control_account_id,
            ),
        )
    for refund, deltas in plan:
        amount = sum(deltas.values())
        await conn.execute(
            "insert into gba.visit_commission_reversals (tenant_id, book_id, "
            "refund_document_id, booking_id, reversal_document_id, amount_minor, created_by) "
            "values (%s, %s, %s, %s, %s, %s, %s)",
            (
                tenant_id,
                view.book_id,
                refund,
                booking_id,
                reversal if amount > 0 else None,
                amount,
                user_id,
            ),
        )
    result = await load_commission(conn, tenant_id, booking_id)
    assert result is not None  # noqa: S101 - read above
    await idempotency.complete(conn, scope, 200, {"booking_id": str(booking_id)})
    return result
