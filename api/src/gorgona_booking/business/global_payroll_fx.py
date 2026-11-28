"""AMARKAL v2.20.0: US Payroll Prep & FLSA/CA/Union Compliance +
Next-Gen Multi-Currency FX Ledger (Live Unrealized/Realized FX Gain/Loss) +
International Tax Profiles (EU/UK VAT, Reverse Charge, GST/HST, IVA) & Local Payment Rails.

Note on US regulatory boundaries:
AMARKAL calculates exact gross-to-net pay, FLSA/California/Union overtime, pre-tax benefits,
and estimated Federal/State/FICA withholdings in Prep & Compliance Mode with human approval
and structured export for licensed US payroll transmitters (Gusto, ADP, Check Embedded).
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Literal
from uuid import UUID

from psycopg import AsyncConnection
from psycopg.rows import dict_row

PayType = Literal["hourly", "salaried"]
OvertimeRule = Literal["flsa_weekly_40", "california_daily_8_12", "union_cba_custom"]
FilingStatus = Literal["single", "married_joint", "head_of_household"]
ExternalPayrollProvider = Literal["none", "gusto", "check_embedded", "adp", "rippling"]
PayrollRunStatus = Literal["draft", "approved", "exported_to_provider", "void"]
PayrollExportProvider = Literal["csv_adp_gusto", "gusto_api", "check_embedded"]

CurrencyCode = Literal["USD", "EUR", "GBP", "CAD", "MXN", "CHF", "AUD", "JPY"]
FxRateSource = Literal["manual", "ecb_feed", "fed_h10", "treasury"]
FxEntryKind = Literal["receivable", "payable", "cash_balance"]
FxEntryStatus = Literal["open", "settled"]

TaxRegime = Literal[
    "us_sales_tax",
    "eu_vat",
    "uk_vat",
    "ca_gst_hst",
    "mx_iva",
    "ch_mwst",
    "au_gst",
]
ReportingStandard = Literal["US_GAAP", "IFRS_EU", "UK_FRS102", "ASPE_CA", "NIF_MX"]
PaymentRailCode = Literal[
    "stripe_us_ach_card",
    "sepa_instant_eu",
    "uk_faster_payments",
    "ca_interac_eft",
    "mx_spei",
    "ch_qr_bill",
    "au_payid_becs",
    "swift_wire",
]

# Effective flat/mid-bracket US State income tax estimate in basis points (100 bps = 1.00%)
US_STATE_INCOME_TAX_BPS: dict[str, int] = {
    "AK": 0,
    "FL": 0,
    "NV": 0,
    "NH": 0,
    "SD": 0,
    "TN": 0,
    "TX": 0,
    "WA": 0,
    "WY": 0,
    "IL": 495,
    "PA": 307,
    "IN": 305,
    "MI": 425,
    "NC": 450,
    "CO": 440,
    "UT": 455,
    "AZ": 250,
    "GA": 539,
    "OH": 350,
    "CA": 800,
    "NY": 650,
    "NJ": 637,
    "MA": 500,
    "VA": 575,
    "MD": 525,
    "MN": 680,
    "OR": 875,
    "WI": 530,
    "CT": 550,
}

DEFAULT_FX_RATES_MICROS: tuple[tuple[CurrencyCode, int, FxRateSource], ...] = (
    ("USD", 1_000_000, "fed_h10"),
    ("EUR", 1_085_000, "ecb_feed"),
    ("GBP", 1_270_000, "fed_h10"),
    ("CAD", 725_000, "fed_h10"),
    ("MXN", 52_000, "fed_h10"),
    ("CHF", 1_135_000, "ecb_feed"),
    ("AUD", 655_000, "fed_h10"),
)

DEFAULT_TAX_PROFILES: tuple[
    tuple[str, str, TaxRegime, str, int, int, bool, CurrencyCode, ReportingStandard, bool], ...
] = (
    (
        "US",
        "United States (Federal / State)",
        "us_sales_tax",
        "US Sales Tax",
        825,
        0,
        False,
        "USD",
        "US_GAAP",
        True,
    ),
    (
        "DE",
        "European Union — Germany",
        "eu_vat",
        "EU VAT (USt)",
        1900,
        700,
        True,
        "EUR",
        "IFRS_EU",
        False,
    ),
    ("GB", "United Kingdom", "uk_vat", "UK VAT", 2000, 500, True, "GBP", "UK_FRS102", False),
    (
        "CA",
        "Canada — Ontario",
        "ca_gst_hst",
        "Ontario HST",
        1300,
        500,
        False,
        "CAD",
        "ASPE_CA",
        False,
    ),
    ("MX", "Mexico", "mx_iva", "Mexico IVA", 1600, 800, False, "MXN", "NIF_MX", False),
)

DEFAULT_PAYMENT_RAILS: tuple[tuple[PaymentRailCode, str, str, CurrencyCode, str], ...] = (
    (
        "stripe_us_ach_card",
        "Stripe US Direct (Cards, Apple Pay, ACH — 0% AMARKAL Fee)",
        "US",
        "USD",
        "Direct settlement to merchant US bank account via Stripe Connect.",
    ),
    (
        "sepa_instant_eu",
        "SEPA Instant Euro Transfer (EU / EEA)",
        "DE",
        "EUR",
        "Reference invoice number on EUR SEPA IBAN wire.",
    ),
    (
        "uk_faster_payments",
        "UK Faster Payments Service (FPS)",
        "GB",
        "GBP",
        "Sort code + account number GBP domestic settlement.",
    ),
)


def _require_row(row: dict[str, Any] | None, label: str) -> dict[str, Any]:
    if row is None:
        raise RuntimeError(f"Expected RETURNING row for {label}.")
    return row


@dataclass(frozen=True, slots=True)
class PayrollProfileView:
    id: UUID
    employee_code: str
    full_name: str
    email: str | None
    work_state: str
    pay_type: PayType
    base_rate_cents: int
    overtime_rule: OvertimeRule
    union_local_code: str
    union_dues_cents: int
    union_ot_multiplier_bps: int
    union_doubletime_bps: int
    health_insurance_pretax_cents: int
    retirement_401k_bps: int
    filing_status: FilingStatus
    state_tax_override_bps: int | None
    external_payroll_provider: ExternalPayrollProvider
    is_active: bool
    created_at: datetime


@dataclass(frozen=True, slots=True)
class PayrollLineCalculation:
    regular_hours_milli: int
    overtime_hours_milli: int
    doubletime_hours_milli: int
    regular_pay_cents: int
    overtime_pay_cents: int
    doubletime_pay_cents: int
    gross_pay_cents: int
    pretax_health_cents: int
    pretax_401k_cents: int
    federal_income_tax_cents: int
    state_income_tax_cents: int
    social_security_cents: int
    medicare_cents: int
    union_dues_cents: int
    net_pay_cents: int
    employer_fica_cents: int
    employer_futa_suta_cents: int
    compliance_notes: str


@dataclass(frozen=True, slots=True)
class PayrollRunLineView:
    id: UUID
    run_id: UUID
    profile_id: UUID
    employee_name: str
    work_state: str
    regular_hours_milli: int
    overtime_hours_milli: int
    doubletime_hours_milli: int
    bonus_cents: int
    regular_pay_cents: int
    overtime_pay_cents: int
    doubletime_pay_cents: int
    gross_pay_cents: int
    pretax_health_cents: int
    pretax_401k_cents: int
    federal_income_tax_cents: int
    state_income_tax_cents: int
    social_security_cents: int
    medicare_cents: int
    union_dues_cents: int
    net_pay_cents: int
    employer_fica_cents: int
    employer_futa_suta_cents: int
    compliance_notes: str


@dataclass(frozen=True, slots=True)
class PayrollRunView:
    id: UUID
    run_number: str
    period_start: date
    period_end: date
    pay_date: date
    status: PayrollRunStatus
    total_gross_cents: int
    total_employee_taxes_cents: int
    total_employer_taxes_cents: int
    total_deductions_cents: int
    total_net_cents: int
    export_provider: PayrollExportProvider
    approved_at: datetime | None
    notes: str
    lines: list[PayrollRunLineView]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class FxRateView:
    id: UUID
    base_currency: CurrencyCode
    quote_currency: str
    rate_micros: int
    source: FxRateSource
    effective_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class FxLedgerEntryView:
    id: UUID
    entry_number: str
    entry_date: date
    description: str
    counterparty_name: str
    currency: CurrencyCode
    amount_minor: int
    entry_kind: FxEntryKind
    booking_rate_micros: int
    booked_usd_cents: int
    current_rate_micros: int
    revalued_usd_cents: int
    fx_gain_loss_cents: int
    status: FxEntryStatus
    settled_rate_micros: int | None
    realized_fx_gain_loss_cents: int
    settled_at: datetime | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class InternationalTaxProfileView:
    id: UUID
    country_code: str
    region_label: str
    tax_regime: TaxRegime
    tax_name: str
    standard_rate_bps: int
    reduced_rate_bps: int
    reverse_charge_b2b: bool
    tax_registration_id: str
    default_currency: CurrencyCode
    reporting_standard: ReportingStandard
    is_default: bool
    is_active: bool


@dataclass(frozen=True, slots=True)
class LocalPaymentRailView:
    id: UUID
    rail_code: PaymentRailCode
    display_name: str
    country_code: str
    currency: CurrencyCode
    settlement_instructions: str
    iban_or_routing_masked: str
    is_enabled: bool


@dataclass(frozen=True, slots=True)
class TaxCalculationResult:
    subtotal_minor: int
    tax_minor: int
    total_minor: int
    applied_rate_bps: int
    reverse_charge_applied: bool
    tax_label: str
    reporting_standard: ReportingStandard


# ── Pure Deterministic US Payroll, FX & International Tax Math ───────────────


def split_us_overtime_hours(
    *,
    overtime_rule: OvertimeRule,
    daily_hours_milli: list[int],
) -> tuple[int, int, int, str]:
    """Split daily worked hours (in thousandths of an hour) into (regular, overtime, doubletime).

    - `flsa_weekly_40`: Federal FLSA — first 40.000 hrs regular, excess at 1.5x OT.
    - `california_daily_8_12`: CA Labor Code §510 — daily > 8h up to 12h is 1.5x OT,
      daily > 12h is 2.0x double-time; plus weekly regular hours capped at 40h (excess 1.5x OT).
    - `union_cba_custom`: Daily > 8h up to 10h is union OT multiplier, > 10h is double-time,
      weekly regular capped at 40h.
    """
    if not daily_hours_milli:
        return 0, 0, 0, "No hours logged."

    total_milli = sum(max(0, h) for h in daily_hours_milli)
    if overtime_rule == "flsa_weekly_40":
        reg = min(total_milli, 40_000)
        ot = max(0, total_milli - 40_000)
        return reg, ot, 0, "FLSA 40h weekly overtime rule applied."

    daily_reg_cap = 8_000
    daily_dt_start = 12_000 if overtime_rule == "california_daily_8_12" else 10_000
    reg_acc = 0
    ot_acc = 0
    dt_acc = 0
    for raw_h in daily_hours_milli:
        h = max(0, raw_h)
        if h > daily_dt_start:
            dt_acc += h - daily_dt_start
            ot_acc += daily_dt_start - daily_reg_cap
            reg_acc += daily_reg_cap
        elif h > daily_reg_cap:
            ot_acc += h - daily_reg_cap
            reg_acc += daily_reg_cap
        else:
            reg_acc += h

    # Weekly 40h cap on straight-time hours
    if reg_acc > 40_000:
        ot_acc += reg_acc - 40_000
        reg_acc = 40_000

    note = (
        "California Labor Code §510 (8h OT / 12h DT / 40h wk) applied."
        if overtime_rule == "california_daily_8_12"
        else "Union CBA daily 8h OT / 10h DT rule applied."
    )
    return reg_acc, ot_acc, dt_acc, note


def calculate_us_paystub(
    *,
    profile: PayrollProfileView,
    regular_hours_milli: int,
    overtime_hours_milli: int,
    doubletime_hours_milli: int,
    bonus_cents: int = 0,
    compliance_note_prefix: str = "",
) -> PayrollLineCalculation:
    """Exact integer-cent US paystub & employer tax calculation (Prep & Compliance Mode)."""
    if profile.pay_type == "salaried":
        regular_pay = profile.base_rate_cents
        overtime_pay = 0
        doubletime_pay = 0
    else:
        regular_pay = (regular_hours_milli * profile.base_rate_cents + 500) // 1000
        ot_bps = (
            profile.union_ot_multiplier_bps
            if profile.overtime_rule == "union_cba_custom"
            else 15_000
        )
        dt_bps = (
            profile.union_doubletime_bps if profile.overtime_rule == "union_cba_custom" else 20_000
        )
        overtime_pay = (
            overtime_hours_milli * profile.base_rate_cents * ot_bps + 5_000_000
        ) // 10_000_000
        doubletime_pay = (
            doubletime_hours_milli * profile.base_rate_cents * dt_bps + 5_000_000
        ) // 10_000_000

    gross = regular_pay + overtime_pay + doubletime_pay + max(0, bonus_cents)
    pretax_health = min(profile.health_insurance_pretax_cents, gross)
    pretax_401k = (gross * profile.retirement_401k_bps + 5000) // 10_000
    pretax_401k = min(pretax_401k, max(0, gross - pretax_health))
    taxable_income = max(0, gross - pretax_health - pretax_401k)

    # Federal withholding estimate by filing status (biweekly progressive approximation)
    if profile.filing_status == "married_joint":
        fed_bps = 1000 if taxable_income <= 300_000 else 1500
    elif profile.filing_status == "head_of_household":
        fed_bps = 1100 if taxable_income <= 250_000 else 1700
    else:
        fed_bps = 1200 if taxable_income <= 200_000 else 1900

    federal_tax = (taxable_income * fed_bps + 5000) // 10_000
    state_bps = (
        profile.state_tax_override_bps
        if profile.state_tax_override_bps is not None
        else US_STATE_INCOME_TAX_BPS.get(profile.work_state, 450)
    )
    state_tax = (taxable_income * state_bps + 5000) // 10_000

    # FICA: Social Security 6.20% (620 bps) + Medicare 1.45% (145 bps) on FICA-taxable wages
    fica_wages = max(0, gross - pretax_health)
    ss_tax = (fica_wages * 620 + 5000) // 10_000
    medicare_tax = (fica_wages * 145 + 5000) // 10_000
    union_dues = profile.union_dues_cents if profile.union_local_code else 0

    total_emp_out = (
        pretax_health + pretax_401k + federal_tax + state_tax + ss_tax + medicare_tax + union_dues
    )
    net_pay = max(0, gross - total_emp_out)

    # Employer-side statutory taxes: matching FICA (7.65%) + FUTA/SUTA est (3.30%)
    employer_fica = ss_tax + medicare_tax
    employer_futa_suta = (fica_wages * 330 + 5000) // 10_000

    notes_parts = [p for p in [compliance_note_prefix.strip()] if p]
    if profile.union_local_code:
        notes_parts.append(f"Union {profile.union_local_code}")
    notes_parts.append(f"State {profile.work_state} ({state_bps / 100:.2f}%)")
    return PayrollLineCalculation(
        regular_hours_milli=regular_hours_milli,
        overtime_hours_milli=overtime_hours_milli,
        doubletime_hours_milli=doubletime_hours_milli,
        regular_pay_cents=regular_pay,
        overtime_pay_cents=overtime_pay,
        doubletime_pay_cents=doubletime_pay,
        gross_pay_cents=gross,
        pretax_health_cents=pretax_health,
        pretax_401k_cents=pretax_401k,
        federal_income_tax_cents=federal_tax,
        state_income_tax_cents=state_tax,
        social_security_cents=ss_tax,
        medicare_cents=medicare_tax,
        union_dues_cents=union_dues,
        net_pay_cents=net_pay,
        employer_fica_cents=employer_fica,
        employer_futa_suta_cents=employer_futa_suta,
        compliance_notes=" · ".join(notes_parts),
    )


def convert_minor_to_usd_cents(*, amount_minor: int, rate_micros: int) -> int:
    """Convert foreign minor units (cents/pence) to exact USD cents using micro-rate (1e6 = 1.0)."""
    return (amount_minor * rate_micros + 500_000) // 1_000_000


def compute_fx_gain_loss_cents(
    *,
    entry_kind: FxEntryKind,
    booked_usd_cents: int,
    current_usd_cents: int,
) -> int:
    """Compute signed FX gain/loss in USD cents.

    - Receivable / Cash Balance: foreign currency strengthening => FX GAIN (+).
    - Payable: foreign currency strengthening => costs MORE USD to settle => FX LOSS (-).
    """
    diff = current_usd_cents - booked_usd_cents
    return -diff if entry_kind == "payable" else diff


def calculate_international_tax(
    *,
    profile: InternationalTaxProfileView,
    subtotal_minor: int,
    is_b2b_cross_border: bool = False,
    use_reduced_rate: bool = False,
) -> TaxCalculationResult:
    """Compute US Sales Tax, EU/UK VAT (with B2B Reverse Charge), Canada GST/HST, or Mexico IVA."""
    if is_b2b_cross_border and profile.reverse_charge_b2b:
        return TaxCalculationResult(
            subtotal_minor=subtotal_minor,
            tax_minor=0,
            total_minor=subtotal_minor,
            applied_rate_bps=0,
            reverse_charge_applied=True,
            tax_label=f"{profile.tax_name} — 0% B2B Reverse Charge",
            reporting_standard=profile.reporting_standard,
        )
    rate_bps = profile.reduced_rate_bps if use_reduced_rate else profile.standard_rate_bps
    tax_minor = (subtotal_minor * rate_bps + 5000) // 10_000
    return TaxCalculationResult(
        subtotal_minor=subtotal_minor,
        tax_minor=tax_minor,
        total_minor=subtotal_minor + tax_minor,
        applied_rate_bps=rate_bps,
        reverse_charge_applied=False,
        tax_label=f"{profile.tax_name} ({rate_bps / 100:.2f}%)",
        reporting_standard=profile.reporting_standard,
    )


# ── Row Mappers ──────────────────────────────────────────────────────────────


def _row_to_profile(r: dict[str, Any]) -> PayrollProfileView:
    return PayrollProfileView(
        id=r["id"],
        employee_code=str(r["employee_code"]),
        full_name=str(r["full_name"]),
        email=str(r["email"]) if r["email"] else None,
        work_state=str(r["work_state"]),
        pay_type=r["pay_type"],
        base_rate_cents=int(r["base_rate_cents"]),
        overtime_rule=r["overtime_rule"],
        union_local_code=str(r["union_local_code"] or ""),
        union_dues_cents=int(r["union_dues_cents"]),
        union_ot_multiplier_bps=int(r["union_ot_multiplier_bps"]),
        union_doubletime_bps=int(r["union_doubletime_bps"]),
        health_insurance_pretax_cents=int(r["health_insurance_pretax_cents"]),
        retirement_401k_bps=int(r["retirement_401k_bps"]),
        filing_status=r["filing_status"],
        state_tax_override_bps=(
            int(r["state_tax_override_bps"]) if r["state_tax_override_bps"] is not None else None
        ),
        external_payroll_provider=r["external_payroll_provider"],
        is_active=bool(r["is_active"]),
        created_at=r["created_at"],
    )


def _row_to_fx_rate(r: dict[str, Any]) -> FxRateView:
    return FxRateView(
        id=r["id"],
        base_currency=r["base_currency"],
        quote_currency=str(r["quote_currency"]),
        rate_micros=int(r["rate_micros"]),
        source=r["source"],
        effective_at=r["effective_at"],
        updated_at=r["updated_at"],
    )


def _row_to_fx_entry(r: dict[str, Any]) -> FxLedgerEntryView:
    return FxLedgerEntryView(
        id=r["id"],
        entry_number=str(r["entry_number"]),
        entry_date=r["entry_date"],
        description=str(r["description"]),
        counterparty_name=str(r["counterparty_name"] or ""),
        currency=r["currency"],
        amount_minor=int(r["amount_minor"]),
        entry_kind=r["entry_kind"],
        booking_rate_micros=int(r["booking_rate_micros"]),
        booked_usd_cents=int(r["booked_usd_cents"]),
        current_rate_micros=int(r["current_rate_micros"]),
        revalued_usd_cents=int(r["revalued_usd_cents"]),
        fx_gain_loss_cents=int(r["fx_gain_loss_cents"]),
        status=r["status"],
        settled_rate_micros=(
            int(r["settled_rate_micros"]) if r["settled_rate_micros"] is not None else None
        ),
        realized_fx_gain_loss_cents=int(r["realized_fx_gain_loss_cents"]),
        settled_at=r["settled_at"],
        created_at=r["created_at"],
    )


def _row_to_tax_profile(r: dict[str, Any]) -> InternationalTaxProfileView:
    return InternationalTaxProfileView(
        id=r["id"],
        country_code=str(r["country_code"]),
        region_label=str(r["region_label"]),
        tax_regime=r["tax_regime"],
        tax_name=str(r["tax_name"]),
        standard_rate_bps=int(r["standard_rate_bps"]),
        reduced_rate_bps=int(r["reduced_rate_bps"]),
        reverse_charge_b2b=bool(r["reverse_charge_b2b"]),
        tax_registration_id=str(r["tax_registration_id"] or ""),
        default_currency=r["default_currency"],
        reporting_standard=r["reporting_standard"],
        is_default=bool(r["is_default"]),
        is_active=bool(r["is_active"]),
    )


def _row_to_rail(r: dict[str, Any]) -> LocalPaymentRailView:
    return LocalPaymentRailView(
        id=r["id"],
        rail_code=r["rail_code"],
        display_name=str(r["display_name"]),
        country_code=str(r["country_code"]),
        currency=r["currency"],
        settlement_instructions=str(r["settlement_instructions"] or ""),
        iban_or_routing_masked=str(r["iban_or_routing_masked"] or ""),
        is_enabled=bool(r["is_enabled"]),
    )


# ── US Payroll Persistence ───────────────────────────────────────────────────


async def list_payroll_profiles(
    conn: AsyncConnection, *, tenant_id: UUID
) -> list[PayrollProfileView]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT id, employee_code, full_name, email, work_state, pay_type,
                   base_rate_cents, overtime_rule, union_local_code, union_dues_cents,
                   union_ot_multiplier_bps, union_doubletime_bps,
                   health_insurance_pretax_cents, retirement_401k_bps, filing_status,
                   state_tax_override_bps, external_payroll_provider, is_active, created_at
            FROM gba.payroll_profiles
            WHERE tenant_id = %s
            ORDER BY employee_code ASC
            """,
            (tenant_id,),
        )
        rows = await cur.fetchall()
    return [_row_to_profile(dict(r)) for r in rows]


