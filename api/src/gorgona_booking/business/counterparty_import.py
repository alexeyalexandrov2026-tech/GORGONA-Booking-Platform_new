"""Managed B2B CSV counterparty importer with dry-run validation and duplicate detection."""

from __future__ import annotations

import csv
import io
from typing import Literal
from uuid import UUID, uuid7

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from gorgona_booking.business import counterparties as counterparty_service
from gorgona_booking.business.counterparty_contracts import (
    CounterpartyInput,
    CounterpartyKind,
    CounterpartyRole,
)
from gorgona_booking.db.pool import RuntimeConnection

MAX_IMPORT_CSV_CHARS = 262_144
MAX_IMPORT_ROWS = 250

_ALLOWED_ROLES: frozenset[str] = frozenset({"customer", "supplier", "contractor", "partner"})
_NAME_ALIASES = (
    "display_name",
    "display name",
    "name",
    "company",
    "company_name",
    "company name",
    "customer",
    "vendor",
    "client",
    "full_name",
    "full name",
)
_LEGAL_ALIASES = ("legal_name", "legal name", "registered_name", "registered name")
_EMAIL_ALIASES = ("email", "e-mail", "email_address", "email address", "primary_email")
_PHONE_ALIASES = ("phone", "phone_number", "phone number", "mobile", "telephone", "tel")
_TAX_ALIASES = ("tax_id", "tax id", "ein", "tin", "vat")
_REG_ALIASES = ("registration_number", "registration number", "reg_number", "mc_number", "dot")
_KIND_ALIASES = ("kind", "type", "entity_type", "entity type")
_ROLE_ALIASES = ("roles", "role", "relationship", "category")


class CounterpartyImportRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    csv_text: str = Field(min_length=3, max_length=MAX_IMPORT_CSV_CHARS)
    dry_run: bool = True
    skip_duplicates: bool = True
    default_kind: CounterpartyKind = "organization"
    default_role: CounterpartyRole = "customer"


class CounterpartyImportRowResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    row_number: int
    display_name: str
    kind: CounterpartyKind
    email: str | None = None
    phone: str | None = None
    roles: list[CounterpartyRole] = Field(default_factory=list)
    status: Literal["valid", "created", "duplicate", "error"]
    message: str
    counterparty_id: UUID | None = None


class CounterpartyImportResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    dry_run: bool
    total_rows: int
    valid_count: int
    created_count: int
    duplicate_count: int
    error_count: int
    rows: list[CounterpartyImportRowResult]


def _pick(normalized: dict[str, str], aliases: tuple[str, ...]) -> str | None:
    for alias in aliases:
        val = normalized.get(alias)
        if val is not None and val.strip():
            return val.strip()
    return None


def _parse_kind(raw: str | None, default: CounterpartyKind) -> CounterpartyKind:
    if not raw:
        return default
    low = raw.strip().lower()
    if low in ("person", "individual", "contact", "consumer", "solo"):
        return "person"
    if low in ("organization", "org", "company", "business", "llc", "inc", "corp", "vendor"):
        return "organization"
    return default


def _parse_roles(raw: str | None, default: CounterpartyRole) -> tuple[CounterpartyRole, ...]:
    if not raw:
        return (default,)
    found: list[CounterpartyRole] = []
    for part in raw.replace(";", ",").replace("|", ",").split(","):
        role_name = part.strip().lower()
        if role_name in ("client", "buyer", "account"):
            role_name = "customer"
        elif role_name in ("vendor", "distributor"):
            role_name = "supplier"
        elif role_name in ("subcontractor", "carrier", "freelancer"):
            role_name = "contractor"
        if role_name in _ALLOWED_ROLES and role_name not in found:
            found.append(role_name)  # type: ignore[arg-type]
    return tuple(found) if found else (default,)


def parse_counterparty_csv(
    csv_text: str,
    *,
    default_kind: CounterpartyKind = "organization",
    default_role: CounterpartyRole = "customer",
) -> list[tuple[int, CounterpartyInput | None, str, CounterpartyKind, str | None, str | None, str]]:
    """Parse CSV into validated CounterpartyInput items with row-level error messages."""
    cleaned_csv = csv_text.lstrip("\ufeff").strip()
    if not cleaned_csv:
        return []
    reader = csv.DictReader(io.StringIO(cleaned_csv))
    if not reader.fieldnames:
        return []

    parsed_rows: list[
        tuple[int, CounterpartyInput | None, str, CounterpartyKind, str | None, str | None, str]
    ] = []
    for idx, raw_row in enumerate(reader, start=2):
        if len(parsed_rows) >= MAX_IMPORT_ROWS:
            break
        normalized = {
            (k or "").strip().lower(): (v or "").strip()
            for k, v in raw_row.items()
            if k is not None
        }
        if not any(normalized.values()):
            continue

        display_name = _pick(normalized, _NAME_ALIASES) or ""
        legal_name = _pick(normalized, _LEGAL_ALIASES)
        email = _pick(normalized, _EMAIL_ALIASES)
        phone = _pick(normalized, _PHONE_ALIASES)
        tax_id = _pick(normalized, _TAX_ALIASES)
        reg_no = _pick(normalized, _REG_ALIASES)
        kind = _parse_kind(_pick(normalized, _KIND_ALIASES), default_kind)
        roles = _parse_roles(_pick(normalized, _ROLE_ALIASES), default_role)

        if not display_name:
            parsed_rows.append(
                (
                    idx,
                    None,
                    "(missing name)",
                    kind,
                    email,
                    phone,
                    "Missing display_name/name column",
                )
            )
            continue

        try:
            item = CounterpartyInput(
                expected_revision=0,
                kind=kind,
                display_name=display_name,
                legal_name=legal_name,
                tax_id=tax_id,
                registration_number=reg_no,
                email=email,
                phone=phone,
                roles=roles,
                archived=False,
                contacts=(),
            )
        except ValidationError as exc:
            first_msg = exc.errors()[0].get("msg", "Invalid counterparty row")
            parsed_rows.append((idx, None, display_name, kind, email, phone, str(first_msg)))
            continue

        parsed_rows.append((idx, item, item.display_name, item.kind, item.email, item.phone, "OK"))
    return parsed_rows


