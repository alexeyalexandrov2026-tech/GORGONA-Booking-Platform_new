"""AMARKAL v2.27.0: Holding Multi-Entity & Intercompany Consolidation API.

Security & accounting invariants:
- Strictly additive under PostgreSQL 18 `ENABLE + FORCE ROW LEVEL SECURITY`; zero
  modifications to existing `legal_entities` or `enterprise_reporting` endpoints.
- Supports unlimited domestic & international subsidiaries per holding account with
  functional currency FX translation into reporting currency (USD) using live tenant
  `gba.fx_rates` (with deterministic ECB / Fed H.10 reference defaults).
- Automatically generates mirrored Due To / Due From intercompany entries, computes
  US GAAP / IFRS consolidated P&L and Balance Sheet with full intercompany eliminations,
  attributes Non-Controlling Interest (NCI) whenever ownership < 100%, and outputs the
  net intercompany cash settlement matrix.
"""

from __future__ import annotations

import re
import secrets
from collections import defaultdict
from datetime import UTC, date, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status
from psycopg import errors as pg_errors
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, Field

from gorgona_booking.api.businesses import CurrentPrincipal
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.tenancy.authorization import authorized_tenant

router = APIRouter(tags=["holding-consolidation"])

EntityRole = Literal["parent_holding", "operating_subsidiary", "spv", "regional_branch"]
CurrencyCode = Literal["USD", "EUR", "GBP", "CAD", "MXN", "CHF", "AUD", "JPY"]
IntercompanyTxKind = Literal[
    "intercompany_service",
    "inventory_transfer",
    "management_fee",
    "intercompany_loan",
    "cost_allocation",
    "dividend",
]
IntercompanyStatus = Literal["posted", "eliminated", "void"]

_CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")

# Reference rate_micros (1 unit of functional currency -> USD * 1_000_000)
DEFAULT_FX_RATE_MICROS: dict[str, int] = {
    "USD": 1_000_000,
    "EUR": 1_090_000,
    "GBP": 1_270_000,
    "CAD": 725_000,
    "MXN": 52_000,
    "CHF": 1_130_000,
    "AUD": 655_000,
    "JPY": 6_600,
}