async def create_payroll_profile(
    conn: AsyncConnection,
    *,
    tenant_id: UUID,
    employee_code: str,
    full_name: str,
    email: str | None,
    work_state: str,
    pay_type: PayType,
    base_rate_cents: int,
    overtime_rule: OvertimeRule,
    union_local_code: str,
    union_dues_cents: int,
    union_ot_multiplier_bps: int,
    union_doubletime_bps: int,
    health_insurance_pretax_cents: int,
    retirement_401k_bps: int,
    filing_status: FilingStatus,
    state_tax_override_bps: int | None,
    external_payroll_provider: ExternalPayrollProvider,
) -> PayrollProfileView:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            INSERT INTO gba.payroll_profiles (
                tenant_id, employee_code, full_name, email, work_state, pay_type,
                base_rate_cents, overtime_rule, union_local_code, union_dues_cents,
                union_ot_multiplier_bps, union_doubletime_bps,
                health_insurance_pretax_cents, retirement_401k_bps, filing_status,
                state_tax_override_bps, external_payroll_provider, is_active
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, true)
            RETURNING id, employee_code, full_name, email, work_state, pay_type,
                      base_rate_cents, overtime_rule, union_local_code, union_dues_cents,
                      union_ot_multiplier_bps, union_doubletime_bps,
                      health_insurance_pretax_cents, retirement_401k_bps, filing_status,
                      state_tax_override_bps, external_payroll_provider, is_active, created_at
            """,
            (
                tenant_id,
                employee_code.strip().upper(),
                full_name.strip(),
                email.strip() if email else None,
                work_state.strip().upper(),
                pay_type,
                base_rate_cents,
                overtime_rule,
                union_local_code.strip(),
                union_dues_cents,
                union_ot_multiplier_bps,
                union_doubletime_bps,
                health_insurance_pretax_cents,
                retirement_401k_bps,
                filing_status,
                state_tax_override_bps,
                external_payroll_provider,
            ),
        )
        row = _require_row(await cur.fetchone(), "payroll_profiles insert")
    return _row_to_profile(dict(row))


async def list_payroll_runs(conn: AsyncConnection, *, tenant_id: UUID) -> list[PayrollRunView]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT id, run_number, period_start, period_end, pay_date, status,
                   total_gross_cents, total_employee_taxes_cents, total_employer_taxes_cents,
                   total_deductions_cents, total_net_cents, export_provider, approved_at,
                   notes, created_at
            FROM gba.payroll_runs
            WHERE tenant_id = %s
            ORDER BY created_at DESC
            LIMIT 50
            """,
            (tenant_id,),
        )
        run_rows = await cur.fetchall()
        await cur.execute(
            """
            SELECT id, run_id, profile_id, employee_name, work_state,
                   regular_hours_milli, overtime_hours_milli, doubletime_hours_milli,
                   bonus_cents, regular_pay_cents, overtime_pay_cents, doubletime_pay_cents,
                   gross_pay_cents, pretax_health_cents, pretax_401k_cents,
                   federal_income_tax_cents, state_income_tax_cents, social_security_cents,
                   medicare_cents, union_dues_cents, net_pay_cents, employer_fica_cents,
                   employer_futa_suta_cents, compliance_notes
            FROM gba.payroll_run_lines
            WHERE tenant_id = %s
            ORDER BY employee_name ASC
            """,
            (tenant_id,),
        )
        line_rows = await cur.fetchall()

    lines_by_run: dict[UUID, list[PayrollRunLineView]] = {}
    for lr in line_rows:
        rid: UUID = lr["run_id"]
        lines_by_run.setdefault(rid, []).append(
            PayrollRunLineView(
                id=lr["id"],
                run_id=rid,
                profile_id=lr["profile_id"],
                employee_name=str(lr["employee_name"]),
                work_state=str(lr["work_state"]),
                regular_hours_milli=int(lr["regular_hours_milli"]),
                overtime_hours_milli=int(lr["overtime_hours_milli"]),
                doubletime_hours_milli=int(lr["doubletime_hours_milli"]),
                bonus_cents=int(lr["bonus_cents"]),
                regular_pay_cents=int(lr["regular_pay_cents"]),
                overtime_pay_cents=int(lr["overtime_pay_cents"]),
                doubletime_pay_cents=int(lr["doubletime_pay_cents"]),
                gross_pay_cents=int(lr["gross_pay_cents"]),
                pretax_health_cents=int(lr["pretax_health_cents"]),
                pretax_401k_cents=int(lr["pretax_401k_cents"]),
                federal_income_tax_cents=int(lr["federal_income_tax_cents"]),
                state_income_tax_cents=int(lr["state_income_tax_cents"]),
                social_security_cents=int(lr["social_security_cents"]),
                medicare_cents=int(lr["medicare_cents"]),
                union_dues_cents=int(lr["union_dues_cents"]),
                net_pay_cents=int(lr["net_pay_cents"]),
                employer_fica_cents=int(lr["employer_fica_cents"]),
                employer_futa_suta_cents=int(lr["employer_futa_suta_cents"]),
                compliance_notes=str(lr["compliance_notes"] or ""),
            )
        )

    return [
        PayrollRunView(
            id=r["id"],
            run_number=str(r["run_number"]),
            period_start=r["period_start"],
            period_end=r["period_end"],
            pay_date=r["pay_date"],
            status=r["status"],
            total_gross_cents=int(r["total_gross_cents"]),
            total_employee_taxes_cents=int(r["total_employee_taxes_cents"]),
            total_employer_taxes_cents=int(r["total_employer_taxes_cents"]),
            total_deductions_cents=int(r["total_deductions_cents"]),
            total_net_cents=int(r["total_net_cents"]),
            export_provider=r["export_provider"],
            approved_at=r["approved_at"],
            notes=str(r["notes"] or ""),
            lines=lines_by_run.get(r["id"], []),
            created_at=r["created_at"],
        )
        for r in run_rows
    ]