async def _existing_duplicate_keys(
    conn: RuntimeConnection, business_id: UUID
) -> tuple[set[str], set[str]]:
    rows = await (
        await conn.execute(
            """
            SELECT DISTINCT ON (c.id)
                lower(btrim(v.display_name)) AS norm_name,
                lower(btrim(coalesce(v.email, ''))) AS norm_email,
                v.state
            FROM gba.counterparties c
            JOIN gba.counterparty_versions v
              ON v.tenant_id = c.tenant_id AND v.counterparty_id = c.id
            WHERE c.tenant_id = %s
            ORDER BY c.id, v.revision DESC
            """,
            (business_id,),
        )
    ).fetchall()
    names: set[str] = set()
    emails: set[str] = set()
    for norm_name, norm_email, state in rows:
        if state == "merged":
            continue
        if norm_name:
            names.add(str(norm_name))
        if norm_email:
            emails.add(str(norm_email))
    return names, emails


async def run_counterparty_import(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    user_id: UUID,
    actor: str,
    idempotency_key: str,
    body: CounterpartyImportRequest,
) -> CounterpartyImportResponse:
    parsed = parse_counterparty_csv(
        body.csv_text,
        default_kind=body.default_kind,
        default_role=body.default_role,
    )
    existing_names, existing_emails = await _existing_duplicate_keys(conn, business_id)

    results: list[CounterpartyImportRowResult] = []
    seen_batch_names: set[str] = set()
    seen_batch_emails: set[str] = set()
    valid_count = 0
    created_count = 0
    duplicate_count = 0
    error_count = 0

    for row_num, item, display_name, kind, email, phone, err_msg in parsed:
        if item is None:
            error_count += 1
            results.append(
                CounterpartyImportRowResult(
                    row_number=row_num,
                    display_name=display_name,
                    kind=kind,
                    email=email,
                    phone=phone,
                    status="error",
                    message=err_msg,
                )
            )
            continue

        norm_name = item.display_name.strip().lower()
        norm_email = item.email.strip().lower() if item.email else ""
        is_dup = (
            norm_name in existing_names
            or norm_name in seen_batch_names
            or (
                bool(norm_email)
                and (norm_email in existing_emails or norm_email in seen_batch_emails)
            )
        )
        if is_dup and body.skip_duplicates:
            duplicate_count += 1
            results.append(
                CounterpartyImportRowResult(
                    row_number=row_num,
                    display_name=item.display_name,
                    kind=item.kind,
                    email=item.email,
                    phone=item.phone,
                    roles=list(item.roles),
                    status="duplicate",
                    message="Matches an existing or earlier counterparty in this import.",
                )
            )
            continue

        seen_batch_names.add(norm_name)
        if norm_email:
            seen_batch_emails.add(norm_email)

        if body.dry_run:
            valid_count += 1
            results.append(
                CounterpartyImportRowResult(
                    row_number=row_num,
                    display_name=item.display_name,
                    kind=item.kind,
                    email=item.email,
                    phone=item.phone,
                    roles=list(item.roles),
                    status="valid",
                    message="Ready to import.",
                )
            )
            continue

        new_id = uuid7()
        row_key = f"imp-{idempotency_key[:96]}-r{row_num}"[:120]
        saved = await counterparty_service.save_counterparty(
            conn,
            business_id=business_id,
            counterparty_id=new_id,
            user_id=user_id,
            actor=actor,
            key=row_key,
            body=item,
        )
        created_count += 1
        results.append(
            CounterpartyImportRowResult(
                row_number=row_num,
                display_name=saved.display_name,
                kind=saved.kind,
                email=saved.email,
                phone=saved.phone,
                roles=list(saved.roles),
                status="created",
                message="Imported into counterparties ledger.",
                counterparty_id=saved.counterparty_id,
            )
        )

    return CounterpartyImportResponse(
        dry_run=body.dry_run,
        total_rows=len(results),
        valid_count=valid_count,
        created_count=created_count,
        duplicate_count=duplicate_count,
        error_count=error_count,
        rows=results,
    )
