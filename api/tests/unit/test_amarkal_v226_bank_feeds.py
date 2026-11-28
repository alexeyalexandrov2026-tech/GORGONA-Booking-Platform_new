"""Unit tests for AMARKAL v2.26.0 US Bank Feeds (OFX/QFX/QBO/CSV parsers & auto-matcher)."""

from __future__ import annotations

from datetime import date

from gorgona_booking.api.bank_feeds import (
    LedgerMatchCandidate,
    ParsedBankTransaction,
    find_best_reconciliation_match,
    infer_bank_category,
    parse_bank_statement,
)

SAMPLE_OFX = """OFXHEADER:100
DATA:OFXSGML
<OFX>
  <BANKMSGSRSV1>
    <STMTTRNRS>
      <STMTRS>
        <BANKTRANLIST>
          <STMTTRN>
            <TRNTYPE>CREDIT
            <DTPOSTED>20261124120000[-5:EST]
            <TRNAMT>12500.00
            <FITID>20261124-CHASE-001
            <NAME>STRIPE US PAYOUT
            <MEMO>SETTLEMENT BATCH 901
          </STMTTRN>
          <STMTTRN>
            <TRNTYPE>DEBIT
            <DTPOSTED>20261125120000[-5:EST]
            <TRNAMT>-1840.50
            <FITID>20261125-CHASE-002
            <NAME>PILOT FLYING J #412
            <MEMO>DIESEL FLEET CARD
          </STMTTRN>
        </BANKTRANLIST>
        <LEDGERBAL>
          <BALAMT>94210.75
        </LEDGERBAL>
      </STMTRS>
    </STMTTRNRS>
  </BANKMSGSRSV1>
</OFX>
"""

SAMPLE_CHASE_CSV = """Posting Date,Description,Amount,Type,Balance
11/26/2026,ACH CREDIT ACME LOGISTICS INV-2026-041,"$4,250.00",ACH_CREDIT,"$98,460.75"
11/25/2026,GUSTO PAYROLL DEBIT,"($3,120.40)",ACH_DEBIT,"$94,210.75"
11/25/2026,GUSTO PAYROLL DEBIT,"($3,120.40)",ACH_DEBIT,"$91,090.35"
"""


def test_parse_ofx_statement_extracts_transactions_and_balance() -> None:
    fmt, txs, bal, errors = parse_bank_statement(SAMPLE_OFX, "auto")
    assert fmt == "ofx"
    assert errors == []
    assert bal == 9_421_075
    assert len(txs) == 2

    assert txs[0].external_tx_id == "20261124-CHASE-001"
    assert txs[0].posted_date == date(2026, 11, 24)
    assert txs[0].direction == "credit"
    assert txs[0].amount_cents == 1_250_000
    assert txs[0].category_hint == "client_payment"

    assert txs[1].external_tx_id == "20261125-CHASE-002"
    assert txs[1].direction == "debit"
    assert txs[1].amount_cents == 184_050
    assert txs[1].category_hint == "fleet_fuel"


def test_parse_csv_handles_us_dates_parentheses_and_distinct_same_day_hashes() -> None:
    fmt, txs, bal, errors = parse_bank_statement(SAMPLE_CHASE_CSV, "auto")
    assert fmt == "csv"
    assert errors == []
    assert bal == 9_846_075
    assert len(txs) == 3

    assert txs[0].posted_date == date(2026, 11, 26)
    assert txs[0].direction == "credit"
    assert txs[0].amount_cents == 425_000

    assert txs[1].direction == "debit"
    assert txs[1].amount_cents == 312_040
    assert txs[1].category_hint == "payroll"

    # Two identical same-day rows get distinct deterministic IDs; re-parse matches exactly
    assert txs[1].external_tx_id != txs[2].external_tx_id
    _, txs_again, _, _ = parse_bank_statement(SAMPLE_CHASE_CSV, "csv")
    assert [t.external_tx_id for t in txs_again] == [t.external_tx_id for t in txs]


def test_find_best_reconciliation_match_scores_exact_amount_date_and_tokens() -> None:
    tx = ParsedBankTransaction(
        external_tx_id="tx-1",
        posted_date=date(2026, 11, 26),
        description="ACH CREDIT ACME LOGISTICS INV-2026-041",
        merchant_name="ACME LOGISTICS",
        direction="credit",
        amount_cents=425_000,
        category_hint="client_payment",
    )
    candidates = [
        LedgerMatchCandidate(
            kind="purchase_order",
            entity_id="po-1",
            label="PO-99 · Wrong Direction",
            direction="debit",
            amount_cents=425_000,
            ref_date=date(2026, 11, 26),
            tokens=frozenset({"acme", "logistics"}),
        ),
        LedgerMatchCandidate(
            kind="invoice",
            entity_id="inv-41",
            label="FIN-03 INV-2026-041 · Acme Logistics",
            direction="credit",
            amount_cents=425_000,
            ref_date=date(2026, 11, 25),
            tokens=frozenset({"inv", "2026", "041", "acme", "logistics"}),
        ),
    ]
    matched = find_best_reconciliation_match(tx, candidates)
    assert matched is not None
    cand, confidence = matched
    assert cand.entity_id == "inv-41"
    assert cand.kind == "invoice"
    assert confidence == 100


def test_find_best_reconciliation_match_returns_none_for_unrelated_amount() -> None:
    tx = ParsedBankTransaction(
        external_tx_id="tx-2",
        posted_date=date(2026, 11, 26),
        description="OFFICE SUPPLIES",
        merchant_name="Staples",
        direction="debit",
        amount_cents=9_500,
        category_hint="operating_expense",
    )
    candidates = [
        LedgerMatchCandidate(
            kind="purchase_order",
            entity_id="po-2",
            label="PO-100 · Huge Freight",
            direction="debit",
            amount_cents=950_000,
            ref_date=date(2026, 11, 26),
            tokens=frozenset({"freight"}),
        )
    ]
    assert find_best_reconciliation_match(tx, candidates) is None
    assert infer_bank_category("AWS US-EAST-1", "debit") == "software_cloud"
    assert infer_bank_category("IRS EFTPS TAX", "debit") == "tax_payment"