async def create_payroll_run(
    conn: AsyncConnection,
    *,
    tenant_id: UUID,
    period_start: date,
    period_end: date,
    pay_date: date,
    export_provider: PayrollExportProvider,
    notes: str,
    entries: list[tuple[UUID, list[int], int]],
    created_by_user_id: UUID | None,
) -> PayrollRunView:
    """Create a Draft US Payroll Prep run with exact FLSA/CA/Union gross-to-net lines."""
    if not entries:
        raise ValueError("Payroll run requires at least one employee time entry.")
    profiles = await list_payroll_profiles(conn, tenant_id=tenant_id)
    prof_map = {p.id: p for p in profiles}

    computed: list[tuple[PayrollProfileView, PayrollLineCalculation, int]] = []
    tot_gross = tot_emp_tax = tot_er_tax = tot_ded = tot_net = 0
    for prof_id, daily_hrs, bonus in entries:
        prof = prof_map.get(prof_id)
        if prof is None:
            raise LookupError("Referenced payroll profile not found.")
        reg_h, ot_h, dt_h, ot_note = split_us_overtime_hours(
            overtime_rule=prof.overtime_rule, daily_hours_milli=daily_hrs
        )
        calc = calculate_us_paystub(
            profile=prof,
            regular_hours_milli=reg_h,
            overtime_hours_milli=ot_h,
            doubletime_hours_milli=dt_h,
            bonus_cents=bonus,
            compliance_note_prefix=ot_note,
        )
        computed.append((prof, calc, bonus))
        tot_gross += calc.gross_pay_cents
        tot_emp_tax += (
            calc.federal_income_tax_cents
            + calc.state_income_tax_cents
            + calc.social_security_cents
            + calc.medicare_cents
        )
        tot_er_tax += calc.employer_fica_cents + calc.employer_futa_suta_cents
        tot_ded += calc.pretax_health_cents + calc.pretax_401k_cents + calc.union_dues_cents
        tot_net += calc.net_pay_cents

    run_number = f"PR-{datetime.now(UTC).strftime('%Y%m%d')}-{secrets.token_hex(3).upper()}"
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            INSERT INTO gba.payroll_runs (
                tenant_id, run_number, period_start, period_end, pay_date, status,
                total_gross_cents, total_employee_taxes_cents, total_employer_taxes_cents,
                total_deductions_cents, total_net_cents, export_provider, notes,
                created_by_user_id
            )
            VALUES (%s, %s, %s, %s, %s, 'draft', %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                tenant_id,
                run_number,
                period_start,
                period_end,
                pay_date,
                tot_gross,
                tot_emp_tax,
                tot_er_tax,
                tot_ded,
                tot_net,
                export_provider,
                notes.strip(),
                created_by_user_id,
            ),
        )
        run_id: UUID = _require_row(await cur.fetchone(), "payroll_runs insert")["id"]
        for prof, c, bonus in computed:
            await cur.execute(
                """
                INSERT INTO gba.payroll_run_lines (
                    tenant_id, run_id, profile_id, employee_name, work_state,
                    regular_hours_milli, overtime_hours_milli, doubletime_hours_milli,
                    bonus_cents, regular_pay_cents, overtime_pay_cents, doubletime_pay_cents,
                    gross_pay_cents, pretax_health_cents, pretax_401k_cents,
                    federal_income_tax_cents, state_income_tax_cents, social_security_cents,
                    medicare_cents, union_dues_cents, net_pay_cents, employer_fica_cents,
                    employer_futa_suta_cents, compliance_notes
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    tenant_id,
                    run_id,
                    prof.id,
                    prof.full_name,
                    prof.work_state,
                    c.regular_hours_milli,
                    c.overtime_hours_milli,
                    c.doubletime_hours_milli,
                    bonus,
                    c.regular_pay_cents,
                    c.overtime_pay_cents,
                    c.doubletime_pay_cents,
                    c.gross_pay_cents,
                    c.pretax_health_cents,
                    c.pretax_401k_cents,
                    c.federal_income_tax_cents,
                    c.state_income_tax_cents,
                    c.social_security_cents,
                    c.medicare_cents,
                    c.union_dues_cents,
                    c.net_pay_cents,
                    c.employer_fica_cents,
                    c.employer_futa_suta_cents,
                    c.compliance_notes,
                ),
            )

    runs = await list_payroll_runs(conn, tenant_id=tenant_id)
    for r in runs:
        if r.id == run_id:
            return r
    raise LookupError("Created payroll run could not be loaded.")


async def approve_or_export_payroll_run(
    conn: AsyncConnection,
    *,
    tenant_id: UUID,
    run_id: UUID,
    action: Literal["approve", "export", "void"],
    actor_user_id: UUID | None,
) -> PayrollRunView:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT status FROM gba.payroll_runs WHERE tenant_id = %s AND id = %s FOR UPDATE",
            (tenant_id, run_id),
        )
        row = await cur.fetchone()
        if row is None:
            raise LookupError("Payroll run not found.")
        cur_status = str(row["status"])
        if cur_status == "void":
            raise ValueError("Cannot modify a void payroll run.")
        if action == "approve":
            if cur_status != "draft":
                raise ValueError("Only draft payroll runs can be approved.")
            await cur.execute(
                """
                UPDATE gba.payroll_runs
                SET status = 'approved', approved_by_user_id = %s, approved_at = now(),
                    updated_at = now()
                WHERE tenant_id = %s AND id = %s
                """,
                (actor_user_id, tenant_id, run_id),
            )
        elif action == "export":
            if cur_status != "approved":
                raise ValueError("Human owner approval is required before exporting payroll.")
            await cur.execute(
                """
                UPDATE gba.payroll_runs
                SET status = 'exported_to_provider', updated_at = now()
                WHERE tenant_id = %s AND id = %s
                """,
                (tenant_id, run_id),
            )
        else:
            await cur.execute(
                """
                UPDATE gba.payroll_runs
                SET status = 'void', updated_at = now()
                WHERE tenant_id = %s AND id = %s
                """,
                (tenant_id, run_id),
            )

    runs = await list_payroll_runs(conn, tenant_id=tenant_id)
    for r in runs:
        if r.id == run_id:
            return r
    raise LookupError("Updated payroll run could not be loaded.")


# ── Multi-Currency FX Rates & Ledger Persistence ─────────────────────────────


async def ensure_and_list_fx_rates(conn: AsyncConnection, *, tenant_id: UUID) -> list[FxRateView]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT id, base_currency, quote_currency, rate_micros, source,
                   effective_at, updated_at
            FROM gba.fx_rates
            WHERE tenant_id = %s
            ORDER BY base_currency ASC
            """,
            (tenant_id,),
        )
        rows = await cur.fetchall()
        if not rows:
            for ccy, micros, src in DEFAULT_FX_RATES_MICROS:
                await cur.execute(
                    """
                    INSERT INTO gba.fx_rates (
                        tenant_id, base_currency, quote_currency, rate_micros, source
                    )
                    VALUES (%s, %s, 'USD', %s, %s)
                    ON CONFLICT (tenant_id, base_currency, quote_currency) DO NOTHING
                    """,
                    (tenant_id, ccy, micros, src),
                )
            await cur.execute(
                """
                SELECT id, base_currency, quote_currency, rate_micros, source,
                       effective_at, updated_at
                FROM gba.fx_rates
                WHERE tenant_id = %s
                ORDER BY base_currency ASC
                """,
                (tenant_id,),
            )
            rows = await cur.fetchall()
    return [_row_to_fx_rate(dict(r)) for r in rows]


