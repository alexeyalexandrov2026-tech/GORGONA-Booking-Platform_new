"""HTTP routes for AMARKAL v2.20.0: US Payroll Prep & FLSA/CA/Union Compliance,
Multi-Currency FX Ledger (Live Gain/Loss Revaluation), International Tax & Local Payment Rails.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from psycopg import errors as pg_errors
from pydantic import BaseModel, ConfigDict, Field

from gorgona_booking.api.businesses import CurrentPrincipal
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business.global_payroll_fx import (
    CurrencyCode,
    ExternalPayrollProvider,
    FilingStatus,
    FxEntryKind,
    FxEntryStatus,
    FxLedgerEntryView,
    FxRateSource,
    FxRateView,
    InternationalTaxProfileView,
    LocalPaymentRailView,
    OvertimeRule,
    PaymentRailCode,
    PayrollExportProvider,
    PayrollProfileView,
    PayrollRunLineView,
    PayrollRunStatus,
    PayrollRunView,
    PayType,
    ReportingStandard,
    TaxRegime,
    approve_or_export_payroll_run,
    calculate_international_tax,
    create_fx_ledger_entry,
    create_payroll_profile,
    create_payroll_run,
    ensure_and_list_fx_rates,
    ensure_and_list_payment_rails,
    ensure_and_list_tax_profiles,
    list_fx_ledger_entries,
    list_payroll_profiles,
    list_payroll_runs,
    settle_fx_ledger_entry,
    upsert_fx_rate,
    upsert_payment_rail,
    upsert_tax_profile,
)
from gorgona_booking.tenancy.authorization import authorized_tenant

router = APIRouter(tags=["global-payroll-fx"])


# ── US Payroll Schemas ───────────────────────────────────────────────────────


class PayrollProfileResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    employee_code: str
    full_name: str
    email: str | None = None
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
    state_tax_override_bps: int | None = None
    external_payroll_provider: ExternalPayrollProvider
    is_active: bool
    created_at: datetime


class CreatePayrollProfileRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    employee_code: str = Field(min_length=2, max_length=48)
    full_name: str = Field(min_length=2, max_length=160)
    email: str | None = Field(default=None, max_length=160)
    work_state: str = Field(default="IL", pattern=r"^[A-Za-z]{2}$")
    pay_type: PayType = "hourly"
    base_rate_cents: int = Field(ge=0, le=999_999_999)
    overtime_rule: OvertimeRule = "flsa_weekly_40"
    union_local_code: str = Field(default="", max_length=80)
    union_dues_cents: int = Field(default=0, ge=0, le=10_000_000)
    union_ot_multiplier_bps: int = Field(default=15000, ge=10000, le=30000)
    union_doubletime_bps: int = Field(default=20000, ge=15000, le=40000)
    health_insurance_pretax_cents: int = Field(default=0, ge=0, le=10_000_000)
    retirement_401k_bps: int = Field(default=0, ge=0, le=5000)
    filing_status: FilingStatus = "single"
    state_tax_override_bps: int | None = Field(default=None, ge=0, le=2000)
    external_payroll_provider: ExternalPayrollProvider = "none"


class PayrollTimeEntryInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    profile_id: UUID
    daily_hours_milli: list[int] = Field(min_length=1, max_length=14)
    bonus_cents: int = Field(default=0, ge=0, le=999_999_999)


class CreatePayrollRunRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    period_start: date
    period_end: date
    pay_date: date
    export_provider: PayrollExportProvider = "csv_adp_gusto"
    notes: str = Field(default="", max_length=1000)
    entries: list[PayrollTimeEntryInput] = Field(min_length=1, max_length=200)


class TransitionPayrollRunRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    action: Literal["approve", "export", "void"]


class PayrollRunLineResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
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


class PayrollRunResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
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
    approved_at: datetime | None = None
    notes: str
    lines: list[PayrollRunLineResponse]
    created_at: datetime


# ── FX & International Tax Schemas ───────────────────────────────────────────


class FxRateResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    base_currency: CurrencyCode
    quote_currency: str
    rate_micros: int
    source: FxRateSource
    effective_at: datetime
    updated_at: datetime


class UpsertFxRateRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    base_currency: CurrencyCode
    rate_micros: int = Field(ge=1, le=999_999_999_999)
    source: FxRateSource = "manual"


class UpsertFxRateResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    rate: FxRateResponse
    revalued_open_entries: int


class FxLedgerEntryResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
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
    settled_rate_micros: int | None = None
    realized_fx_gain_loss_cents: int
    settled_at: datetime | None = None
    created_at: datetime


class CreateFxEntryRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    description: str = Field(min_length=2, max_length=240)
    counterparty_name: str = Field(default="", max_length=160)
    currency: CurrencyCode
    amount_minor: int = Field(ge=1, le=999_999_999_999)
    entry_kind: FxEntryKind = "receivable"
    booking_rate_micros: int | None = Field(default=None, ge=1, le=999_999_999_999)
    entry_date: date | None = None


class SettleFxEntryRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    settlement_rate_micros: int = Field(ge=1, le=999_999_999_999)


class TaxProfileResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
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


class UpsertTaxProfileRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    country_code: str = Field(pattern=r"^[A-Za-z]{2}$")
    region_label: str = Field(min_length=2, max_length=120)
    tax_regime: TaxRegime
    tax_name: str = Field(min_length=2, max_length=80)
    standard_rate_bps: int = Field(ge=0, le=4000)
    reduced_rate_bps: int = Field(default=0, ge=0, le=4000)
    reverse_charge_b2b: bool = False
    tax_registration_id: str = Field(default="", max_length=64)
    default_currency: CurrencyCode = "EUR"
    reporting_standard: ReportingStandard = "IFRS_EU"


class TaxPreviewRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    profile_id: UUID
    subtotal_minor: int = Field(ge=0, le=999_999_999_999)
    is_b2b_cross_border: bool = False
    use_reduced_rate: bool = False


class TaxPreviewResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    subtotal_minor: int
    tax_minor: int
    total_minor: int
    applied_rate_bps: int
    reverse_charge_applied: bool
    tax_label: str
    reporting_standard: ReportingStandard


class PaymentRailResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    rail_code: PaymentRailCode
    display_name: str
    country_code: str
    currency: CurrencyCode
    settlement_instructions: str
    iban_or_routing_masked: str
    is_enabled: bool


class UpsertPaymentRailRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    rail_code: PaymentRailCode
    display_name: str = Field(min_length=2, max_length=120)
    country_code: str = Field(pattern=r"^[A-Za-z]{2}$")
    currency: CurrencyCode
    settlement_instructions: str = Field(default="", max_length=1000)
    iban_or_routing_masked: str = Field(default="", max_length=64)
    is_enabled: bool = True


# ── Serializers ──────────────────────────────────────────────────────────────


def _prof_resp(v: PayrollProfileView) -> PayrollProfileResponse:
    return PayrollProfileResponse(
        id=v.id,
        employee_code=v.employee_code,
        full_name=v.full_name,
        email=v.email,
        work_state=v.work_state,
        pay_type=v.pay_type,
        base_rate_cents=v.base_rate_cents,
        overtime_rule=v.overtime_rule,
        union_local_code=v.union_local_code,
        union_dues_cents=v.union_dues_cents,
        union_ot_multiplier_bps=v.union_ot_multiplier_bps,
        union_doubletime_bps=v.union_doubletime_bps,
        health_insurance_pretax_cents=v.health_insurance_pretax_cents,
        retirement_401k_bps=v.retirement_401k_bps,
        filing_status=v.filing_status,
        state_tax_override_bps=v.state_tax_override_bps,
        external_payroll_provider=v.external_payroll_provider,
        is_active=v.is_active,
        created_at=v.created_at,
    )


def _line_resp(v: PayrollRunLineView) -> PayrollRunLineResponse:
    return PayrollRunLineResponse(
        id=v.id,
        run_id=v.run_id,
        profile_id=v.profile_id,
        employee_name=v.employee_name,
        work_state=v.work_state,
        regular_hours_milli=v.regular_hours_milli,
        overtime_hours_milli=v.overtime_hours_milli,
        doubletime_hours_milli=v.doubletime_hours_milli,
        bonus_cents=v.bonus_cents,
        regular_pay_cents=v.regular_pay_cents,
        overtime_pay_cents=v.overtime_pay_cents,
        doubletime_pay_cents=v.doubletime_pay_cents,
        gross_pay_cents=v.gross_pay_cents,
        pretax_health_cents=v.pretax_health_cents,
        pretax_401k_cents=v.pretax_401k_cents,
        federal_income_tax_cents=v.federal_income_tax_cents,
        state_income_tax_cents=v.state_income_tax_cents,
        social_security_cents=v.social_security_cents,
        medicare_cents=v.medicare_cents,
        union_dues_cents=v.union_dues_cents,
        net_pay_cents=v.net_pay_cents,
        employer_fica_cents=v.employer_fica_cents,
        employer_futa_suta_cents=v.employer_futa_suta_cents,
        compliance_notes=v.compliance_notes,
    )


def _run_resp(v: PayrollRunView) -> PayrollRunResponse:
    return PayrollRunResponse(
        id=v.id,
        run_number=v.run_number,
        period_start=v.period_start,
        period_end=v.period_end,
        pay_date=v.pay_date,
        status=v.status,
        total_gross_cents=v.total_gross_cents,
        total_employee_taxes_cents=v.total_employee_taxes_cents,
        total_employer_taxes_cents=v.total_employer_taxes_cents,
        total_deductions_cents=v.total_deductions_cents,
        total_net_cents=v.total_net_cents,
        export_provider=v.export_provider,
        approved_at=v.approved_at,
        notes=v.notes,
        lines=[_line_resp(x) for x in v.lines],
        created_at=v.created_at,
    )


def _rate_resp(v: FxRateView) -> FxRateResponse:
    return FxRateResponse(
        id=v.id,
        base_currency=v.base_currency,
        quote_currency=v.quote_currency,
        rate_micros=v.rate_micros,
        source=v.source,
        effective_at=v.effective_at,
        updated_at=v.updated_at,
    )


def _fx_resp(v: FxLedgerEntryView) -> FxLedgerEntryResponse:
    return FxLedgerEntryResponse(
        id=v.id,
        entry_number=v.entry_number,
        entry_date=v.entry_date,
        description=v.description,
        counterparty_name=v.counterparty_name,
        currency=v.currency,
        amount_minor=v.amount_minor,
        entry_kind=v.entry_kind,
        booking_rate_micros=v.booking_rate_micros,
        booked_usd_cents=v.booked_usd_cents,
        current_rate_micros=v.current_rate_micros,
        revalued_usd_cents=v.revalued_usd_cents,
        fx_gain_loss_cents=v.fx_gain_loss_cents,
        status=v.status,
        settled_rate_micros=v.settled_rate_micros,
        realized_fx_gain_loss_cents=v.realized_fx_gain_loss_cents,
        settled_at=v.settled_at,
        created_at=v.created_at,
    )


def _tax_resp(v: InternationalTaxProfileView) -> TaxProfileResponse:
    return TaxProfileResponse(
        id=v.id,
        country_code=v.country_code,
        region_label=v.region_label,
        tax_regime=v.tax_regime,
        tax_name=v.tax_name,
        standard_rate_bps=v.standard_rate_bps,
        reduced_rate_bps=v.reduced_rate_bps,
        reverse_charge_b2b=v.reverse_charge_b2b,
        tax_registration_id=v.tax_registration_id,
        default_currency=v.default_currency,
        reporting_standard=v.reporting_standard,
        is_default=v.is_default,
        is_active=v.is_active,
    )


def _rail_resp(v: LocalPaymentRailView) -> PaymentRailResponse:
    return PaymentRailResponse(
        id=v.id,
        rail_code=v.rail_code,
        display_name=v.display_name,
        country_code=v.country_code,
        currency=v.currency,
        settlement_instructions=v.settlement_instructions,
        iban_or_routing_masked=v.iban_or_routing_masked,
        is_enabled=v.is_enabled,
    )


# ── US Payroll Routes ────────────────────────────────────────────────────────


@router.get(
    "/v1/businesses/{business_id}/global-finance/payroll/profiles",
    response_model=list[PayrollProfileResponse],
)
async def get_payroll_profiles(
    business_id: UUID, principal: CurrentPrincipal, request: Request
) -> list[PayrollProfileResponse]:
    pool = runtime_pool(request)
    async with authorized_tenant(
        pool,
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as session:
        items = await list_payroll_profiles(session.conn, tenant_id=business_id)
    return [_prof_resp(p) for p in items]


@router.post(
    "/v1/businesses/{business_id}/global-finance/payroll/profiles",
    response_model=PayrollProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_payroll_profile(
    business_id: UUID,
    body: CreatePayrollProfileRequest,
    principal: CurrentPrincipal,
    request: Request,
) -> PayrollProfileResponse:
    pool = runtime_pool(request)
    try:
        async with authorized_tenant(
            pool,
            principal,
            business_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            prof = await create_payroll_profile(
                session.conn,
                tenant_id=business_id,
                employee_code=body.employee_code,
                full_name=body.full_name,
                email=body.email,
                work_state=body.work_state,
                pay_type=body.pay_type,
                base_rate_cents=body.base_rate_cents,
                overtime_rule=body.overtime_rule,
                union_local_code=body.union_local_code,
                union_dues_cents=body.union_dues_cents,
                union_ot_multiplier_bps=body.union_ot_multiplier_bps,
                union_doubletime_bps=body.union_doubletime_bps,
                health_insurance_pretax_cents=body.health_insurance_pretax_cents,
                retirement_401k_bps=body.retirement_401k_bps,
                filing_status=body.filing_status,
                state_tax_override_bps=body.state_tax_override_bps,
                external_payroll_provider=body.external_payroll_provider,
            )
    except pg_errors.UniqueViolation as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An employee profile with this employee code already exists.",
        ) from exc
    return _prof_resp(prof)


@router.get(
    "/v1/businesses/{business_id}/global-finance/payroll/runs",
    response_model=list[PayrollRunResponse],
)
async def get_payroll_runs(
    business_id: UUID, principal: CurrentPrincipal, request: Request
) -> list[PayrollRunResponse]:
    pool = runtime_pool(request)
    async with authorized_tenant(
        pool,
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as session:
        items = await list_payroll_runs(session.conn, tenant_id=business_id)
    return [_run_resp(r) for r in items]


@router.post(
    "/v1/businesses/{business_id}/global-finance/payroll/runs",
    response_model=PayrollRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_payroll_run(
    business_id: UUID,
    body: CreatePayrollRunRequest,
    principal: CurrentPrincipal,
    request: Request,
) -> PayrollRunResponse:
    pool = runtime_pool(request)
    try:
        async with authorized_tenant(
            pool,
            principal,
            business_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            run = await create_payroll_run(
                session.conn,
                tenant_id=business_id,
                period_start=body.period_start,
                period_end=body.period_end,
                pay_date=body.pay_date,
                export_provider=body.export_provider,
                notes=body.notes,
                entries=[(e.profile_id, e.daily_hours_milli, e.bonus_cents) for e in body.entries],
                created_by_user_id=principal.user_id,
            )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return _run_resp(run)


@router.post(
    "/v1/businesses/{business_id}/global-finance/payroll/runs/{run_id}/transition",
    response_model=PayrollRunResponse,
)
async def post_transition_payroll_run(
    business_id: UUID,
    run_id: UUID,
    body: TransitionPayrollRunRequest,
    principal: CurrentPrincipal,
    request: Request,
) -> PayrollRunResponse:
    pool = runtime_pool(request)
    try:
        async with authorized_tenant(
            pool,
            principal,
            business_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            run = await approve_or_export_payroll_run(
                session.conn,
                tenant_id=business_id,
                run_id=run_id,
                action=body.action,
                actor_user_id=principal.user_id,
            )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _run_resp(run)


# ── Multi-Currency FX Rates & Ledger Routes ──────────────────────────────────


@router.get(
    "/v1/businesses/{business_id}/global-finance/fx/rates",
    response_model=list[FxRateResponse],
)
async def get_fx_rates(
    business_id: UUID, principal: CurrentPrincipal, request: Request
) -> list[FxRateResponse]:
    pool = runtime_pool(request)
    async with authorized_tenant(
        pool,
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as session:
        items = await ensure_and_list_fx_rates(session.conn, tenant_id=business_id)
    return [_rate_resp(r) for r in items]


@router.put(
    "/v1/businesses/{business_id}/global-finance/fx/rates",
    response_model=UpsertFxRateResponse,
)
async def put_fx_rate(
    business_id: UUID,
    body: UpsertFxRateRequest,
    principal: CurrentPrincipal,
    request: Request,
) -> UpsertFxRateResponse:
    pool = runtime_pool(request)
    async with authorized_tenant(
        pool,
        principal,
        business_id,
        Permission.BUSINESS_MANAGE,
        request_id=get_request_id(request),
    ) as session:
        rate, revalued = await upsert_fx_rate(
            session.conn,
            tenant_id=business_id,
            base_currency=body.base_currency,
            rate_micros=body.rate_micros,
            source=body.source,
        )
    return UpsertFxRateResponse(rate=_rate_resp(rate), revalued_open_entries=revalued)


@router.get(
    "/v1/businesses/{business_id}/global-finance/fx/entries",
    response_model=list[FxLedgerEntryResponse],
)
async def get_fx_entries(
    business_id: UUID, principal: CurrentPrincipal, request: Request
) -> list[FxLedgerEntryResponse]:
    pool = runtime_pool(request)
    async with authorized_tenant(
        pool,
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as session:
        items = await list_fx_ledger_entries(session.conn, tenant_id=business_id)
    return [_fx_resp(e) for e in items]


@router.post(
    "/v1/businesses/{business_id}/global-finance/fx/entries",
    response_model=FxLedgerEntryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_fx_entry(
    business_id: UUID,
    body: CreateFxEntryRequest,
    principal: CurrentPrincipal,
    request: Request,
) -> FxLedgerEntryResponse:
    pool = runtime_pool(request)
    async with authorized_tenant(
        pool,
        principal,
        business_id,
        Permission.BUSINESS_MANAGE,
        request_id=get_request_id(request),
    ) as session:
        entry = await create_fx_ledger_entry(
            session.conn,
            tenant_id=business_id,
            description=body.description,
            counterparty_name=body.counterparty_name,
            currency=body.currency,
            amount_minor=body.amount_minor,
            entry_kind=body.entry_kind,
            booking_rate_micros=body.booking_rate_micros,
            entry_date=body.entry_date,
            created_by_user_id=principal.user_id,
        )
    return _fx_resp(entry)


@router.post(
    "/v1/businesses/{business_id}/global-finance/fx/entries/{entry_id}/settle",
    response_model=FxLedgerEntryResponse,
)
async def post_settle_fx_entry(
    business_id: UUID,
    entry_id: UUID,
    body: SettleFxEntryRequest,
    principal: CurrentPrincipal,
    request: Request,
) -> FxLedgerEntryResponse:
    pool = runtime_pool(request)
    try:
        async with authorized_tenant(
            pool,
            principal,
            business_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            entry = await settle_fx_ledger_entry(
                session.conn,
                tenant_id=business_id,
                entry_id=entry_id,
                settlement_rate_micros=body.settlement_rate_micros,
            )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _fx_resp(entry)


# ── International Tax Profiles & Local Payment Rails ─────────────────────────


@router.get(
    "/v1/businesses/{business_id}/global-finance/tax-profiles",
    response_model=list[TaxProfileResponse],
)
async def get_tax_profiles(
    business_id: UUID, principal: CurrentPrincipal, request: Request
) -> list[TaxProfileResponse]:
    pool = runtime_pool(request)
    async with authorized_tenant(
        pool,
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as session:
        items = await ensure_and_list_tax_profiles(session.conn, tenant_id=business_id)
    return [_tax_resp(t) for t in items]


@router.put(
    "/v1/businesses/{business_id}/global-finance/tax-profiles",
    response_model=TaxProfileResponse,
)
async def put_tax_profile(
    business_id: UUID,
    body: UpsertTaxProfileRequest,
    principal: CurrentPrincipal,
    request: Request,
) -> TaxProfileResponse:
    pool = runtime_pool(request)
    async with authorized_tenant(
        pool,
        principal,
        business_id,
        Permission.BUSINESS_MANAGE,
        request_id=get_request_id(request),
    ) as session:
        prof = await upsert_tax_profile(
            session.conn,
            tenant_id=business_id,
            country_code=body.country_code,
            region_label=body.region_label,
            tax_regime=body.tax_regime,
            tax_name=body.tax_name,
            standard_rate_bps=body.standard_rate_bps,
            reduced_rate_bps=body.reduced_rate_bps,
            reverse_charge_b2b=body.reverse_charge_b2b,
            tax_registration_id=body.tax_registration_id,
            default_currency=body.default_currency,
            reporting_standard=body.reporting_standard,
        )
    return _tax_resp(prof)


@router.post(
    "/v1/businesses/{business_id}/global-finance/tax-preview",
    response_model=TaxPreviewResponse,
)
async def post_tax_preview(
    business_id: UUID,
    body: TaxPreviewRequest,
    principal: CurrentPrincipal,
    request: Request,
) -> TaxPreviewResponse:
    pool = runtime_pool(request)
    async with authorized_tenant(
        pool,
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as session:
        profiles = await ensure_and_list_tax_profiles(session.conn, tenant_id=business_id)
    target = next((p for p in profiles if p.id == body.profile_id), None)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tax profile not found.")
    res = calculate_international_tax(
        profile=target,
        subtotal_minor=body.subtotal_minor,
        is_b2b_cross_border=body.is_b2b_cross_border,
        use_reduced_rate=body.use_reduced_rate,
    )
    return TaxPreviewResponse(
        subtotal_minor=res.subtotal_minor,
        tax_minor=res.tax_minor,
        total_minor=res.total_minor,
        applied_rate_bps=res.applied_rate_bps,
        reverse_charge_applied=res.reverse_charge_applied,
        tax_label=res.tax_label,
        reporting_standard=res.reporting_standard,
    )


@router.get(
    "/v1/businesses/{business_id}/global-finance/payment-rails",
    response_model=list[PaymentRailResponse],
)
async def get_payment_rails(
    business_id: UUID, principal: CurrentPrincipal, request: Request
) -> list[PaymentRailResponse]:
    pool = runtime_pool(request)
    async with authorized_tenant(
        pool,
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as session:
        items = await ensure_and_list_payment_rails(session.conn, tenant_id=business_id)
    return [_rail_resp(r) for r in items]


@router.put(
    "/v1/businesses/{business_id}/global-finance/payment-rails",
    response_model=PaymentRailResponse,
)
async def put_payment_rail(
    business_id: UUID,
    body: UpsertPaymentRailRequest,
    principal: CurrentPrincipal,
    request: Request,
) -> PaymentRailResponse:
    pool = runtime_pool(request)
    async with authorized_tenant(
        pool,
        principal,
        business_id,
        Permission.BUSINESS_MANAGE,
        request_id=get_request_id(request),
    ) as session:
        rail = await upsert_payment_rail(
            session.conn,
            tenant_id=business_id,
            rail_code=body.rail_code,
            display_name=body.display_name,
            country_code=body.country_code,
            currency=body.currency,
            settlement_instructions=body.settlement_instructions,
            iban_or_routing_masked=body.iban_or_routing_masked,
            is_enabled=body.is_enabled,
        )
    return _rail_resp(rail)
