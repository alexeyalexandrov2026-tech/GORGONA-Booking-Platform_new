"""Unit tests for AMARKAL v2.27.0 Holding Multi-Entity & Intercompany Consolidation."""

from __future__ import annotations

from gorgona_booking.api.holding_consolidation import (
    compute_consolidated_holding,
    convert_minor_to_usd_cents,
    mirrored_entry_labels,
)


def test_convert_minor_to_usd_cents_handles_usd_eur_and_jpy() -> None:
    assert convert_minor_to_usd_cents(250_000, "USD", 1_000_000) == 250_000
    # 1,000.00 EUR (100,000 minor) @ 1.10 USD/EUR -> $1,100.00 (110,000 cents)
    assert convert_minor_to_usd_cents(100_000, "EUR", 1_100_000) == 110_000
    # 10,000 JPY (0 minor decimals) @ 0.0066 USD/JPY (6,600 micros) -> $66.00 (6,600 cents)
    assert convert_minor_to_usd_cents(10_000, "JPY", 6_600) == 6_600


def test_compute_consolidated_holding_fx_eliminations_nci_and_due_to_from_matrix() -> None:
    subsidiaries = [
        {
            "id": "sub-us",
            "entity_code": "US-HQ",
            "legal_name": "Parent Holdings LLC",
            "entity_role": "parent_holding",
            "jurisdiction_country": "US",
            "jurisdiction_state": "IL",
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
            "functional_currency": "EUR",
            "ownership_bps": 8_000,  # 80% owned -> 20% Non-Controlling Interest (NCI)
        },
    ]
    snapshots = [
        {
            "subsidiary_id": "sub-us",
            "revenue_minor": 500_000,
            "cogs_minor": 100_000,
            "opex_minor": 100_000,
            "cash_minor": 300_000,
            "ar_minor": 150_000,
            "ap_minor": 50_000,
            "inventory_minor": 0,
            "fixed_assets_minor": 200_000,
            "debt_minor": 100_000,
            "equity_minor": 500_000,
        },
        {
            "subsidiary_id": "sub-eu",
            "revenue_minor": 200_000,  # EUR -> @1.10 = 220,000 USD cents
            "cogs_minor": 50_000,  # EUR -> 55,000 USD cents
            "opex_minor": 50_000,  # EUR -> 55,000 USD cents; NI = 110,000 (88k Ctrl / 22k NCI)
            "cash_minor": 100_000,  # 110,000
            "ar_minor": 50_000,  # 55,000
            "ap_minor": 100_000,  # 110,000
            "inventory_minor": 0,
            "fixed_assets_minor": 100_000,  # 110,000
            "debt_minor": 50_000,  # 55,000
            "equity_minor": 100_000,  # 110,000
        },
    ]
    intercompany_txs = [
        {
            "source_subsidiary_id": "sub-us",
            "target_subsidiary_id": "sub-eu",
            "tx_kind": "management_fee",
            "usd_equivalent_cents": 40_000,
            "status": "eliminated",
        },
        {
            "source_subsidiary_id": "sub-us",
            "target_subsidiary_id": "sub-eu",
            "tx_kind": "intercompany_loan",
            "usd_equivalent_cents": 25_000,
            "status": "eliminated",
        },
        {
            "source_subsidiary_id": "sub-eu",
            "target_subsidiary_id": "sub-us",
            "tx_kind": "intercompany_service",
            "usd_equivalent_cents": 10_000,
            "status": "eliminated",
        },
        {
            "source_subsidiary_id": "sub-us",
            "target_subsidiary_id": "sub-eu",
            "tx_kind": "management_fee",
            "usd_equivalent_cents": 99_999,
            "status": "void",  # must be completely ignored
        },
    ]

    per_entity, pre, elim, cons, matrix = compute_consolidated_holding(
        subsidiaries=subsidiaries,
        snapshots=snapshots,
        intercompany_txs=intercompany_txs,
        fx_rates_micros={"USD": 1_000_000, "EUR": 1_100_000},
    )

    assert len(per_entity) == 2
    eu_row = next(r for r in per_entity if r.entity_code == "EU-DE")
    assert eu_row.revenue_usd_cents == 220_000
    assert eu_row.net_income_usd_cents == 110_000
    assert eu_row.controlling_net_income_cents == 88_000
    assert eu_row.nci_net_income_cents == 22_000

    # Pre-elimination revenue: 500k + 220k = 720k; Eliminated rev: 40k + 10k = 50k -> Cons: 670k
    assert pre.revenue_cents == 720_000
    assert elim.revenue_cents == -50_000
    assert cons.revenue_cents == 670_000

    # OpEx eliminated matches management_fee + service = 50k -> Net Income stays neutral (410k)
    assert elim.opex_cents == -50_000
    assert cons.net_income_cents == 410_000
    assert cons.nci_net_income_cents == 22_000
    assert cons.controlling_interest_net_income_cents == 388_000

    # AR eliminated: 40k + 25k + 10k = 75k; AP eliminated: 40k + 10k = 50k; Debt eliminated: 25k
    assert elim.ar_cents == -75_000
    assert elim.ap_cents == -50_000
    assert elim.debt_cents == -25_000
    assert cons.ar_cents == 130_000
    assert cons.ap_cents == 110_000
    assert cons.debt_cents == 130_000

    # Net Due To / Due From: US-HQ due from EU-DE = (40k + 25k) - 10k = 55k
    assert len(matrix) == 1
    assert matrix[0].creditor_code == "US-HQ"
    assert matrix[0].debtor_code == "EU-DE"
    assert matrix[0].net_due_usd_cents == 55_000
    assert matrix[0].tx_count == 3

    src_l, tgt_l = mirrored_entry_labels("intercompany_loan")
    assert "Due From" in src_l
    assert "Due To" in tgt_l