async def upsert_fx_rate(
    conn: AsyncConnection,
    *,
    tenant_id: UUID,
    base_currency: CurrencyCode,
    rate_micros: int,
    source: FxRateSource,
) -> tuple[FxRateView, int]:
    """Update FX rate and auto-revalue all open multi-currency FX ledger entries on the fly."""
    effective_micros = 1_000_000 if base_currency == "USD" else rate_micros
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            INSERT INTO gba.fx_rates (
                tenant_id, base_currency, quote_currency, rate_micros, source,
                effective_at, updated_at
            )
            VALUES (%s, %s, 'USD', %s, %s, now(), now())
            ON CONFLICT (tenant_id, base_currency, quote_currency) DO UPDATE SET
                rate_micros = EXCLUDED.rate_micros,
                source = EXCLUDED.source,
                effective_at = now(),
                updated_at = now()
            RETURNING id, base_currency, quote_currency, rate_micros, source,
                      effective_at, updated_at
            """,
            (tenant_id, base_currency, effective_micros, source),
        )
        rate_row = _require_row(await cur.fetchone(), "fx_rates upsert")

        # Live Mark-to-Market revaluation on all open entries in this currency
        await cur.execute(
            """
            SELECT id, amount_minor, entry_kind, booked_usd_cents
            FROM gba.fx_ledger_entries
            WHERE tenant_id = %s AND currency = %s AND status = 'open'
            FOR UPDATE
            """,
            (tenant_id, base_currency),
        )
        open_rows = await cur.fetchall()
        revalued_cnt = 0
        for er in open_rows:
            reval_usd = convert_minor_to_usd_cents(
                amount_minor=int(er["amount_minor"]), rate_micros=effective_micros
            )
            gain_loss = compute_fx_gain_loss_cents(
                entry_kind=er["entry_kind"],
                booked_usd_cents=int(er["booked_usd_cents"]),
                current_usd_cents=reval_usd,
            )
            await cur.execute(
                """
                UPDATE gba.fx_ledger_entries
                SET current_rate_micros = %s,
                    revalued_usd_cents = %s,
                    fx_gain_loss_cents = %s,
                    updated_at = now()
                WHERE tenant_id = %s AND id = %s
                """,
                (effective_micros, reval_usd, gain_loss, tenant_id, er["id"]),
            )
            revalued_cnt += 1
    return _row_to_fx_rate(dict(rate_row)), revalued_cnt


async def list_fx_ledger_entries(
    conn: AsyncConnection, *, tenant_id: UUID
) -> list[FxLedgerEntryView]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT id, entry_number, entry_date, description, counterparty_name, currency,
                   amount_minor, entry_kind, booking_rate_micros, booked_usd_cents,
                   current_rate_micros, revalued_usd_cents, fx_gain_loss_cents, status,
                   settled_rate_micros, realized_fx_gain_loss_cents, settled_at, created_at
            FROM gba.fx_ledger_entries
            WHERE tenant_id = %s
            ORDER BY entry_date DESC, created_at DESC
            LIMIT 100
            """,
            (tenant_id,),
        )
        rows = await cur.fetchall()
    return [_row_to_fx_entry(dict(r)) for r in rows]


