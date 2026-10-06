"""Exact financial arithmetic shared by H documents and allocations.

These pure functions authorize no operation and persist no financial fact.
Callers must resolve book/currency, stable source identity, dependency/state
rules and eligibility under the G transaction lock. SQL must recheck the same
cap from immutable effective allocation history before committing effects.
"""

from typing import Self

from pydantic import Field, StrictInt, model_validator

from gorgona_booking.business.contracts import Strict
from gorgona_booking.business.financial_contracts import InvoiceDraftInput
from gorgona_booking.business.ledger_contracts import MAX_MINOR, to_minor
from gorgona_booking.errors import ConflictError, DomainError


class FinancialAmountError(DomainError):
    code = "FINANCIAL_AMOUNT_INVALID"


class FinancialCapError(ConflictError):
    code = "FINANCIAL_CAP_EXCEEDED"


class FinancialStateError(ConflictError):
    code = "FINANCIAL_STATE_INVALID"


class QuantizedInvoice(Strict):
    amounts_minor: tuple[StrictInt, ...]
    principal_minor: StrictInt = Field(ge=1, le=MAX_MINOR)


class FinancialBalance(Strict):
    principal_minor: StrictInt = Field(ge=1, le=MAX_MINOR)
    paid_minor: StrictInt = Field(default=0, ge=0, le=MAX_MINOR)
    credited_minor: StrictInt = Field(default=0, ge=0, le=MAX_MINOR)
    reserved_minor: StrictInt = Field(default=0, ge=0, le=MAX_MINOR)

    @model_validator(mode="after")
    def one_cap(self) -> Self:
        if self.paid_minor + self.credited_minor + self.reserved_minor > self.principal_minor:
            raise ValueError("Effective paid, credited and reserved allocations exceed principal")
        return self

    @property
    def available_minor(self) -> int:
        return self.principal_minor - self.paid_minor - self.credited_minor - self.reserved_minor


class CreditSplit(Strict):
    balance: FinancialBalance
    unpaid_minor: StrictInt = Field(ge=0, le=MAX_MINOR)
    refund_minor: StrictInt = Field(ge=0, le=MAX_MINOR)


def _amount(value: int, *, zero: bool = False) -> int:
    if type(value) is not int or not (0 if zero else 1) <= value <= MAX_MINOR:
        raise FinancialAmountError("An allocation needs bounded integer minor units")
    return value


def quantize_invoice(body: InvoiceDraftInput, scale: int) -> QuantizedInvoice:
    if type(scale) is not int or scale not in (0, 2, 3):
        raise FinancialAmountError("Unsupported currency scale")
    amounts = []
    for number, line in enumerate(body.lines, 1):
        try:
            amounts.append(to_minor(line.amount, scale))
        except ValueError as exc:
            raise FinancialAmountError(str(exc), line=number, currency=body.currency) from exc
    principal = sum(amounts)
    if principal > MAX_MINOR:
        raise FinancialAmountError("The invoice total exceeds the supported principal range")
    return QuantizedInvoice(amounts_minor=tuple(amounts), principal_minor=principal)


def reserve(balance: FinancialBalance, amount_minor: int) -> FinancialBalance:
    amount = _amount(amount_minor)
    if amount > balance.available_minor:
        raise FinancialCapError("The obligation has insufficient available principal")
    return FinancialBalance(
        principal_minor=balance.principal_minor,
        paid_minor=balance.paid_minor,
        credited_minor=balance.credited_minor,
        reserved_minor=balance.reserved_minor + amount,
    )


def confirm(balance: FinancialBalance, amount_minor: int) -> FinancialBalance:
    amount = _amount(amount_minor)
    if amount > balance.reserved_minor:
        raise FinancialCapError("Confirmation exceeds the reserved allocation")
    return FinancialBalance(
        principal_minor=balance.principal_minor,
        paid_minor=balance.paid_minor + amount,
        credited_minor=balance.credited_minor,
        reserved_minor=balance.reserved_minor - amount,
    )


def release(balance: FinancialBalance, amount_minor: int) -> FinancialBalance:
    amount = _amount(amount_minor)
    if amount > balance.reserved_minor:
        raise FinancialCapError("Release exceeds the reserved allocation")
    return FinancialBalance(
        principal_minor=balance.principal_minor,
        paid_minor=balance.paid_minor,
        credited_minor=balance.credited_minor,
        reserved_minor=balance.reserved_minor - amount,
    )


def split_credit(
    balance: FinancialBalance, amount_minor: int, *, uncredited_minor: int
) -> CreditSplit:
    """Split a validated line credit; confirmed cash stays in the original P."""
    amount = _amount(amount_minor)
    remaining = _amount(uncredited_minor, zero=True)
    if remaining > balance.principal_minor:
        raise FinancialAmountError("Original uncredited line capacity exceeds principal")
    if balance.reserved_minor:
        raise FinancialStateError("Resolve active reserves before issuing a credit")
    if amount > remaining:
        raise FinancialCapError("Credit exceeds the original uncredited line capacity")
    unpaid = min(amount, balance.available_minor)
    return CreditSplit(
        balance=FinancialBalance(
            principal_minor=balance.principal_minor,
            paid_minor=balance.paid_minor,
            credited_minor=balance.credited_minor + unpaid,
            reserved_minor=0,
        ),
        unpaid_minor=unpaid,
        refund_minor=amount - unpaid,
    )


def correct_confirmation(
    balance: FinancialBalance, *, old_minor: int, new_minor: int
) -> FinancialBalance:
    """Allocation effect after identity/dependency checks, never a cash refund."""
    old = _amount(old_minor)
    new = _amount(new_minor, zero=True)
    if old > balance.paid_minor or new > old:
        raise FinancialCapError("Correction exceeds the effective original allocation")
    return FinancialBalance(
        principal_minor=balance.principal_minor,
        paid_minor=balance.paid_minor - old + new,
        credited_minor=balance.credited_minor,
        reserved_minor=balance.reserved_minor + old - new,
    )
