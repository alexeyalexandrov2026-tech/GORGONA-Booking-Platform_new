"""Unit tests for AMARKAL v2.32.0 Intercompany Mirror Trade (SO <-> PO) & UPII Elimination."""

from __future__ import annotations

from pathlib import Path

import gorgona_booking
from gorgona_booking.api.holding_consolidation import (
    compute_consolidated_holding,
    compute_intercompany_trade_metrics,
)


def test_compute_intercompany_trade_metrics_goods_upii_and_services_zero() -> None:
    # 100 units @ $800.00 transfer price ($80,000), seller internal cost $550.00 ($55,000)
    # Intercompany profit = $25,000; 40% (4000 bps) still unsold at period close -> $10,000 UPII
    tot_tr, tot_cost, ic_prof, tr_usd, upii_usd = compute_intercompany_trade_metrics(
        trade_kind="raw_materials",
        quantity_milli=100_000,
        unit_transfer_price_minor=80_000,
        seller_unit_cost_minor=55_000,
        buyer_unsold_inventory_bps=4_000,
        currency="USD",
        fx_rate_micros=1_000_000,
    )
    assert tot_tr == 8_000_000
    assert tot_cost == 5_500_000
    assert ic_prof == 2_500_000
    assert tr_usd == 8_000_000
    assert upii_usd == 1_000_000

    # EUR transfer: 50 units @ EUR 200 transfer, EUR 120 cost -> EUR 4,000 profit
    # FX 1.10 USD/EUR -> $4,400 USD profit; 50% unsold -> $2,200.00 (220,000 cents) UPII
    _, _, _, eur_tr_usd, eur_upii_usd = compute_intercompany_trade_metrics(
        trade_kind="finished_goods",
        quantity_milli=50_000,
        unit_transfer_price_minor=20_000,
        seller_unit_cost_minor=12_000,
        buyer_unsold_inventory_bps=5_000,
        currency="EUR",
        fx_rate_micros=1_100_000,
    )
    assert eur_tr_usd == 1_100_000
    assert eur_upii_usd == 220_000

    # Pure intercompany services carry 0 UPII even if unsold_bps > 0
    _, _, _, svc_usd, svc_upii = compute_intercompany_trade_metrics(
        trade_kind="intercompany_service",
        quantity_milli=1_000,
        unit_transfer_price_minor=500_000,
        seller_unit_cost_minor=200_000,
        buyer_unsold_inventory_bps=10_000,
        currency="USD",
        fx_rate_micros=1_000_000,
    )
    assert svc_usd == 500_000
    assert svc_upii == 0


def test_consolidation_eliminates_mirror_trade_turnover_and_defers_upii_in_inventory() -> None:
    subsidiaries = [
        {
            "id": "sub-us",
            "entity_code": "US-OPS",
            "legal_name": "US Operations LLC",
            "entity_role": "parent_holding",
            "jurisdiction_country": "US",
            "jurisdiction_state": "TX",
            "functional_currency": "USD",
            "ownership_bps": 10_000,
        },
        {
            "id": "sub-eu",
            "entity_code": "EU-DE",
            "legal_name": "Europe GmbH",
            "entity_role": "operating_subsidiary",
            "jurisdiction_country": "DE",
            "jurisdiction_state": "HH",
            "functional_currency": "USD",
            "ownership_bps": 10_000,
        },
    ]
    snapshots = [
        {
            "subsidiary_id": "sub-us",
            "revenue_minor": 10_000_000,  # includes $80k IC sale
            "cogs_minor": 5_500_000,  # includes $55k internal cost
            "opex_minor": 1_000_000,
            "cash_minor": 5_000_000,
            "ar_minor": 8_000_000,  # $80k Due From EU-DE
            "ap_minor": 0,
            "inventory_minor": 2_000_000,
            "fixed_assets_minor": 0,
            "debt_minor": 0,
            "equity_minor": 15_000_000,
        },
        {
            "subsidiary_id": "sub-eu",
            "revenue_minor": 6_000_000,
            "cogs_minor": 4_800_000,  # 60% of $80k goods sold externally
            "opex_minor": 500_000,
            "cash_minor": 3_000_000,
            "ar_minor": 0,
            "ap_minor": 8_000_000,  # $80k Due To US-OPS
            "inventory_minor": 3_200_000,  # 40% of $80k sitting in ending inventory ($10k UPII)
            "fixed_assets_minor": 0,
            "debt_minor": 0,
            "equity_minor": -1_800_000,
        },
    ]
    # Linked intercompany inventory transfer elimination ($80k = 8,000,000 cents)
    ic_txs = [
        {
            "source_subsidiary_id": "sub-us",
            "target_subsidiary_id": "sub-eu",
            "tx_kind": "inventory_transfer",
            "usd_equivalent_cents": 8_000_000,
            "status": "eliminated",
        }
    ]
    # Mirror trade order with $10,000 (1,000,000 cents) deferred UPII
    trade_orders = [
        {
            "status": "invoiced_eliminated",
            "upii_usd_cents": 1_000_000,
        },
        {
            "status": "mirrored_open",  # not yet invoiced -> must NOT eliminate UPII yet
            "upii_usd_cents": 999_999,
        },
    ]

    _, pre, elim, cons, _ = compute_consolidated_holding(
        subsidiaries=subsidiaries,
        snapshots=snapshots,
        intercompany_txs=ic_txs,
        fx_rates_micros={"USD": 1_000_000},
        intercompany_trade_orders=trade_orders,
    )

    # Pre revenue = $160k -> eliminate $80k -> Consolidated revenue = $80k
    assert pre.revenue_cents == 16_000_000
    assert elim.revenue_cents == -8_000_000
    assert cons.revenue_cents == 8_000_000

    # COGS elimination = -$80k turnover + $10k deferred UPII = -$70k net elimination
    assert elim.cogs_cents == -7_000_000
    assert cons.cogs_cents == pre.cogs_cents - 7_000_000

    # Net Income reduced by exactly $10k UPII (ASC 810 / IFRS 10)
    assert elim.net_income_cents == -1_000_000
    assert cons.net_income_cents == pre.net_income_cents - 1_000_000

    # Inventory reduced by $10k UPII, AR/AP eliminated by $80k, Equity reduced by $10k UPII
    assert elim.inventory_cents == -1_000_000
    assert cons.inventory_cents == pre.inventory_cents - 1_000_000
    assert elim.ar_cents == -8_000_000
    assert elim.ap_cents == -8_000_000
    assert elim.equity_cents == -1_000_000
    # Balance Sheet stays in exact equilibrium (Assets - Liabilities = Equity)
    assert cons.total_assets_cents - cons.total_liabilities_cents == cons.equity_cents


def test_migration_0169_enforces_force_rls_and_no_security_definer() -> None:
    mig_path = (
        Path(gorgona_booking.__file__).parent
        / "db"
        / "migrations"
        / "0169_intercompany_mirror_trade.sql"
    )
    sql = mig_path.read_text(encoding="utf-8")
    non_comment_sql = "\n".join(
        line for line in sql.splitlines() if not line.strip().startswith("--")
    )
    assert "ENABLE ROW LEVEL SECURITY" in non_comment_sql
    assert "FORCE ROW LEVEL SECURITY" in non_comment_sql
    assert "gba.intercompany_trade_orders" in non_comment_sql
    assert "SECURITY DEFINER" not in non_comment_sql.upper()
