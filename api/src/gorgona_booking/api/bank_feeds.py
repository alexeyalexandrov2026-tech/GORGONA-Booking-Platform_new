"""AMARKAL v2.26.0: US Direct Bank Feeds, OFX/QFX/QBO/CSV Importer & Smart Reconciliation.

Security & architectural invariants:
- Strictly additive over PostgreSQL 18 `ENABLE + FORCE ROW LEVEL SECURITY`.
- Zero external dependencies for statement ingestion: parses US bank OFX / QFX / QBO
  (SGML & XML) and Chase / Bank of America / Wells Fargo / Mercury / Relay CSV exports
  with deterministic idempotent deduplication (`ON CONFLICT DO NOTHING`).
- Human-in-the-Loop auto-reconciliation suggests matches against live FIN-03 invoices,
  B2B Purchase Orders, Stripe settlements, US Payroll runs, and FX Ledger entries, and
  never finalizes reconciliation without explicit operator confirmation.
- Optional Plaid Direct US Bank connector stores tenant BYOK credentials strictly inside
  AMARKAL's per-tenant AES-256-GCM Secret Vault (never returned in plaintext).
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
from collections import Counter
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, Field

from gorgona_booking.api.businesses import CurrentPrincipal
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.connectors.vault import (
    get_tenant_secret_public,
    mask_secret_hint,
    upsert_tenant_secret,
)
from gorgona_booking.tenancy.authorization import authorized_tenant

router = APIRouter(tags=["bank-feeds"])

AccountType = Literal["checking", "savings", "credit_card", "treasury"]
ConnectionMode = Literal["statement_upload", "plaid_sandbox", "plaid_production"]
TxDirection = Literal["credit", "debit"]
SourceFormat = Literal["ofx", "qfx", "qbo", "csv", "plaid", "manual"]
ReconciliationStatus = Literal["unmatched", "suggested", "reconciled", "excluded"]
MatchedEntityKind = Literal[
    "invoice",
    "purchase_order",
    "payment_session",
    "payroll_run",
    "fx_entry",
    "manual_category",
]
CurrencyCode = Literal["USD", "EUR", "GBP", "CAD", "MXN", "CHF", "AUD", "JPY"]

MAX_STATEMENT_ROWS = 500
PLAID_CONNECTOR_ID = "plaid_us_bank"
_CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")
_WORD_RE = re.compile(r"[a-z0-9]{3,}")
_STMTTRN_RE = re.compile(r"<STMTTRN>(.*?)</STMTTRN>", re.IGNORECASE | re.DOTALL)

SUPPORTED_US_INSTITUTIONS: tuple[dict[str, str], ...] = (
    {"id": "chase", "name": "Chase Business", "rail": "Plaid / OFX / QBO / CSV"},
    {"id": "bofa", "name": "Bank of America", "rail": "Plaid / OFX / QFX / CSV"},
    {"id": "wells_fargo", "name": "Wells Fargo Commercial", "rail": "Plaid / QBO / CSV"},
    {"id": "mercury", "name": "Mercury Treasury & Checking", "rail": "Plaid / CSV"},
    {"id": "relay", "name": "Relay Financial", "rail": "Plaid / QBO / CSV"},
    {"id": "citi", "name": "Citibank Commercial", "rail": "Plaid / OFX / CSV"},
    {"id": "pnc", "name": "PNC Business Banking", "rail": "Plaid / QFX / CSV"},
    {"id": "capital_one", "name": "Capital One Spark", "rail": "Plaid / QFX / CSV"},
)


class BankAccountView(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    institution_name: str
    account_name: str
    account_mask: str
    account_type: AccountType
    currency: CurrencyCode
    connection_mode: ConnectionMode
    current_balance_cents: int
    last_synced_at: datetime | None
    is_active: bool
    unmatched_count: int
    suggested_count: int
    reconciled_count: int


class PlaidStatusView(BaseModel):
    model_config = ConfigDict(frozen=True)
    configured: bool
    source: Literal["none", "tenant_vault_byok", "platform_env"]
    plaid_env: Literal["sandbox", "production"]
    client_id_hint: str | None
    updated_at: datetime | None
    supported_institutions: list[dict[str, str]]


class BankFeedsSummaryResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    accounts: list[BankAccountView]
    total_balance_cents: int
    total_transactions: int
    unmatched_count: int
    suggested_count: int
    reconciled_count: int
    excluded_count: int
    reconciliation_rate_pct: float
    plaid_status: PlaidStatusView


class CreateBankAccountRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    institution_name: str = Field(min_length=2, max_length=120)
    account_name: str = Field(min_length=2, max_length=120)
    account_mask: str = Field(default="0000", pattern=r"^[0-9A-Za-z]{2,8}$")
    account_type: AccountType = "checking"
    currency: CurrencyCode = "USD"
    current_balance_cents: int = Field(default=0, ge=-999_999_999_999, le=999_999_999_999)


class BankStatementImportRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    source_format: Literal["auto", "ofx", "qfx", "qbo", "csv"] = "auto"
    raw_content: str = Field(min_length=8, max_length=600_000)
    dry_run: bool = False


class ParsedBankTxPreview(BaseModel):
    model_config = ConfigDict(frozen=True)
    external_tx_id: str
    posted_date: str
    description: str
    merchant_name: str
    direction: TxDirection
    amount_cents: int
    category_hint: str


class BankStatementImportResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    detected_format: SourceFormat
    dry_run: bool
    parsed_count: int
    imported_count: int
    duplicate_skipped_count: int
    suggested_match_count: int
    detected_balance_cents: int | None
    errors: list[str]
    preview: list[ParsedBankTxPreview]


class BankTransactionView(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    bank_account_id: UUID
    account_label: str
    external_tx_id: str
    posted_date: date
    description: str
    merchant_name: str
    direction: TxDirection
    amount_cents: int
    currency: CurrencyCode
    category_hint: str
    source_format: SourceFormat
    reconciliation_status: ReconciliationStatus
    matched_entity_kind: MatchedEntityKind | None
    matched_entity_id: str | None
    matched_entity_label: str
    match_confidence: int
    reconciled_at: datetime | None
    notes: str


class ReconcileTransactionRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    action: Literal["confirm_match", "manual_category", "exclude", "unmatch"]
    matched_entity_kind: MatchedEntityKind | None = None
    matched_entity_id: str | None = Field(default=None, max_length=120)
    matched_entity_label: str | None = Field(default=None, max_length=200)
    category_hint: str | None = Field(default=None, max_length=80)
    notes: str = Field(default="", max_length=500)


class SavePlaidCredentialsRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    plaid_env: Literal["sandbox", "production"] = "sandbox"
    client_id: str = Field(min_length=6, max_length=128)
    secret: str = Field(min_length=8, max_length=160)


class PlaidSandboxSyncRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    institution_name: str = Field(default="Chase Business", min_length=2, max_length=120)
    account_name: str = Field(default="Operating Checking", min_length=2, max_length=120)
    account_mask: str = Field(default="4821", pattern=r"^[0-9A-Za-z]{2,8}$")


class PlaidSandboxSyncResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    account: BankAccountView
    imported_count: int
    duplicate_skipped_count: int
    suggested_match_count: int
    message: str


@dataclass(frozen=True)
class ParsedBankTransaction:
    external_tx_id: str
    posted_date: date
    description: str
    merchant_name: str
    direction: TxDirection
    amount_cents: int
    category_hint: str


@dataclass(frozen=True)
class LedgerMatchCandidate:
    kind: MatchedEntityKind
    entity_id: str
    label: str
    direction: TxDirection
    amount_cents: int
    ref_date: date
    tokens: frozenset[str]


def _clean(raw: str | None, *, max_len: int = 240) -> str:
    cleaned = _CTRL_RE.sub(" ", (raw or "")).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:max_len]


def _tokenize(text: str) -> frozenset[str]:
    return frozenset(_WORD_RE.findall(text.lower()))


def infer_bank_category(description: str, direction: TxDirection) -> str:
    low = description.lower()
    if any(k in low for k in ("payroll", "gusto", "adp", "paychex", "salary", "wages")):
        return "payroll"
    if any(k in low for k in ("stripe", "payout", "ach credit", "wire in", "invoice")):
        return "client_payment" if direction == "credit" else "merchant_fee"
    if any(k in low for k in ("fuel", "pilot", "loves", "shell", "chevron", "diesel", "toll")):
        return "fleet_fuel"
    if any(k in low for k in ("irs", "eftps", "state tax", "sales tax", "franchise tax")):
        return "tax_payment"
    if any(k in low for k in ("aws", "google cloud", "microsoft", "slack", "github", "zoom")):
        return "software_cloud"
    if any(k in low for k in ("fee", "service charge", "wire fee", "overdraft")):
        return "bank_fee"
    if any(k in low for k in ("rent", "lease", "warehouse", "property")):
        return "facilities_rent"
    if direction == "credit":
        return "revenue_inflow"
    return "operating_expense"


def _parse_money_signed_cents(raw: str) -> int:
    s = raw.strip()
    if not s:
        raise ValueError("Empty amount")
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1].strip()
    s = s.replace("$", "").replace(",", "").replace(" ", "")
    if s.startswith("-"):
        neg = True
        s = s[1:]
    elif s.startswith("+"):
        s = s[1:]
    val = float(s)
    cents = round(abs(val) * 100)
    return -cents if neg else cents


def _parse_us_date(raw: str) -> date:
    s = raw.strip().split(" ", 1)[0].split("T", 1)[0]
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=UTC).date()
        except ValueError:
            continue
    raise ValueError(f"Unsupported date format: {raw!r}")


def _extract_ofx_tag(block: str, tag: str) -> str:
    # Supports both XML (<TAG>value</TAG>) and SGML (<TAG>value\n<NEXTTAG>)
    xml_m = re.search(rf"<{tag}>\s*([^<\r\n]+?)\s*</{tag}>", block, re.IGNORECASE)
    if xml_m:
        return xml_m.group(1).strip()
    sgml_m = re.search(rf"<{tag}>\s*([^<\r\n]+)", block, re.IGNORECASE)
    if sgml_m:
        return sgml_m.group(1).strip()
    return ""


def parse_ofx_statement(
    raw_content: str,
) -> tuple[list[ParsedBankTransaction], int | None, list[str]]:
    """Parse US bank OFX / QFX / QBO (SGML or XML) statement payloads."""
    txs: list[ParsedBankTransaction] = []
    errors: list[str] = []
    seen_hashes: Counter[str] = Counter()

    bal_cents: int | None = None
    bal_block = re.search(r"<LEDGERBAL>(.*?)</LEDGERBAL>", raw_content, re.IGNORECASE | re.DOTALL)
    if bal_block:
        bal_str = _extract_ofx_tag(bal_block.group(1), "BALAMT")
        if bal_str:
            try:
                bal_cents = _parse_money_signed_cents(bal_str)
            except ValueError:
                bal_cents = None

    blocks = _STMTTRN_RE.findall(raw_content)
    if not blocks:
        return [], bal_cents, ["No <STMTTRN> transaction blocks found in OFX/QFX/QBO payload."]

    for idx, block in enumerate(blocks, start=1):
        if len(txs) >= MAX_STATEMENT_ROWS:
            errors.append(f"Batch capped at {MAX_STATEMENT_ROWS} transactions; split larger files.")
            break
        try:
            dt_raw = _extract_ofx_tag(block, "DTPOSTED")[:8]
            if len(dt_raw) < 8:
                raise ValueError("Missing DTPOSTED")
            posted = _parse_us_date(dt_raw)

            amt_raw = _extract_ofx_tag(block, "TRNAMT")
            signed_cents = _parse_money_signed_cents(amt_raw)
            if signed_cents == 0:
                continue
            direction: TxDirection = "credit" if signed_cents > 0 else "debit"
            amount_cents = abs(signed_cents)

            name = _clean(_extract_ofx_tag(block, "NAME"), max_len=160)
            memo = _clean(_extract_ofx_tag(block, "MEMO"), max_len=160)
            desc = _clean(
                f"{name} — {memo}"
                if name and memo and memo.lower() not in name.lower()
                else (name or memo or "Bank Transaction"),
                max_len=300,
            )
            fitid = _clean(_extract_ofx_tag(block, "FITID"), max_len=120)
            if not fitid:
                base_sig = f"{posted.isoformat()}|{direction}|{amount_cents}|{desc.lower()}"
                occ = seen_hashes[base_sig]
                seen_hashes[base_sig] += 1
                fitid = f"ofx-{hashlib.sha256(f'{base_sig}|{occ}'.encode()).hexdigest()[:24]}"

            txs.append(
                ParsedBankTransaction(
                    external_tx_id=fitid,
                    posted_date=posted,
                    description=desc,
                    merchant_name=name or desc[:80],
                    direction=direction,
                    amount_cents=amount_cents,
                    category_hint=infer_bank_category(desc, direction),
                )
            )
        except Exception as exc:
            errors.append(f"OFX item #{idx}: {exc}")

    return txs, bal_cents, errors


def parse_bank_csv_statement(
    raw_content: str,
) -> tuple[list[ParsedBankTransaction], int | None, list[str]]:
    """Parse Chase, Bank of America, Wells Fargo, Mercury, and Relay US bank CSV exports."""
    text = raw_content.lstrip("\ufeff").strip()
    if not text:
        return [], None, ["CSV statement payload is empty."]

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return [], None, ["CSV header row is missing."]

    txs: list[ParsedBankTransaction] = []
    errors: list[str] = []
    seen_sigs: Counter[str] = Counter()
    latest_balance: int | None = None

    def pick(row: dict[str, str], *keys: str) -> str:
        for k in keys:
            if k in row and row[k].strip():
                return row[k].strip()
        return ""

    for idx, raw_row in enumerate(reader, start=2):
        if len(txs) >= MAX_STATEMENT_ROWS:
            errors.append(f"Batch capped at {MAX_STATEMENT_ROWS} rows; split larger exports.")
            break

        norm = {
            re.sub(r"[^a-z0-9]+", "_", (k or "").strip().lower()).strip("_"): (v or "").strip()
            for k, v in raw_row.items()
            if k is not None
        }
        if not any(norm.values()):
            continue

        try:
            date_str = pick(
                norm,
                "posting_date",
                "post_date",
                "transaction_date",
                "date",
                "date_utc",
                "effective_date",
            )
            if not date_str:
                raise ValueError("Missing date column")
            posted = _parse_us_date(date_str)

            desc = _clean(
                pick(
                    norm,
                    "description",
                    "bank_description",
                    "name",
                    "merchant",
                    "payee",
                    "memo",
                ),
                max_len=300,
            )
            if not desc:
                raise ValueError("Missing description / merchant column")
            merchant = _clean(pick(norm, "merchant", "name", "payee") or desc, max_len=160)

            amt_str = pick(norm, "amount", "amount_usd", "transaction_amount")
            credit_str = pick(norm, "credit", "deposit", "inflow")
            debit_str = pick(norm, "debit", "withdrawal", "outflow")

            if amt_str:
                signed_cents = _parse_money_signed_cents(amt_str)
            elif credit_str:
                signed_cents = abs(_parse_money_signed_cents(credit_str))
            elif debit_str:
                signed_cents = -abs(_parse_money_signed_cents(debit_str))
            else:
                raise ValueError("Missing Amount or Credit/Debit columns")

            if signed_cents == 0:
                continue

            type_col = pick(norm, "type", "transaction_type").lower()
            if signed_cents > 0 and type_col in ("debit", "withdrawal", "ach_debit"):
                signed_cents = -signed_cents

            direction: TxDirection = "credit" if signed_cents > 0 else "debit"
            amount_cents = abs(signed_cents)

            bal_str = pick(norm, "balance", "running_bal", "running_balance")
            if bal_str and latest_balance is None:
                with suppress(ValueError):
                    latest_balance = _parse_money_signed_cents(bal_str)

            explicit_id = _clean(
                pick(norm, "transaction_id", "fitid", "reference", "check_or_slip"),
                max_len=120,
            )
            if explicit_id and len(explicit_id) >= 4:
                ext_id = explicit_id
            else:
                base_sig = f"{posted.isoformat()}|{direction}|{amount_cents}|{desc.lower()}"
                occ = seen_sigs[base_sig]
                seen_sigs[base_sig] += 1
                ext_id = f"csv-{hashlib.sha256(f'{base_sig}|{occ}'.encode()).hexdigest()[:24]}"

            txs.append(
                ParsedBankTransaction(
                    external_tx_id=ext_id,
                    posted_date=posted,
                    description=desc,
                    merchant_name=merchant,
                    direction=direction,
                    amount_cents=amount_cents,
                    category_hint=infer_bank_category(desc, direction),
                )
            )
        except Exception as exc:
            errors.append(f"Row {idx}: {exc}")

    return txs, latest_balance, errors


def parse_bank_statement(
    raw_content: str,
    requested_format: Literal["auto", "ofx", "qfx", "qbo", "csv"] = "auto",
) -> tuple[SourceFormat, list[ParsedBankTransaction], int | None, list[str]]:
    """Detect format (OFX/QFX/QBO vs CSV) and parse deterministically."""
    upper_head = raw_content[:2000].upper()
    is_ofx = "<OFX>" in upper_head or "<STMTTRN>" in upper_head or "OFXHEADER:" in upper_head

    if requested_format in ("ofx", "qfx", "qbo") or (requested_format == "auto" and is_ofx):
        fmt: SourceFormat = requested_format if requested_format in ("ofx", "qfx", "qbo") else "ofx"
        txs, bal, errs = parse_ofx_statement(raw_content)
        return fmt, txs, bal, errs

    txs, bal, errs = parse_bank_csv_statement(raw_content)
    return "csv", txs, bal, errs


def find_best_reconciliation_match(
    tx: ParsedBankTransaction,
    candidates: list[LedgerMatchCandidate],
) -> tuple[LedgerMatchCandidate, int] | None:
    """Score live ledger/PO/Stripe/Payroll candidates for Human-in-the-Loop bank matching."""
    tx_tokens = _tokenize(f"{tx.description} {tx.merchant_name}")
    best: tuple[LedgerMatchCandidate, int] | None = None

    for cand in candidates:
        if cand.direction != tx.direction:
            continue
        diff = abs(cand.amount_cents - tx.amount_cents)
        tol = max(500, round(tx.amount_cents * 0.01))
        if diff == 0:
            score = 65
        elif diff <= tol:
            score = 40
        else:
            continue

        day_delta = abs((tx.posted_date - cand.ref_date).days)
        if day_delta <= 3:
            score += 20
        elif day_delta <= 10:
            score += 12
        elif day_delta <= 30:
            score += 5

        if tx_tokens and cand.tokens and (tx_tokens & cand.tokens):
            score += 15

        if score >= 65 and (best is None or score > best[1]):
            best = (cand, min(100, score))

    return best


async def _load_reconciliation_candidates(
    cur: Any,
    business_id: UUID,
) -> list[LedgerMatchCandidate]:
    """Load recent tenant financial records under FORCE RLS for smart auto-matching."""
    candidates: list[LedgerMatchCandidate] = []
    cutoff = datetime.now(UTC).date() - timedelta(days=120)

    # 1. Paid Stripe payment sessions (credits)
    await cur.execute(
        """
        SELECT id, customer_name, description, reference_id, amount_cents,
               COALESCE(paid_at, created_at)::date AS ref_date
        FROM gba.payment_sessions
        WHERE tenant_id = %s AND status = 'paid'
          AND COALESCE(paid_at, created_at)::date >= %s
        ORDER BY created_at DESC LIMIT 200
        """,
        (business_id, cutoff),
    )
    for r in await cur.fetchall():
        label = f"Stripe · {r['customer_name'] or r['description']}"[:180]
        toks = _tokenize(
            f"stripe {r['customer_name']} {r['description']} {r['reference_id'] or ''}"
        )
        candidates.append(
            LedgerMatchCandidate(
                kind="payment_session",
                entity_id=str(r["id"]),
                label=label,
                direction="credit",
                amount_cents=int(r["amount_cents"]),
                ref_date=r["ref_date"],
                tokens=toks,
            )
        )

    # 2. Issued Double-Entry FIN-03 invoices (receivable = credit, payable = debit)
    await cur.execute(
        """
        WITH latest AS (
            SELECT DISTINCT ON (book_id, document_id)
                document_id, direction, state, number, title, invoice_date, principal_minor
            FROM gba.financial_document_versions
            WHERE tenant_id = %s
            ORDER BY book_id, document_id, revision DESC
        )
        SELECT document_id, direction, number, title, invoice_date, principal_minor
        FROM latest
        WHERE state = 'issued' AND invoice_date >= %s
        ORDER BY invoice_date DESC LIMIT 200
        """,
        (business_id, cutoff),
    )
    for r in await cur.fetchall():
        direction: TxDirection = "credit" if r["direction"] == "receivable" else "debit"
        label = f"FIN-03 {r['number']} · {r['title']}"[:180]
        candidates.append(
            LedgerMatchCandidate(
                kind="invoice",
                entity_id=str(r["document_id"]),
                label=label,
                direction=direction,
                amount_cents=int(r["principal_minor"]),
                ref_date=r["invoice_date"],
                tokens=_tokenize(f"{r['number']} {r['title']}"),
            )
        )

    # 3. Active B2B Purchase Orders (debits)
    await cur.execute(
        """
        SELECT id, po_number, vendor_name, title, total_cents, created_at::date AS ref_date
        FROM gba.purchase_orders
        WHERE tenant_id = %s AND status != 'cancelled'
          AND created_at::date >= %s
        ORDER BY created_at DESC LIMIT 200
        """,
        (business_id, cutoff),
    )
    for r in await cur.fetchall():
        label = f"PO {r['po_number']} · {r['vendor_name']}"[:180]
        candidates.append(
            LedgerMatchCandidate(
                kind="purchase_order",
                entity_id=str(r["id"]),
                label=label,
                direction="debit",
                amount_cents=int(r["total_cents"]),
                ref_date=r["ref_date"],
                tokens=_tokenize(f"{r['po_number']} {r['vendor_name']} {r['title']}"),
            )
        )

    # 4. US Payroll runs (debits)
    await cur.execute(
        """
        SELECT id, run_number, pay_date,
               (total_gross_cents + total_employer_taxes_cents) AS total_outflow_cents
        FROM gba.payroll_runs
        WHERE tenant_id = %s AND status != 'void' AND pay_date >= %s
        ORDER BY pay_date DESC LIMIT 100
        """,
        (business_id, cutoff),
    )
    for r in await cur.fetchall():
        if int(r["total_outflow_cents"] or 0) <= 0:
            continue
        label = f"Payroll {r['run_number']} ({r['pay_date']})"
        candidates.append(
            LedgerMatchCandidate(
                kind="payroll_run",
                entity_id=str(r["id"]),
                label=label,
                direction="debit",
                amount_cents=int(r["total_outflow_cents"]),
                ref_date=r["pay_date"],
                tokens=_tokenize(f"payroll gusto adp {r['run_number']}"),
            )
        )

    return candidates


async def _load_plaid_status(cur: Any, conn: Any, business_id: UUID) -> PlaidStatusView:
    pub = await get_tenant_secret_public(
        conn,
        tenant_id=business_id,
        connector_id=PLAID_CONNECTOR_ID,
        kind="plugin_credential",
    )
    if pub is not None:
        env_raw = str(pub.metadata_public.get("plaid_env", "sandbox"))
        plaid_env: Literal["sandbox", "production"] = (
            "production" if env_raw == "production" else "sandbox"
        )
        return PlaidStatusView(
            configured=True,
            source="tenant_vault_byok",
            plaid_env=plaid_env,
            client_id_hint=str(pub.metadata_public.get("client_id_masked") or pub.key_hint),
            updated_at=pub.updated_at,
            supported_institutions=list(SUPPORTED_US_INSTITUTIONS),
        )

    env_cid = os.environ.get("PLAID_CLIENT_ID", "").strip()
    env_sec = os.environ.get("PLAID_SECRET", "").strip()
    if env_cid and env_sec:
        env_mode = os.environ.get("PLAID_ENV", "sandbox").strip().lower()
        return PlaidStatusView(
            configured=True,
            source="platform_env",
            plaid_env="production" if env_mode == "production" else "sandbox",
            client_id_hint=mask_secret_hint(env_cid),
            updated_at=None,
            supported_institutions=list(SUPPORTED_US_INSTITUTIONS),
        )

    return PlaidStatusView(
        configured=False,
        source="none",
        plaid_env="sandbox",
        client_id_hint=None,
        updated_at=None,
        supported_institutions=list(SUPPORTED_US_INSTITUTIONS),
    )


async def _fetch_accounts_with_counts(cur: Any, business_id: UUID) -> list[BankAccountView]:
    await cur.execute(
        """
        SELECT a.id,
               a.institution_name,
               a.account_name,
               a.account_mask,
               a.account_type,
               a.currency,
               a.connection_mode,
               a.current_balance_cents,
               a.last_synced_at,
               a.is_active,
               COUNT(t.id) FILTER (WHERE t.reconciliation_status = 'unmatched')::int
                   AS unmatched_count,
               COUNT(t.id) FILTER (WHERE t.reconciliation_status = 'suggested')::int
                   AS suggested_count,
               COUNT(t.id) FILTER (WHERE t.reconciliation_status = 'reconciled')::int
                   AS reconciled_count
        FROM gba.bank_feed_accounts a
        LEFT JOIN gba.bank_feed_transactions t
          ON t.tenant_id = a.tenant_id AND t.bank_account_id = a.id
        WHERE a.tenant_id = %s
        GROUP BY a.id
        ORDER BY a.created_at DESC
        """,
        (business_id,),
    )
    rows = await cur.fetchall()
    return [
        BankAccountView(
            id=r["id"],
            institution_name=str(r["institution_name"]),
            account_name=str(r["account_name"]),
            account_mask=str(r["account_mask"]),
            account_type=r["account_type"],
            currency=r["currency"],
            connection_mode=r["connection_mode"],
            current_balance_cents=int(r["current_balance_cents"]),
            last_synced_at=r["last_synced_at"],
            is_active=bool(r["is_active"]),
            unmatched_count=int(r["unmatched_count"]),
            suggested_count=int(r["suggested_count"]),
            reconciled_count=int(r["reconciled_count"]),
        )
        for r in rows
    ]


@router.get(
    "/v1/businesses/{business_id}/banking/summary",
    response_model=BankFeedsSummaryResponse,
)
async def get_bank_feeds_summary(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> BankFeedsSummaryResponse:
    """Return US bank feed accounts, reconciliation KPIs, and Plaid BYOK connector status."""
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
        accounts = await _fetch_accounts_with_counts(cur, business_id)
        await cur.execute(
            """
            SELECT COUNT(*)::int AS total_tx,
                   COUNT(*) FILTER (WHERE reconciliation_status = 'unmatched')::int AS unmatched,
                   COUNT(*) FILTER (WHERE reconciliation_status = 'suggested')::int AS suggested,
                   COUNT(*) FILTER (WHERE reconciliation_status = 'reconciled')::int AS reconciled,
                   COUNT(*) FILTER (WHERE reconciliation_status = 'excluded')::int AS excluded
            FROM gba.bank_feed_transactions
            WHERE tenant_id = %s
            """,
            (business_id,),
        )
        stats = await cur.fetchone() or {
            "total_tx": 0,
            "unmatched": 0,
            "suggested": 0,
            "reconciled": 0,
            "excluded": 0,
        }
        plaid_status = await _load_plaid_status(cur, session.conn, business_id)

    total_tx = int(stats["total_tx"])
    reconciled = int(stats["reconciled"])
    excluded = int(stats["excluded"])
    active_denom = max(0, total_tx - excluded)
    rec_rate = round((reconciled / active_denom) * 100.0, 1) if active_denom > 0 else 0.0

    return BankFeedsSummaryResponse(
        accounts=accounts,
        total_balance_cents=sum(a.current_balance_cents for a in accounts if a.is_active),
        total_transactions=total_tx,
        unmatched_count=int(stats["unmatched"]),
        suggested_count=int(stats["suggested"]),
        reconciled_count=reconciled,
        excluded_count=excluded,
        reconciliation_rate_pct=rec_rate,
        plaid_status=plaid_status,
    )


@router.post(
    "/v1/businesses/{business_id}/banking/accounts",
    response_model=BankAccountView,
    status_code=status.HTTP_201_CREATED,
)
async def create_bank_account(
    business_id: UUID,
    body: CreateBankAccountRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> BankAccountView:
    """Register a US business bank account for OFX/QFX/QBO/CSV or Plaid feeds."""
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
            INSERT INTO gba.bank_feed_accounts (
                tenant_id, institution_name, account_name, account_mask,
                account_type, currency, connection_mode, current_balance_cents,
                created_by_user_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, 'statement_upload', %s, %s)
            RETURNING id, institution_name, account_name, account_mask, account_type,
                      currency, connection_mode, current_balance_cents, last_synced_at, is_active
            """,
            (
                business_id,
                _clean(body.institution_name, max_len=120),
                _clean(body.account_name, max_len=120),
                body.account_mask,
                body.account_type,
                body.currency,
                body.current_balance_cents,
                session.principal.user_id,
            ),
        )
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=500, detail="Failed to create bank feed account.")
    return BankAccountView(
        id=row["id"],
        institution_name=str(row["institution_name"]),
        account_name=str(row["account_name"]),
        account_mask=str(row["account_mask"]),
        account_type=row["account_type"],
        currency=row["currency"],
        connection_mode=row["connection_mode"],
        current_balance_cents=int(row["current_balance_cents"]),
        last_synced_at=row["last_synced_at"],
        is_active=bool(row["is_active"]),
        unmatched_count=0,
        suggested_count=0,
        reconciled_count=0,
    )