class SubsidiaryView(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    entity_code: str
    legal_name: str
    entity_role: EntityRole
    jurisdiction_country: str
    jurisdiction_state: str
    functional_currency: CurrencyCode
    ownership_bps: int
    tax_id_masked: str
    is_active: bool
    created_at: datetime


class EntitySnapshotView(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    subsidiary_id: UUID
    period_key: str
    revenue_minor: int
    cogs_minor: int
    opex_minor: int
    cash_minor: int
    ar_minor: int
    ap_minor: int
    inventory_minor: int
    fixed_assets_minor: int
    debt_minor: int
    equity_minor: int
    notes: str
    updated_at: datetime


class IntercompanyTxView(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    tx_number: str
    period_key: str
    tx_date: date
    source_subsidiary_id: UUID
    source_code: str
    source_name: str
    target_subsidiary_id: UUID
    target_code: str
    target_name: str
    tx_kind: IntercompanyTxKind
    currency: CurrencyCode
    amount_minor: int
    fx_rate_micros: int
    usd_equivalent_cents: int
    description: str
    source_entry_label: str
    target_entry_label: str
    status: IntercompanyStatus
    eliminated_at: datetime | None


class EntityConsolidatedRow(BaseModel):
    model_config = ConfigDict(frozen=True)
    subsidiary_id: str
    entity_code: str
    legal_name: str
    entity_role: EntityRole
    jurisdiction: str
    functional_currency: CurrencyCode
    fx_rate_micros: int
    ownership_pct: float
    revenue_usd_cents: int
    cogs_usd_cents: int
    opex_usd_cents: int
    net_income_usd_cents: int
    controlling_net_income_cents: int
    nci_net_income_cents: int
    cash_usd_cents: int
    total_assets_usd_cents: int
    total_liabilities_usd_cents: int
    equity_usd_cents: int


class ConsolidatedStatementColumn(BaseModel):
    model_config = ConfigDict(frozen=True)
    revenue_cents: int
    cogs_cents: int
    gross_profit_cents: int
    opex_cents: int
    net_income_cents: int
    controlling_interest_net_income_cents: int
    nci_net_income_cents: int
    cash_cents: int
    ar_cents: int
    inventory_cents: int
    fixed_assets_cents: int
    total_assets_cents: int
    ap_cents: int
    debt_cents: int
    total_liabilities_cents: int
    equity_cents: int


class DueToDueFromPair(BaseModel):
    model_config = ConfigDict(frozen=True)
    creditor_code: str
    creditor_name: str
    debtor_code: str
    debtor_name: str
    net_due_usd_cents: int
    tx_count: int


class HoldingOverviewResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    period_key: str
    reporting_currency: Literal["USD"]
    subsidiaries: list[SubsidiaryView]
    snapshots: list[EntitySnapshotView]
    intercompany_transactions: list[IntercompanyTxView]
    per_entity_usd: list[EntityConsolidatedRow]
    pre_elimination: ConsolidatedStatementColumn
    eliminations: ConsolidatedStatementColumn
    consolidated: ConsolidatedStatementColumn
    due_to_due_from_matrix: list[DueToDueFromPair]
    fx_rates_micros: dict[str, int]


class CreateSubsidiaryRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    entity_code: str = Field(min_length=2, max_length=32, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    legal_name: str = Field(min_length=2, max_length=200)
    entity_role: EntityRole = "operating_subsidiary"
    jurisdiction_country: str = Field(default="US", pattern=r"^[A-Za-z]{2}$")
    jurisdiction_state: str = Field(default="", max_length=40)
    functional_currency: CurrencyCode = "USD"
    ownership_bps: int = Field(default=10000, ge=0, le=10000)
    tax_id_masked: str = Field(default="", max_length=48)


class UpsertEntitySnapshotRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    subsidiary_id: UUID
    period_key: str = Field(pattern=r"^[0-9]{4}-[0-9]{2}$")
    revenue_minor: int = Field(default=0, ge=0)
    cogs_minor: int = Field(default=0, ge=0)
    opex_minor: int = Field(default=0, ge=0)
    cash_minor: int = Field(default=0)
    ar_minor: int = Field(default=0, ge=0)
    ap_minor: int = Field(default=0, ge=0)
    inventory_minor: int = Field(default=0, ge=0)
    fixed_assets_minor: int = Field(default=0, ge=0)
    debt_minor: int = Field(default=0, ge=0)
    equity_minor: int = Field(default=0)
    notes: str = Field(default="", max_length=500)


class CreateIntercompanyTxRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    period_key: str = Field(pattern=r"^[0-9]{4}-[0-9]{2}$")
    tx_date: date | None = None
    source_subsidiary_id: UUID
    target_subsidiary_id: UUID
    tx_kind: IntercompanyTxKind = "intercompany_service"
    currency: CurrencyCode = "USD"
    amount_minor: int = Field(ge=1, le=999_999_999_999)
    description: str = Field(min_length=2, max_length=240)
    auto_eliminate: bool = True


class UpdateIntercompanyStatusRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    status: IntercompanyStatus


class SeedSampleHoldingResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    period_key: str
    subsidiaries_seeded: int
    snapshots_seeded: int
    intercompany_seeded: int
    message: str


def _clean(val: str | None, *, max_len: int = 200) -> str:
    return re.sub(r"\s+", " ", _CTRL_RE.sub(" ", val or "")).strip()[:max_len]


def convert_minor_to_usd_cents(amount_minor: int, currency: str, rate_micros: int) -> int:
    """Convert functional-currency minor units into USD cents via rate_micros.

    Note: JPY has 0 minor decimals (1 JPY = 1 minor unit), whereas USD/EUR/GBP/CAD/MXN/CHF/AUD
    have 2 minor decimals (100 minor units = 1 major unit).
    """
    ccy = currency.upper()
    if ccy == "USD":
        return int(amount_minor)
    if ccy == "JPY":
        # amount_minor is whole JPY -> USD cents = JPY * (rate_micros / 1_000_000) * 100
        return round((amount_minor * rate_micros) / 10_000)
    return round((amount_minor * rate_micros) / 1_000_000)


def mirrored_entry_labels(tx_kind: IntercompanyTxKind) -> tuple[str, str]:
    """Return canonical double-entry Due From / Due To labels for both entities."""
    if tx_kind == "intercompany_loan":
        return (
            "DR Intercompany Loan Receivable (Due From) / CR Cash",
            "DR Cash / CR Intercompany Loan Payable (Due To)",
        )
    if tx_kind == "inventory_transfer":
        return (
            "DR Intercompany AR (Due From) / CR Intercompany Sales",
            "DR Intercompany COGS / Inventory / CR Intercompany AP (Due To)",
        )
    if tx_kind == "management_fee":
        return (
            "DR Intercompany AR (Due From) / CR Management Fee Revenue",
            "DR Management Fee Expense / CR Intercompany AP (Due To)",
        )
    if tx_kind == "dividend":
        return (
            "DR Intercompany Dividend Receivable / CR Dividend Income",
            "DR Retained Earnings (Dividend Declared) / CR Dividend Payable",
        )
    if tx_kind == "cost_allocation":
        return (
            "DR Intercompany AR (Due From) / CR Shared Services Recovery",
            "DR Allocated OpEx / CR Intercompany AP (Due To)",
        )
    return (
        "DR Intercompany AR (Due From) / CR Intercompany Service Revenue",
        "DR Intercompany Service Expense / CR Intercompany AP (Due To)",
    )


def compute_consolidated_holding(
    *,
    subsidiaries: list[dict[str, Any]],
    snapshots: list[dict[str, Any]],
    intercompany_txs: list[dict[str, Any]],
    fx_rates_micros: dict[str, int],
) -> tuple[
    list[EntityConsolidatedRow],
    ConsolidatedStatementColumn,
    ConsolidatedStatementColumn,
    ConsolidatedStatementColumn,
    list[DueToDueFromPair],
]:
    """Compute US GAAP / IFRS multi-entity consolidation, eliminations, NCI, and Due To/From."""
    snap_by_sub = {str(s["subsidiary_id"]): s for s in snapshots}
    sub_by_id = {str(s["id"]): s for s in subsidiaries}

    per_entity: list[EntityConsolidatedRow] = []

    pre_rev = pre_cogs = pre_opex = pre_cash = pre_ar = pre_inv = pre_fa = 0
    pre_ap = pre_debt = pre_eq = 0
    pre_ctrl_ni = pre_nci_ni = 0

    for sub in subsidiaries:
        sid = str(sub["id"])
        ccy = str(sub["functional_currency"]).upper()
        rate = int(fx_rates_micros.get(ccy, DEFAULT_FX_RATE_MICROS.get(ccy, 1_000_000)))
        own_bps = max(0, min(10_000, int(sub.get("ownership_bps", 10_000))))
        snap = snap_by_sub.get(sid, {})

        rev = convert_minor_to_usd_cents(int(snap.get("revenue_minor", 0)), ccy, rate)
        cogs = convert_minor_to_usd_cents(int(snap.get("cogs_minor", 0)), ccy, rate)
        opex = convert_minor_to_usd_cents(int(snap.get("opex_minor", 0)), ccy, rate)
        ni = rev - cogs - opex
        ctrl_ni = round((ni * own_bps) / 10_000)
        nci_ni = ni - ctrl_ni

        cash = convert_minor_to_usd_cents(int(snap.get("cash_minor", 0)), ccy, rate)
        ar = convert_minor_to_usd_cents(int(snap.get("ar_minor", 0)), ccy, rate)
        inv = convert_minor_to_usd_cents(int(snap.get("inventory_minor", 0)), ccy, rate)
        fa = convert_minor_to_usd_cents(int(snap.get("fixed_assets_minor", 0)), ccy, rate)
        ap = convert_minor_to_usd_cents(int(snap.get("ap_minor", 0)), ccy, rate)
        debt = convert_minor_to_usd_cents(int(snap.get("debt_minor", 0)), ccy, rate)
        eq = convert_minor_to_usd_cents(int(snap.get("equity_minor", 0)), ccy, rate)

        tot_assets = cash + ar + inv + fa
        tot_liab = ap + debt

        pre_rev += rev
        pre_cogs += cogs
        pre_opex += opex
        pre_ctrl_ni += ctrl_ni
        pre_nci_ni += nci_ni
        pre_cash += cash
        pre_ar += ar
        pre_inv += inv
        pre_fa += fa
        pre_ap += ap
        pre_debt += debt
        pre_eq += eq

        country = str(sub.get("jurisdiction_country") or "US")
        state = str(sub.get("jurisdiction_state") or "").strip()
        jurisdiction = f"{country}-{state}" if state else country

        per_entity.append(
            EntityConsolidatedRow(
                subsidiary_id=sid,
                entity_code=str(sub["entity_code"]),
                legal_name=str(sub["legal_name"]),
                entity_role=sub["entity_role"],
                jurisdiction=jurisdiction,
                functional_currency=sub["functional_currency"],
                fx_rate_micros=rate,
                ownership_pct=round(own_bps / 100.0, 2),
                revenue_usd_cents=rev,
                cogs_usd_cents=cogs,
                opex_usd_cents=opex,
                net_income_usd_cents=ni,
                controlling_net_income_cents=ctrl_ni,
                nci_net_income_cents=nci_ni,
                cash_usd_cents=cash,
                total_assets_usd_cents=tot_assets,
                total_liabilities_usd_cents=tot_liab,
                equity_usd_cents=eq,
            )
        )

    # Eliminations and bilateral Due To / Due From matrix
    elim_rev = elim_cogs = elim_opex = elim_ar = elim_ap = elim_debt = elim_eq = 0
    pair_net: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: {"net": 0, "count": 0})

    for tx in intercompany_txs:
        tx_status = str(tx.get("status") or "eliminated")
        if tx_status == "void":
            continue
        usd = max(0, int(tx.get("usd_equivalent_cents") or 0))
        kind = str(tx.get("tx_kind") or "intercompany_service")
        src_id = str(tx["source_subsidiary_id"])
        tgt_id = str(tx["target_subsidiary_id"])

        # Track bilateral Due From (src) -> Due To (tgt) across posted & eliminated active items
        pair_key = (src_id, tgt_id) if src_id < tgt_id else (tgt_id, src_id)
        sign = 1 if src_id < tgt_id else -1
        pair_net[pair_key]["net"] += sign * usd
        pair_net[pair_key]["count"] += 1

        if tx_status != "eliminated":
            continue

        if kind == "intercompany_loan":
            elim_ar += usd
            elim_debt += usd
        elif kind == "inventory_transfer":
            elim_rev += usd
            elim_cogs += usd
            elim_ar += usd
            elim_ap += usd
        elif kind == "dividend":
            elim_rev += usd
            elim_eq += usd
            elim_ar += usd
            elim_ap += usd
        else:
            # intercompany_service, management_fee, cost_allocation
            elim_rev += usd
            elim_opex += usd
            elim_ar += usd
            elim_ap += usd

    pre_gp = pre_rev - pre_cogs
    pre_ni = pre_gp - pre_opex
    pre_assets = pre_cash + pre_ar + pre_inv + pre_fa
    pre_liab = pre_ap + pre_debt

    pre_col = ConsolidatedStatementColumn(
        revenue_cents=pre_rev,
        cogs_cents=pre_cogs,
        gross_profit_cents=pre_gp,
        opex_cents=pre_opex,
        net_income_cents=pre_ni,
        controlling_interest_net_income_cents=pre_ctrl_ni,
        nci_net_income_cents=pre_nci_ni,
        cash_cents=pre_cash,
        ar_cents=pre_ar,
        inventory_cents=pre_inv,
        fixed_assets_cents=pre_fa,
        total_assets_cents=pre_assets,
        ap_cents=pre_ap,
        debt_cents=pre_debt,
        total_liabilities_cents=pre_liab,
        equity_cents=pre_eq,
    )

    elim_gp = -(elim_rev - elim_cogs)
    elim_ni = elim_gp + elim_opex
    elim_assets = -elim_ar
    elim_liab = -(elim_ap + elim_debt)

    elim_col = ConsolidatedStatementColumn(
        revenue_cents=-elim_rev,
        cogs_cents=-elim_cogs,
        gross_profit_cents=elim_gp,
        opex_cents=-elim_opex,
        net_income_cents=elim_ni,
        controlling_interest_net_income_cents=elim_ni,
        nci_net_income_cents=0,
        cash_cents=0,
        ar_cents=-elim_ar,
        inventory_cents=0,
        fixed_assets_cents=0,
        total_assets_cents=elim_assets,
        ap_cents=-elim_ap,
        debt_cents=-elim_debt,
        total_liabilities_cents=elim_liab,
        equity_cents=-elim_eq,
    )

    cons_rev = pre_rev - elim_rev
    cons_cogs = pre_cogs - elim_cogs
    cons_gp = cons_rev - cons_cogs
    cons_opex = pre_opex - elim_opex
    cons_ni = cons_gp - cons_opex
    cons_ctrl_ni = pre_ctrl_ni + elim_ni
    cons_ar = max(0, pre_ar - elim_ar)
    cons_ap = max(0, pre_ap - elim_ap)
    cons_debt = max(0, pre_debt - elim_debt)
    cons_assets = pre_cash + cons_ar + pre_inv + pre_fa
    cons_liab = cons_ap + cons_debt
    cons_eq = pre_eq - elim_eq

    cons_col = ConsolidatedStatementColumn(
        revenue_cents=cons_rev,
        cogs_cents=cons_cogs,
        gross_profit_cents=cons_gp,
        opex_cents=cons_opex,
        net_income_cents=cons_ni,
        controlling_interest_net_income_cents=cons_ctrl_ni,
        nci_net_income_cents=pre_nci_ni,
        cash_cents=pre_cash,
        ar_cents=cons_ar,
        inventory_cents=pre_inv,
        fixed_assets_cents=pre_fa,
        total_assets_cents=cons_assets,
        ap_cents=cons_ap,
        debt_cents=cons_debt,
        total_liabilities_cents=cons_liab,
        equity_cents=cons_eq,
    )

    matrix: list[DueToDueFromPair] = []
    for (a_id, b_id), info in pair_net.items():
        net_val = info["net"]
        if net_val == 0:
            continue
        cred_id, debt_id = (a_id, b_id) if net_val > 0 else (b_id, a_id)
        creditor = sub_by_id.get(cred_id)
        debtor = sub_by_id.get(debt_id)
        if creditor and debtor:
            matrix.append(
                DueToDueFromPair(
                    creditor_code=str(creditor["entity_code"]),
                    creditor_name=str(creditor["legal_name"]),
                    debtor_code=str(debtor["entity_code"]),
                    debtor_name=str(debtor["legal_name"]),
                    net_due_usd_cents=abs(net_val),
                    tx_count=info["count"],
                )
            )
    matrix.sort(key=lambda m: m.net_due_usd_cents, reverse=True)

    return per_entity, pre_col, elim_col, cons_col, matrix


async def _load_fx_rates(cur: Any, business_id: UUID) -> dict[str, int]:
    rates = dict(DEFAULT_FX_RATE_MICROS)
    await cur.execute(
        """
        SELECT base_currency, rate_micros
        FROM gba.fx_rates
        WHERE tenant_id = %s AND quote_currency = 'USD'
        """,
        (business_id,),
    )
    for row in await cur.fetchall():
        rates[str(row["base_currency"]).upper()] = int(row["rate_micros"])
    return rates


@router.get(
    "/v1/businesses/{business_id}/holding/overview",
    response_model=HoldingOverviewResponse,
)
async def get_holding_overview(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    period_key: Annotated[str | None, Query(pattern=r"^[0-9]{4}-[0-9]{2}$")] = None,
) -> HoldingOverviewResponse:
    """Return subsidiaries, snapshots, Due To/From ledger, and consolidated USD P&L/BS."""
    eff_period = period_key or datetime.now(UTC).strftime("%Y-%m")

    async with (
        authorized_tenant(
            runtime_pool(request),
            principal,
            business_id,
            Permission.BUSINESS_READ,
            request_id=get_request_id(request),
        ) as session,
        session.conn.cursor(row_factory=dict_row) as cur,
    ):
        fx_rates = await _load_fx_rates(cur, business_id)

        await cur.execute(
            """
            SELECT id, entity_code, legal_name, entity_role, jurisdiction_country,
                   jurisdiction_state, functional_currency, ownership_bps,
                   tax_id_masked, is_active, created_at
            FROM gba.holding_subsidiaries
            WHERE tenant_id = %s
            ORDER BY CASE entity_role WHEN 'parent_holding' THEN 0 ELSE 1 END, entity_code ASC
            """,
            (business_id,),
        )
        sub_rows = [dict(r) for r in await cur.fetchall()]

        await cur.execute(
            """
            SELECT id, subsidiary_id, period_key, revenue_minor, cogs_minor, opex_minor,
                   cash_minor, ar_minor, ap_minor, inventory_minor, fixed_assets_minor,
                   debt_minor, equity_minor, notes, updated_at
            FROM gba.holding_entity_trial_snapshots
            WHERE tenant_id = %s AND period_key = %s
            """,
            (business_id, eff_period),
        )
        snap_rows = [dict(r) for r in await cur.fetchall()]

        await cur.execute(
            """
            SELECT t.id, t.tx_number, t.period_key, t.tx_date,
                   t.source_subsidiary_id,
                   s.entity_code AS source_code,
                   s.legal_name AS source_name,
                   t.target_subsidiary_id,
                   d.entity_code AS target_code,
                   d.legal_name AS target_name,
                   t.tx_kind, t.currency, t.amount_minor, t.fx_rate_micros,
                   t.usd_equivalent_cents, t.description,
                   t.source_entry_label, t.target_entry_label,
                   t.status, t.eliminated_at
            FROM gba.intercompany_transactions t
            JOIN gba.holding_subsidiaries s
              ON s.tenant_id = t.tenant_id AND s.id = t.source_subsidiary_id
            JOIN gba.holding_subsidiaries d
              ON d.tenant_id = t.tenant_id AND d.id = t.target_subsidiary_id
            WHERE t.tenant_id = %s AND t.period_key = %s
            ORDER BY t.tx_date DESC, t.created_at DESC
            """,
            (business_id, eff_period),
        )
        ic_rows = [dict(r) for r in await cur.fetchall()]

    per_entity, pre_col, elim_col, cons_col, matrix = compute_consolidated_holding(
        subsidiaries=sub_rows,
        snapshots=snap_rows,
        intercompany_txs=ic_rows,
        fx_rates_micros=fx_rates,
    )

    return HoldingOverviewResponse(
        period_key=eff_period,
        reporting_currency="USD",
        subsidiaries=[SubsidiaryView(**r) for r in sub_rows],
        snapshots=[EntitySnapshotView(**r) for r in snap_rows],
        intercompany_transactions=[IntercompanyTxView(**r) for r in ic_rows],
        per_entity_usd=per_entity,
        pre_elimination=pre_col,
        eliminations=elim_col,
        consolidated=cons_col,
        due_to_due_from_matrix=matrix,
        fx_rates_micros=fx_rates,
    )


@router.post(
    "/v1/businesses/{business_id}/holding/subsidiaries",
    response_model=SubsidiaryView,
    status_code=status.HTTP_201_CREATED,
)
async def create_subsidiary(
    business_id: UUID,
    body: CreateSubsidiaryRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> SubsidiaryView:
    """Register a parent holding or domestic/international subsidiary under FORCE RLS."""
    code = body.entity_code.strip().upper()
    country = body.jurisdiction_country.strip().upper()

    async with (
        authorized_tenant(
            runtime_pool(request),
            principal,
            business_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session,
        session.conn.cursor(row_factory=dict_row) as cur,
    ):
        try:
            await cur.execute(
                """
                INSERT INTO gba.holding_subsidiaries (
                    tenant_id, entity_code, legal_name, entity_role,
                    jurisdiction_country, jurisdiction_state, functional_currency,
                    ownership_bps, tax_id_masked, created_by_user_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, entity_code, legal_name, entity_role, jurisdiction_country,
                          jurisdiction_state, functional_currency, ownership_bps,
                          tax_id_masked, is_active, created_at
                """,
                (
                    business_id,
                    code,
                    _clean(body.legal_name, max_len=200),
                    body.entity_role,
                    country,
                    _clean(body.jurisdiction_state, max_len=40),
                    body.functional_currency,
                    body.ownership_bps,
                    _clean(body.tax_id_masked, max_len=48),
                    session.principal.user_id,
                ),
            )
            row = await cur.fetchone()
        except pg_errors.UniqueViolation as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Subsidiary entity code '{code}' already exists.",
            ) from exc

    if row is None:
        raise HTTPException(status_code=500, detail="Failed to register subsidiary.")
    return SubsidiaryView(**row)


@router.post(
    "/v1/businesses/{business_id}/holding/snapshots",
    response_model=EntitySnapshotView,
)
async def upsert_entity_snapshot(
    business_id: UUID,
    body: UpsertEntitySnapshotRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> EntitySnapshotView:
    """Save or update a subsidiary's period P&L and Balance Sheet snapshot."""
    async with (
        authorized_tenant(
            runtime_pool(request),
            principal,
            business_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session,
        session.conn.cursor(row_factory=dict_row) as cur,
    ):
        await cur.execute(
            "SELECT id FROM gba.holding_subsidiaries WHERE tenant_id = %s AND id = %s",
            (business_id, body.subsidiary_id),
        )
        if await cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="Subsidiary not found.")

        await cur.execute(
            """
            INSERT INTO gba.holding_entity_trial_snapshots (
                tenant_id, subsidiary_id, period_key, revenue_minor, cogs_minor, opex_minor,
                cash_minor, ar_minor, ap_minor, inventory_minor, fixed_assets_minor,
                debt_minor, equity_minor, notes, updated_by_user_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, subsidiary_id, period_key) DO UPDATE SET
                revenue_minor = EXCLUDED.revenue_minor,
                cogs_minor = EXCLUDED.cogs_minor,
                opex_minor = EXCLUDED.opex_minor,
                cash_minor = EXCLUDED.cash_minor,
                ar_minor = EXCLUDED.ar_minor,
                ap_minor = EXCLUDED.ap_minor,
                inventory_minor = EXCLUDED.inventory_minor,
                fixed_assets_minor = EXCLUDED.fixed_assets_minor,
                debt_minor = EXCLUDED.debt_minor,
                equity_minor = EXCLUDED.equity_minor,
                notes = EXCLUDED.notes,
                updated_by_user_id = EXCLUDED.updated_by_user_id,
                updated_at = now()
            RETURNING id, subsidiary_id, period_key, revenue_minor, cogs_minor, opex_minor,
                      cash_minor, ar_minor, ap_minor, inventory_minor, fixed_assets_minor,
                      debt_minor, equity_minor, notes, updated_at
            """,
            (
                business_id,
                body.subsidiary_id,
                body.period_key,
                body.revenue_minor,
                body.cogs_minor,
                body.opex_minor,
                body.cash_minor,
                body.ar_minor,
                body.ap_minor,
                body.inventory_minor,
                body.fixed_assets_minor,
                body.debt_minor,
                body.equity_minor,
                _clean(body.notes, max_len=500),
                session.principal.user_id,
            ),
        )
        row = await cur.fetchone()

    if row is None:
        raise HTTPException(status_code=500, detail="Failed to save trial balance snapshot.")
    return EntitySnapshotView(**row)


@router.post(
    "/v1/businesses/{business_id}/holding/intercompany",
    response_model=IntercompanyTxView,
    status_code=status.HTTP_201_CREATED,
)
async def create_intercompany_transaction(
    business_id: UUID,
    body: CreateIntercompanyTxRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> IntercompanyTxView:
    """Post a mirrored Due To / Due From intercompany transaction with FX translation."""
    if body.source_subsidiary_id == body.target_subsidiary_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Source and target subsidiaries must be different legal entities.",
        )

    eff_date = body.tx_date or datetime.now(UTC).date()
    tx_number = f"IC-{eff_date.strftime('%Y%m%d')}-{secrets.token_hex(3).upper()}"
    src_label, tgt_label = mirrored_entry_labels(body.tx_kind)
    ic_status: IntercompanyStatus = "eliminated" if body.auto_eliminate else "posted"
    elim_at = datetime.now(UTC) if body.auto_eliminate else None

    async with (
        authorized_tenant(
            runtime_pool(request),
            principal,
            business_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session,
        session.conn.cursor(row_factory=dict_row) as cur,
    ):
        fx_rates = await _load_fx_rates(cur, business_id)
        rate_micros = int(
            fx_rates.get(body.currency, DEFAULT_FX_RATE_MICROS.get(body.currency, 1_000_000))
        )
        usd_cents = max(
            1, convert_minor_to_usd_cents(body.amount_minor, body.currency, rate_micros)
        )

        await cur.execute(
            """
            SELECT id, entity_code, legal_name
            FROM gba.holding_subsidiaries
            WHERE tenant_id = %s AND id IN (%s, %s)
            """,
            (business_id, body.source_subsidiary_id, body.target_subsidiary_id),
        )
        found = {r["id"]: r for r in await cur.fetchall()}
        if body.source_subsidiary_id not in found or body.target_subsidiary_id not in found:
            raise HTTPException(
                status_code=404, detail="Both source and target subsidiaries must exist."
            )

        await cur.execute(
            """
            INSERT INTO gba.intercompany_transactions (
                tenant_id, tx_number, period_key, tx_date,
                source_subsidiary_id, target_subsidiary_id, tx_kind,
                currency, amount_minor, fx_rate_micros, usd_equivalent_cents,
                description, source_entry_label, target_entry_label,
                status, eliminated_at, created_by_user_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, tx_number, period_key, tx_date, source_subsidiary_id,
                      target_subsidiary_id, tx_kind, currency, amount_minor,
                      fx_rate_micros, usd_equivalent_cents, description,
                      source_entry_label, target_entry_label, status, eliminated_at
            """,
            (
                business_id,
                tx_number,
                body.period_key,
                eff_date,
                body.source_subsidiary_id,
                body.target_subsidiary_id,
                body.tx_kind,
                body.currency,
                body.amount_minor,
                rate_micros,
                usd_cents,
                _clean(body.description, max_len=240),
                src_label,
                tgt_label,
                ic_status,
                elim_at,
                session.principal.user_id,
            ),
        )
        row = await cur.fetchone()

    if row is None:
        raise HTTPException(status_code=500, detail="Failed to post intercompany transaction.")
    src_row = found[body.source_subsidiary_id]
    tgt_row = found[body.target_subsidiary_id]
    return IntercompanyTxView(
        **row,
        source_code=str(src_row["entity_code"]),
        source_name=str(src_row["legal_name"]),
        target_code=str(tgt_row["entity_code"]),
        target_name=str(tgt_row["legal_name"]),
    )


@router.post(
    "/v1/businesses/{business_id}/holding/intercompany/{tx_id}/status",
    response_model=IntercompanyTxView,
)
async def update_intercompany_status(
    business_id: UUID,
    tx_id: UUID,
    body: UpdateIntercompanyStatusRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> IntercompanyTxView:
    """Toggle an intercompany entry between eliminated, posted (uneliminated), or void."""
    elim_at = datetime.now(UTC) if body.status == "eliminated" else None

    async with (
        authorized_tenant(
            runtime_pool(request),
            principal,
            business_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session,
        session.conn.cursor(row_factory=dict_row) as cur,
    ):
        await cur.execute(
            """
            UPDATE gba.intercompany_transactions
            SET status = %s, eliminated_at = %s, updated_at = now()
            WHERE tenant_id = %s AND id = %s
            RETURNING id
            """,
            (body.status, elim_at, business_id, tx_id),
        )
        if await cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="Intercompany transaction not found.")

        await cur.execute(
            """
            SELECT t.id, t.tx_number, t.period_key, t.tx_date,
                   t.source_subsidiary_id,
                   s.entity_code AS source_code,
                   s.legal_name AS source_name,
                   t.target_subsidiary_id,
                   d.entity_code AS target_code,
                   d.legal_name AS target_name,
                   t.tx_kind, t.currency, t.amount_minor, t.fx_rate_micros,
                   t.usd_equivalent_cents, t.description,
                   t.source_entry_label, t.target_entry_label,
                   t.status, t.eliminated_at
            FROM gba.intercompany_transactions t
            JOIN gba.holding_subsidiaries s
              ON s.tenant_id = t.tenant_id AND s.id = t.source_subsidiary_id
            JOIN gba.holding_subsidiaries d
              ON d.tenant_id = t.tenant_id AND d.id = t.target_subsidiary_id
            WHERE t.tenant_id = %s AND t.id = %s
            """,
            (business_id, tx_id),
        )
        row = await cur.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Intercompany transaction not found.")
    return IntercompanyTxView(**row)


@router.post(
    "/v1/businesses/{business_id}/holding/seed-sample-group",
    response_model=SeedSampleHoldingResponse,
)
async def seed_sample_holding_group(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    period_key: Annotated[str | None, Query(pattern=r"^[0-9]{4}-[0-9]{2}$")] = None,
) -> SeedSampleHoldingResponse:
    """Idempotently seed a 4-entity multi-currency US/EU/CA holding group for instant demo."""
    eff_period = period_key or datetime.now(UTC).strftime("%Y-%m")
    today = datetime.now(UTC).date()

    sample_subs = [
        (
            "US-HQ",
            "Alexey AAA Holdings LLC",
            "parent_holding",
            "US",
            "IL",
            "USD",
            10000,
            "EIN-**-***4821",
        ),
        (
            "US-OPS",
            "Midwest Cold-Chain Logistics LLC",
            "operating_subsidiary",
            "US",
            "TX",
            "USD",
            10000,
            "EIN-**-***9104",
        ),
        (
            "EU-DE",
            "AMARKAL Europe GmbH",
            "operating_subsidiary",
            "DE",
            "HH",
            "EUR",
            8000,
            "DE-***88219",
        ),
        (
            "CA-ON",
            "AMARKAL Canada Freight Inc.",
            "regional_branch",
            "CA",
            "ON",
            "CAD",
            10000,
            "BN-***4410",
        ),
    ]

    async with (
        authorized_tenant(
            runtime_pool(request),
            principal,
            business_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session,
        session.conn.cursor(row_factory=dict_row) as cur,
    ):
        fx_rates = await _load_fx_rates(cur, business_id)
        sub_ids: dict[str, UUID] = {}
        subs_seeded = 0

        for code, name, role, country, state, ccy, own_bps, tax_id in sample_subs:
            await cur.execute(
                """
                INSERT INTO gba.holding_subsidiaries (
                    tenant_id, entity_code, legal_name, entity_role,
                    jurisdiction_country, jurisdiction_state, functional_currency,
                    ownership_bps, tax_id_masked, created_by_user_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, entity_code) DO UPDATE SET updated_at = now()
                RETURNING id
                """,
                (
                    business_id,
                    code,
                    name,
                    role,
                    country,
                    state,
                    ccy,
                    own_bps,
                    tax_id,
                    session.principal.user_id,
                ),
            )
            r = await cur.fetchone()
            if r:
                sub_ids[code] = r["id"]
                subs_seeded += 1

        # Period snapshots (in functional currency minor units)
        sample_snaps = [
            # code, rev, cogs, opex, cash, ar, ap, inv, fa, debt, eq
            (
                "US-HQ",
                18000000,
                0,
                6200000,
                95000000,
                24000000,
                3500000,
                0,
                42000000,
                12000000,
                145500000,
            ),
            (
                "US-OPS",
                64000000,
                31000000,
                14500000,
                38500000,
                19200000,
                11400000,
                8200000,
                56000000,
                18000000,
                92500000,
            ),
            (
                "EU-DE",
                42000000,
                19500000,
                10500000,
                22400000,
                14800000,
                9600000,
                4100000,
                28000000,
                9500000,
                50200000,
            ),
            (
                "CA-ON",
                28000000,
                12500000,
                7400000,
                16200000,
                9400000,
                5800000,
                2600000,
                14000000,
                4000000,
                32400000,
            ),
        ]
        snaps_seeded = 0
        for code, rev, cogs, opex, cash, ar, ap, inv, fa, debt, eq in sample_snaps:
            sid = sub_ids.get(code)
            if not sid:
                continue
            await cur.execute(
                """
                INSERT INTO gba.holding_entity_trial_snapshots (
                    tenant_id, subsidiary_id, period_key, revenue_minor, cogs_minor, opex_minor,
                    cash_minor, ar_minor, ap_minor, inventory_minor, fixed_assets_minor,
                    debt_minor, equity_minor, notes, updated_by_user_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, subsidiary_id, period_key) DO NOTHING
                RETURNING id
                """,
                (
                    business_id,
                    sid,
                    eff_period,
                    rev,
                    cogs,
                    opex,
                    cash,
                    ar,
                    ap,
                    inv,
                    fa,
                    debt,
                    eq,
                    f"Sample multi-entity holding trial balance ({eff_period})",
                    session.principal.user_id,
                ),
            )
            if await cur.fetchone():
                snaps_seeded += 1

        # Mirrored intercompany transactions
        sample_ics: list[tuple[str, str, str, IntercompanyTxKind, CurrencyCode, int, str]] = [
            (
                f"IC-DEMO-{eff_period}-01",
                "US-HQ",
                "US-OPS",
                "management_fee",
                "USD",
                8500000,
                "Parent HQ Executive & Cloud ERP Management Fee",
            ),
            (
                f"IC-DEMO-{eff_period}-02",
                "US-OPS",
                "EU-DE",
                "intercompany_service",
                "EUR",
                4500000,
                "Transatlantic Cold-Chain Freight Allocation (US -> Hamburg)",
            ),
            (
                f"IC-DEMO-{eff_period}-03",
                "US-HQ",
                "CA-ON",
                "intercompany_loan",
                "CAD",
                6000000,
                "Intercompany Fleet Working Capital Line (Due From CA-ON)",
            ),
        ]
        ic_seeded = 0
        for tx_no, src_code, tgt_code, kind, ccy, amt, desc in sample_ics:
            src_id = sub_ids.get(src_code)
            tgt_id = sub_ids.get(tgt_code)
            if not src_id or not tgt_id:
                continue
            rate = int(fx_rates.get(ccy, DEFAULT_FX_RATE_MICROS.get(ccy, 1_000_000)))
            usd_cents = max(1, convert_minor_to_usd_cents(amt, ccy, rate))
            src_lbl, tgt_lbl = mirrored_entry_labels(kind)
            await cur.execute(
                """
                INSERT INTO gba.intercompany_transactions (
                    tenant_id, tx_number, period_key, tx_date,
                    source_subsidiary_id, target_subsidiary_id, tx_kind,
                    currency, amount_minor, fx_rate_micros, usd_equivalent_cents,
                    description, source_entry_label, target_entry_label,
                    status, eliminated_at, created_by_user_id
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    'eliminated', now(), %s
                )
                ON CONFLICT (tenant_id, tx_number) DO NOTHING
                RETURNING id
                """,
                (
                    business_id,
                    tx_no,
                    eff_period,
                    today,
                    src_id,
                    tgt_id,
                    kind,
                    ccy,
                    amt,
                    rate,
                    usd_cents,
                    desc,
                    src_lbl,
                    tgt_lbl,
                    session.principal.user_id,
                ),
            )
            if await cur.fetchone():
                ic_seeded += 1

    return SeedSampleHoldingResponse(
        period_key=eff_period,
        subsidiaries_seeded=subs_seeded,
        snapshots_seeded=snaps_seeded,
        intercompany_seeded=ic_seeded,
        message=(
            f"Loaded 4-entity US/EU/CA holding structure for {eff_period} with "
            f"automatic EUR/CAD FX translation, 20% EU minority NCI, and mirrored "
            f"Due To / Due From intercompany eliminations."
        ),
    )