async def create_fx_ledger_entry(
    conn: AsyncConnection,
    *,
    tenant_id: UUID,
    description: str,
    counterparty_name: str,
    currency: CurrencyCode,
    amount_minor: int,
    entry_kind: FxEntryKind,
    booking_rate_micros: int | None,
    entry_date: date | None,
    created_by_user_id: UUID | None,
) -> FxLedgerEntryView:
    rates = await ensure_and_list_fx_rates(conn, tenant_id=tenant_id)
    rate_map = {r.base_currency: r.rate_micros for r in rates}
    current_micros = rate_map.get(currency, 1_000_000)
    book_micros = booking_rate_micros if booking_rate_micros is not None else current_micros
    booked_usd = convert_minor_to_usd_cents(amount_minor=amount_minor, rate_micros=book_micros)
    revalued_usd = convert_minor_to_usd_cents(amount_minor=amount_minor, rate_micros=current_micros)
    fx_gl = compute_fx_gain_loss_cents(
        entry_kind=entry_kind, booked_usd_cents=booked_usd, current_usd_cents=revalued_usd
    )
    entry_num = f"FX-{datetime.now(UTC).strftime('%Y%m%d')}-{secrets.token_hex(3).upper()}"
    eff_date = entry_date or datetime.now(UTC).date()

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            INSERT INTO gba.fx_ledger_entries (
                tenant_id, entry_number, entry_date, description, counterparty_name,
                currency, amount_minor, entry_kind, booking_rate_micros, booked_usd_cents,
                current_rate_micros, revalued_usd_cents, fx_gain_loss_cents, status,
                realized_fx_gain_loss_cents, created_by_user_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'open', 0, %s)
            RETURNING id, entry_number, entry_date, description, counterparty_name, currency,
                      amount_minor, entry_kind, booking_rate_micros, booked_usd_cents,
                      current_rate_micros, revalued_usd_cents, fx_gain_loss_cents, status,
                      settled_rate_micros, realized_fx_gain_loss_cents, settled_at, created_at
            """,
            (
                tenant_id,
                entry_num,
                eff_date,
                description.strip(),
                counterparty_name.strip(),
                currency,
                amount_minor,
                entry_kind,
                book_micros,
                booked_usd,
                current_micros,
                revalued_usd,
                fx_gl,
                created_by_user_id,
            ),
        )
        row = _require_row(await cur.fetchone(), "fx_ledger_entries insert")
    return _row_to_fx_entry(dict(row))


async def settle_fx_ledger_entry(
    conn: AsyncConnection,
    *,
    tenant_id: UUID,
    entry_id: UUID,
    settlement_rate_micros: int,
) -> FxLedgerEntryView:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT id, amount_minor, entry_kind, booked_usd_cents, status
            FROM gba.fx_ledger_entries
            WHERE tenant_id = %s AND id = %s
            FOR UPDATE
            """,
            (tenant_id, entry_id),
        )
        cur_row = await cur.fetchone()
        if cur_row is None:
            raise LookupError("FX ledger entry not found.")
        if cur_row["status"] == "settled":
            raise ValueError("FX ledger entry is already settled.")
        settled_usd = convert_minor_to_usd_cents(
            amount_minor=int(cur_row["amount_minor"]), rate_micros=settlement_rate_micros
        )
        realized = compute_fx_gain_loss_cents(
            entry_kind=cur_row["entry_kind"],
            booked_usd_cents=int(cur_row["booked_usd_cents"]),
            current_usd_cents=settled_usd,
        )
        await cur.execute(
            """
            UPDATE gba.fx_ledger_entries
            SET status = 'settled',
                current_rate_micros = %s,
                revalued_usd_cents = %s,
                fx_gain_loss_cents = %s,
                settled_rate_micros = %s,
                realized_fx_gain_loss_cents = %s,
                settled_at = now(),
                updated_at = now()
            WHERE tenant_id = %s AND id = %s
            RETURNING id, entry_number, entry_date, description, counterparty_name, currency,
                      amount_minor, entry_kind, booking_rate_micros, booked_usd_cents,
                      current_rate_micros, revalued_usd_cents, fx_gain_loss_cents, status,
                      settled_rate_micros, realized_fx_gain_loss_cents, settled_at, created_at
            """,
            (
                settlement_rate_micros,
                settled_usd,
                realized,
                settlement_rate_micros,
                realized,
                tenant_id,
                entry_id,
            ),
        )
        row = _require_row(await cur.fetchone(), "fx_ledger_entries settle")
    return _row_to_fx_entry(dict(row))