@router.post(
    "/v1/businesses/{business_id}/banking/accounts/{account_id}/import",
    response_model=BankStatementImportResponse,
)
async def import_bank_statement(
    business_id: UUID,
    account_id: UUID,
    body: BankStatementImportRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> BankStatementImportResponse:
    """Import US bank OFX/QFX/QBO/CSV statements with dry-run preview and auto-matching."""
    fmt, parsed, detected_bal, errors = parse_bank_statement(body.raw_content, body.source_format)
    preview = [
        ParsedBankTxPreview(
            external_tx_id=t.external_tx_id,
            posted_date=t.posted_date.isoformat(),
            description=t.description,
            merchant_name=t.merchant_name,
            direction=t.direction,
            amount_cents=t.amount_cents,
            category_hint=t.category_hint,
        )
        for t in parsed[:25]
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
        await cur.execute(
            "SELECT id, currency FROM gba.bank_feed_accounts WHERE tenant_id = %s AND id = %s",
            (business_id, account_id),
        )
        acct = await cur.fetchone()
        if acct is None:
            raise HTTPException(status_code=404, detail="Bank feed account not found.")

        candidates = await _load_reconciliation_candidates(cur, business_id)
        if body.dry_run:
            suggested_preview = sum(
                1 for t in parsed if find_best_reconciliation_match(t, candidates) is not None
            )
            return BankStatementImportResponse(
                detected_format=fmt,
                dry_run=True,
                parsed_count=len(parsed),
                imported_count=0,
                duplicate_skipped_count=0,
                suggested_match_count=suggested_preview,
                detected_balance_cents=detected_bal,
                errors=errors[:25],
                preview=preview,
            )

        imported = 0
        duplicates = 0
        suggested = 0
        acct_currency = str(acct["currency"])

        for tx in parsed:
            match = find_best_reconciliation_match(tx, candidates)
            rec_status: ReconciliationStatus = "suggested" if match is not None else "unmatched"
            m_kind = match[0].kind if match is not None else None
            m_id = match[0].entity_id if match is not None else None
            m_label = match[0].label if match is not None else ""
            m_conf = match[1] if match is not None else 0

            await cur.execute(
                """
                INSERT INTO gba.bank_feed_transactions (
                    tenant_id, bank_account_id, external_tx_id, posted_date,
                    description, merchant_name, direction, amount_cents, currency,
                    category_hint, source_format, reconciliation_status,
                    matched_entity_kind, matched_entity_id, matched_entity_label,
                    match_confidence
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, bank_account_id, external_tx_id) DO NOTHING
                RETURNING id
                """,
                (
                    business_id,
                    account_id,
                    tx.external_tx_id,
                    tx.posted_date,
                    tx.description,
                    tx.merchant_name,
                    tx.direction,
                    tx.amount_cents,
                    acct_currency,
                    tx.category_hint,
                    fmt,
                    rec_status,
                    m_kind,
                    m_id,
                    m_label,
                    m_conf,
                ),
            )
            inserted = await cur.fetchone()
            if inserted is not None:
                imported += 1
                if match is not None:
                    suggested += 1
            else:
                duplicates += 1

        if detected_bal is not None:
            await cur.execute(
                """
                UPDATE gba.bank_feed_accounts
                SET current_balance_cents = %s, last_synced_at = now(), updated_at = now()
                WHERE tenant_id = %s AND id = %s
                """,
                (detected_bal, business_id, account_id),
            )
        else:
            await cur.execute(
                """
                UPDATE gba.bank_feed_accounts
                SET last_synced_at = now(), updated_at = now()
                WHERE tenant_id = %s AND id = %s
                """,
                (business_id, account_id),
            )

    return BankStatementImportResponse(
        detected_format=fmt,
        dry_run=False,
        parsed_count=len(parsed),
        imported_count=imported,
        duplicate_skipped_count=duplicates,
        suggested_match_count=suggested,
        detected_balance_cents=detected_bal,
        errors=errors[:25],
        preview=preview,
    )


@router.get(
    "/v1/businesses/{business_id}/banking/transactions",
    response_model=list[BankTransactionView],
)
async def list_bank_transactions(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    account_id: Annotated[UUID | None, Query()] = None,
    reconciliation_status: Annotated[ReconciliationStatus | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[BankTransactionView]:
    """List bank feed transactions for Human-in-the-Loop reconciliation."""
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
        await cur.execute(
            """
            SELECT t.id,
                   t.bank_account_id,
                   (a.institution_name || ' ••' || a.account_mask) AS account_label,
                   t.external_tx_id,
                   t.posted_date,
                   t.description,
                   t.merchant_name,
                   t.direction,
                   t.amount_cents,
                   t.currency,
                   t.category_hint,
                   t.source_format,
                   t.reconciliation_status,
                   t.matched_entity_kind,
                   t.matched_entity_id,
                   t.matched_entity_label,
                   t.match_confidence,
                   t.reconciled_at,
                   t.notes
            FROM gba.bank_feed_transactions t
            JOIN gba.bank_feed_accounts a
              ON a.tenant_id = t.tenant_id AND a.id = t.bank_account_id
            WHERE t.tenant_id = %s
              AND (%s::uuid IS NULL OR t.bank_account_id = %s::uuid)
              AND (%s::text IS NULL OR t.reconciliation_status = %s::text)
            ORDER BY t.posted_date DESC, t.created_at DESC
            LIMIT %s
            """,
            (
                business_id,
                account_id,
                account_id,
                reconciliation_status,
                reconciliation_status,
                limit,
            ),
        )
        rows = await cur.fetchall()

    return [
        BankTransactionView(
            id=r["id"],
            bank_account_id=r["bank_account_id"],
            account_label=str(r["account_label"]),
            external_tx_id=str(r["external_tx_id"]),
            posted_date=r["posted_date"],
            description=str(r["description"]),
            merchant_name=str(r["merchant_name"]),
            direction=r["direction"],
            amount_cents=int(r["amount_cents"]),
            currency=r["currency"],
            category_hint=str(r["category_hint"]),
            source_format=r["source_format"],
            reconciliation_status=r["reconciliation_status"],
            matched_entity_kind=r["matched_entity_kind"],
            matched_entity_id=r["matched_entity_id"],
            matched_entity_label=str(r["matched_entity_label"]),
            match_confidence=int(r["match_confidence"]),
            reconciled_at=r["reconciled_at"],
            notes=str(r["notes"]),
        )
        for r in rows
    ]


@router.post(
    "/v1/businesses/{business_id}/banking/transactions/{tx_id}/reconcile",
    response_model=BankTransactionView,
)
async def reconcile_bank_transaction(
    business_id: UUID,
    tx_id: UUID,
    body: ReconcileTransactionRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> BankTransactionView:
    """Confirm a suggested match, categorize manually, exclude, or unmatch a bank transaction."""
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
            SELECT id, matched_entity_kind, matched_entity_id, matched_entity_label,
                   match_confidence, category_hint
            FROM gba.bank_feed_transactions
            WHERE tenant_id = %s AND id = %s
            """,
            (business_id, tx_id),
        )
        existing = await cur.fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="Bank transaction not found.")

        new_status: ReconciliationStatus
        m_kind = existing["matched_entity_kind"]
        m_id = existing["matched_entity_id"]
        m_label = str(existing["matched_entity_label"] or "")
        m_conf = int(existing["match_confidence"] or 0)
        cat = _clean(body.category_hint, max_len=80) or str(existing["category_hint"])
        rec_at: datetime | None = datetime.now(UTC)
        rec_by: UUID | None = session.principal.user_id

        if body.action == "confirm_match":
            new_status = "reconciled"
            if body.matched_entity_kind is not None:
                m_kind = body.matched_entity_kind
            if body.matched_entity_id is not None:
                m_id = body.matched_entity_id
            if body.matched_entity_label:
                m_label = _clean(body.matched_entity_label, max_len=200)
            m_conf = max(m_conf, 100)
        elif body.action == "manual_category":
            new_status = "reconciled"
            m_kind = "manual_category"
            m_id = cat
            m_label = _clean(body.matched_entity_label or f"Category: {cat}", max_len=200)
            m_conf = 100
        elif body.action == "exclude":
            new_status = "excluded"
            m_kind = None
            m_id = None
            m_label = "Excluded (Transfer / Duplicate)"
            m_conf = 0
        else:
            new_status = "unmatched"
            m_kind = None
            m_id = None
            m_label = ""
            m_conf = 0
            rec_at = None
            rec_by = None

        await cur.execute(
            """
            UPDATE gba.bank_feed_transactions
            SET reconciliation_status = %s,
                matched_entity_kind = %s,
                matched_entity_id = %s,
                matched_entity_label = %s,
                match_confidence = %s,
                category_hint = %s,
                notes = %s,
                reconciled_by_user_id = %s,
                reconciled_at = %s,
                updated_at = now()
            WHERE tenant_id = %s AND id = %s
            """,
            (
                new_status,
                m_kind,
                m_id,
                m_label,
                m_conf,
                cat,
                _clean(body.notes, max_len=500),
                rec_by,
                rec_at,
                business_id,
                tx_id,
            ),
        )
        await cur.execute(
            """
            SELECT t.id, t.bank_account_id,
                   (a.institution_name || ' ••' || a.account_mask) AS account_label,
                   t.external_tx_id, t.posted_date, t.description, t.merchant_name,
                   t.direction, t.amount_cents, t.currency, t.category_hint,
                   t.source_format, t.reconciliation_status, t.matched_entity_kind,
                   t.matched_entity_id, t.matched_entity_label, t.match_confidence,
                   t.reconciled_at, t.notes
            FROM gba.bank_feed_transactions t
            JOIN gba.bank_feed_accounts a
              ON a.tenant_id = t.tenant_id AND a.id = t.bank_account_id
            WHERE t.tenant_id = %s AND t.id = %s
            """,
            (business_id, tx_id),
        )
        r = await cur.fetchone()

    if r is None:
        raise HTTPException(status_code=404, detail="Bank transaction not found.")
    return BankTransactionView(
        id=r["id"],
        bank_account_id=r["bank_account_id"],
        account_label=str(r["account_label"]),
        external_tx_id=str(r["external_tx_id"]),
        posted_date=r["posted_date"],
        description=str(r["description"]),
        merchant_name=str(r["merchant_name"]),
        direction=r["direction"],
        amount_cents=int(r["amount_cents"]),
        currency=r["currency"],
        category_hint=str(r["category_hint"]),
        source_format=r["source_format"],
        reconciliation_status=r["reconciliation_status"],
        matched_entity_kind=r["matched_entity_kind"],
        matched_entity_id=r["matched_entity_id"],
        matched_entity_label=str(r["matched_entity_label"]),
        match_confidence=int(r["match_confidence"]),
        reconciled_at=r["reconciled_at"],
        notes=str(r["notes"]),
    )


@router.post(
    "/v1/businesses/{business_id}/banking/plaid/credentials",
    response_model=PlaidStatusView,
)
async def save_plaid_byok_credentials(
    business_id: UUID,
    body: SavePlaidCredentialsRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> PlaidStatusView:
    """Encrypt and store tenant BYOK Plaid credentials inside AMARKAL AES-256-GCM Secret Vault."""
    settings = request.app.state.settings
    payload_str = json.dumps({"client_id": body.client_id.strip(), "secret": body.secret.strip()})

    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_MANAGE,
        request_id=get_request_id(request),
    ) as session:
        pub = await upsert_tenant_secret(
            session.conn,
            tenant_id=business_id,
            connector_id=PLAID_CONNECTOR_ID,
            kind="plugin_credential",
            plaintext=payload_str,
            metadata_public={
                "plaid_env": body.plaid_env,
                "client_id_masked": mask_secret_hint(body.client_id),
            },
            user_id=session.principal.user_id,
            environment=settings.environment,
            hint_source=body.client_id,
        )

    return PlaidStatusView(
        configured=True,
        source="tenant_vault_byok",
        plaid_env=body.plaid_env,
        client_id_hint=str(pub.metadata_public.get("client_id_masked") or pub.key_hint),
        updated_at=pub.updated_at,
        supported_institutions=list(SUPPORTED_US_INSTITUTIONS),
    )


@router.post(
    "/v1/businesses/{business_id}/banking/plaid/sandbox-sync",
    response_model=PlaidSandboxSyncResponse,
)
async def sync_plaid_sandbox_feed(
    business_id: UUID,
    body: PlaidSandboxSyncRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> PlaidSandboxSyncResponse:
    """Run an idempotent Plaid Sandbox US bank feed sync & auto-reconciliation preview."""
    today = datetime.now(UTC).date()
    sample_txs = [
        ParsedBankTransaction(
            external_tx_id=f"plaid-sbx-{body.account_mask}-001",
            posted_date=today - timedelta(days=1),
            description="STRIPE US PAYOUT ACH SETTLEMENT (0% AMARKAL FEE)",
            merchant_name="Stripe US",
            direction="credit",
            amount_cents=1845000,
            category_hint="client_payment",
        ),
        ParsedBankTransaction(
            external_tx_id=f"plaid-sbx-{body.account_mask}-002",
            posted_date=today - timedelta(days=2),
            description="ACH WIRE IN — MIDWEST COLD CHAIN LOGISTICS INC",
            merchant_name="Midwest Cold Chain Logistics",
            direction="credit",
            amount_cents=960000,
            category_hint="client_payment",
        ),
        ParsedBankTransaction(
            external_tx_id=f"plaid-sbx-{body.account_mask}-003",
            posted_date=today - timedelta(days=3),
            description="PILOT FLYING J FLEET DIESEL CARD #04",
            merchant_name="Pilot Flying J",
            direction="debit",
            amount_cents=218500,
            category_hint="fleet_fuel",
        ),
        ParsedBankTransaction(
            external_tx_id=f"plaid-sbx-{body.account_mask}-004",
            posted_date=today - timedelta(days=4),
            description="GUSTO US PAYROLL ACH DEBIT — BIWEEKLY RUN",
            merchant_name="Gusto Payroll",
            direction="debit",
            amount_cents=642000,
            category_hint="payroll",
        ),
        ParsedBankTransaction(
            external_tx_id=f"plaid-sbx-{body.account_mask}-005",
            posted_date=today - timedelta(days=5),
            description="GOOGLE CLOUD PLATFORM US-CENTRAL1 HOSTING",
            merchant_name="Google Cloud",
            direction="debit",
            amount_cents=48900,
            category_hint="software_cloud",
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
        await cur.execute(
            """
            SELECT id FROM gba.bank_feed_accounts
            WHERE tenant_id = %s
              AND institution_name = %s
              AND account_mask = %s
            LIMIT 1
            """,
            (business_id, body.institution_name, body.account_mask),
        )
        existing_acct = await cur.fetchone()
        if existing_acct is None:
            await cur.execute(
                """
                INSERT INTO gba.bank_feed_accounts (
                    tenant_id, institution_name, account_name, account_mask,
                    account_type, currency, connection_mode, plaid_item_id,
                    current_balance_cents, last_synced_at, created_by_user_id
                )
                VALUES (%s, %s, %s, %s, 'checking', 'USD', 'plaid_sandbox', %s, 14825000, now(), %s)
                RETURNING id
                """,
                (
                    business_id,
                    _clean(body.institution_name, max_len=120),
                    _clean(body.account_name, max_len=120),
                    body.account_mask,
                    f"item-sbx-{body.account_mask}",
                    session.principal.user_id,
                ),
            )
            acct_row = await cur.fetchone()
            if acct_row is None:
                raise HTTPException(status_code=500, detail="Unable to create Plaid sandbox feed.")
            account_id = acct_row["id"]
        else:
            account_id = existing_acct["id"]
            await cur.execute(
                """
                UPDATE gba.bank_feed_accounts
                SET last_synced_at = now(), updated_at = now()
                WHERE tenant_id = %s AND id = %s
                """,
                (business_id, account_id),
            )

        candidates = await _load_reconciliation_candidates(cur, business_id)
        imported = 0
        duplicates = 0
        suggested = 0

        for tx in sample_txs:
            match = find_best_reconciliation_match(tx, candidates)
            rec_status: ReconciliationStatus = "suggested" if match is not None else "unmatched"
            await cur.execute(
                """
                INSERT INTO gba.bank_feed_transactions (
                    tenant_id, bank_account_id, external_tx_id, posted_date,
                    description, merchant_name, direction, amount_cents, currency,
                    category_hint, source_format, reconciliation_status,
                    matched_entity_kind, matched_entity_id, matched_entity_label,
                    match_confidence
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'USD', %s, 'plaid', %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, bank_account_id, external_tx_id) DO NOTHING
                RETURNING id
                """,
                (
                    business_id,
                    account_id,
                    tx.external_tx_id,
                    tx.posted_date,
                    tx.description,
                    tx.merchant_name,
                    tx.direction,
                    tx.amount_cents,
                    tx.category_hint,
                    rec_status,
                    match[0].kind if match is not None else None,
                    match[0].entity_id if match is not None else None,
                    match[0].label if match is not None else "",
                    match[1] if match is not None else 0,
                ),
            )
            if await cur.fetchone() is not None:
                imported += 1
                if match is not None:
                    suggested += 1
            else:
                duplicates += 1

        accounts = await _fetch_accounts_with_counts(cur, business_id)
        target = next((a for a in accounts if a.id == account_id), accounts[0])

    return PlaidSandboxSyncResponse(
        account=target,
        imported_count=imported,
        duplicate_skipped_count=duplicates,
        suggested_match_count=suggested,
        message=(
            f"Synced {imported} new US bank transactions from {body.institution_name} "
            f"(••{body.account_mask}); {duplicates} duplicates skipped, "
            f"{suggested} auto-match suggestions ready for review."
        ),
    )