# ── International Tax Profiles & Local Payment Rails ─────────────────────────


async def ensure_and_list_tax_profiles(
    conn: AsyncConnection, *, tenant_id: UUID
) -> list[InternationalTaxProfileView]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT id, country_code, region_label, tax_regime, tax_name,
                   standard_rate_bps, reduced_rate_bps, reverse_charge_b2b,
                   tax_registration_id, default_currency, reporting_standard,
                   is_default, is_active
            FROM gba.international_tax_profiles
            WHERE tenant_id = %s
            ORDER BY is_default DESC, country_code ASC
            """,
            (tenant_id,),
        )
        rows = await cur.fetchall()
        if not rows:
            for (
                cc,
                reg_lbl,
                regime,
                tname,
                std_bps,
                red_bps,
                rev_chg,
                ccy,
                rep_std,
                is_def,
            ) in DEFAULT_TAX_PROFILES:
                await cur.execute(
                    """
                    INSERT INTO gba.international_tax_profiles (
                        tenant_id, country_code, region_label, tax_regime, tax_name,
                        standard_rate_bps, reduced_rate_bps, reverse_charge_b2b,
                        tax_registration_id, default_currency, reporting_standard,
                        is_default, is_active
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, '', %s, %s, %s, true)
                    ON CONFLICT (tenant_id, country_code, tax_regime) DO NOTHING
                    """,
                    (
                        tenant_id,
                        cc,
                        reg_lbl,
                        regime,
                        tname,
                        std_bps,
                        red_bps,
                        rev_chg,
                        ccy,
                        rep_std,
                        is_def,
                    ),
                )
            await cur.execute(
                """
                SELECT id, country_code, region_label, tax_regime, tax_name,
                       standard_rate_bps, reduced_rate_bps, reverse_charge_b2b,
                       tax_registration_id, default_currency, reporting_standard,
                       is_default, is_active
                FROM gba.international_tax_profiles
                WHERE tenant_id = %s
                ORDER BY is_default DESC, country_code ASC
                """,
                (tenant_id,),
            )
            rows = await cur.fetchall()
    return [_row_to_tax_profile(dict(r)) for r in rows]


async def upsert_tax_profile(
    conn: AsyncConnection,
    *,
    tenant_id: UUID,
    country_code: str,
    region_label: str,
    tax_regime: TaxRegime,
    tax_name: str,
    standard_rate_bps: int,
    reduced_rate_bps: int,
    reverse_charge_b2b: bool,
    tax_registration_id: str,
    default_currency: CurrencyCode,
    reporting_standard: ReportingStandard,
) -> InternationalTaxProfileView:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            INSERT INTO gba.international_tax_profiles (
                tenant_id, country_code, region_label, tax_regime, tax_name,
                standard_rate_bps, reduced_rate_bps, reverse_charge_b2b,
                tax_registration_id, default_currency, reporting_standard,
                is_default, is_active
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, false, true)
            ON CONFLICT (tenant_id, country_code, tax_regime) DO UPDATE SET
                region_label = EXCLUDED.region_label,
                tax_name = EXCLUDED.tax_name,
                standard_rate_bps = EXCLUDED.standard_rate_bps,
                reduced_rate_bps = EXCLUDED.reduced_rate_bps,
                reverse_charge_b2b = EXCLUDED.reverse_charge_b2b,
                tax_registration_id = EXCLUDED.tax_registration_id,
                default_currency = EXCLUDED.default_currency,
                reporting_standard = EXCLUDED.reporting_standard,
                updated_at = now()
            RETURNING id, country_code, region_label, tax_regime, tax_name,
                      standard_rate_bps, reduced_rate_bps, reverse_charge_b2b,
                      tax_registration_id, default_currency, reporting_standard,
                      is_default, is_active
            """,
            (
                tenant_id,
                country_code.strip().upper(),
                region_label.strip(),
                tax_regime,
                tax_name.strip(),
                standard_rate_bps,
                reduced_rate_bps,
                reverse_charge_b2b,
                tax_registration_id.strip(),
                default_currency,
                reporting_standard,
            ),
        )
        row = _require_row(await cur.fetchone(), "international_tax_profiles upsert")
    return _row_to_tax_profile(dict(row))


async def ensure_and_list_payment_rails(
    conn: AsyncConnection, *, tenant_id: UUID
) -> list[LocalPaymentRailView]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT id, rail_code, display_name, country_code, currency,
                   settlement_instructions, iban_or_routing_masked, is_enabled
            FROM gba.local_payment_rails
            WHERE tenant_id = %s
            ORDER BY country_code ASC, rail_code ASC
            """,
            (tenant_id,),
        )
        rows = await cur.fetchall()
        if not rows:
            for code, disp, cc, ccy, instr in DEFAULT_PAYMENT_RAILS:
                await cur.execute(
                    """
                    INSERT INTO gba.local_payment_rails (
                        tenant_id, rail_code, display_name, country_code, currency,
                        settlement_instructions, iban_or_routing_masked, is_enabled
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, '', true)
                    ON CONFLICT (tenant_id, rail_code) DO NOTHING
                    """,
                    (tenant_id, code, disp, cc, ccy, instr),
                )
            await cur.execute(
                """
                SELECT id, rail_code, display_name, country_code, currency,
                       settlement_instructions, iban_or_routing_masked, is_enabled
                FROM gba.local_payment_rails
                WHERE tenant_id = %s
                ORDER BY country_code ASC, rail_code ASC
                """,
                (tenant_id,),
            )
            rows = await cur.fetchall()
    return [_row_to_rail(dict(r)) for r in rows]


async def upsert_payment_rail(
    conn: AsyncConnection,
    *,
    tenant_id: UUID,
    rail_code: PaymentRailCode,
    display_name: str,
    country_code: str,
    currency: CurrencyCode,
    settlement_instructions: str,
    iban_or_routing_masked: str,
    is_enabled: bool,
) -> LocalPaymentRailView:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            INSERT INTO gba.local_payment_rails (
                tenant_id, rail_code, display_name, country_code, currency,
                settlement_instructions, iban_or_routing_masked, is_enabled
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, rail_code) DO UPDATE SET
                display_name = EXCLUDED.display_name,
                country_code = EXCLUDED.country_code,
                currency = EXCLUDED.currency,
                settlement_instructions = EXCLUDED.settlement_instructions,
                iban_or_routing_masked = EXCLUDED.iban_or_routing_masked,
                is_enabled = EXCLUDED.is_enabled,
                updated_at = now()
            RETURNING id, rail_code, display_name, country_code, currency,
                      settlement_instructions, iban_or_routing_masked, is_enabled
            """,
            (
                tenant_id,
                rail_code,
                display_name.strip(),
                country_code.strip().upper(),
                currency,
                settlement_instructions.strip(),
                iban_or_routing_masked.strip(),
                is_enabled,
            ),
        )
        row = _require_row(await cur.fetchone(), "local_payment_rails upsert")
    return _row_to_rail(dict(row))
