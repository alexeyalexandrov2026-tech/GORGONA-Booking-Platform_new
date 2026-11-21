"""PRO-01 Slice 4 (ADR-0038): FIN-03 matter invoicing and ACL-enforced audited exports."""

from datetime import date
from typing import Literal, Self
from uuid import UUID, uuid7

from psycopg import errors
from psycopg.rows import class_row
from pydantic import AwareDatetime, Field, field_validator, model_validator

from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.business import commands, financial_documents
from gorgona_booking.business.contracts import Strict, Versioned
from gorgona_booking.business.financial_contracts import InvoiceDraftInput, InvoiceLineInput
from gorgona_booking.business.ledger_contracts import from_minor
from gorgona_booking.business.module_gate import module_writes, require_module
from gorgona_booking.business.projects_matters import (
    PROJECTS_MODULE,
    ConflictCheckView,
    MatterView,
    ProjectsStateError,
    _check_ready,
    _clean_single_line,
    _require_matter_visible,
    get_matter,
    list_conflict_checks,
)
from gorgona_booking.business.projects_time import (
    RecurringRunView,
    RecurringScheduleView,
    TimeEntryView,
    list_recurring_runs,
    list_recurring_schedules,
    list_time_entries,
)
from gorgona_booking.business.projects_work import (
    MatterFileView,
    StageView,
    TaskView,
    list_matter_files,
    list_stages,
    list_tasks,
)
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import InvalidReferenceError, NotFoundError
from gorgona_booking.tenancy.authorization import PermissionDeniedError

InvoiceItemKind = Literal["time_entry", "stage_fee", "recurring_run"]
ExportScope = Literal["matter", "portfolio"]


class MatterInvoiceInput(Versioned):
    book_id: UUID
    receivable_account_id: UUID
    revenue_account_id: UUID
    invoice_date: date
    due_date: date
    title: str
    number: str | None = None
    time_entry_ids: list[UUID] = Field(default_factory=list, max_length=200)
    stage_ids: list[UUID] = Field(default_factory=list, max_length=100)
    recurring_run_ids: list[UUID] = Field(default_factory=list, max_length=100)

    @field_validator("title")
    @classmethod
    def valid_title(cls, value: str) -> str:
        return _clean_single_line(value, 200)

    @field_validator("number")
    @classmethod
    def valid_number(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _clean_single_line(value, 64)

    @model_validator(mode="after")
    def valid_dates_and_items(self) -> Self:
        if self.due_date < self.invoice_date:
            raise ValueError("Due date cannot precede invoice date")
        if not (self.time_entry_ids or self.stage_ids or self.recurring_run_ids):
            raise ValueError("Select at least one time entry, stage fee, or recurring run")
        if len(set(self.time_entry_ids)) != len(self.time_entry_ids):
            raise ValueError("Duplicate time_entry_ids are not allowed")
        if len(set(self.stage_ids)) != len(self.stage_ids):
            raise ValueError("Duplicate stage_ids are not allowed")
        if len(set(self.recurring_run_ids)) != len(self.recurring_run_ids):
            raise ValueError("Duplicate recurring_run_ids are not allowed")
        return self


class MatterInvoiceItemView(Strict):
    schema_version: Literal[1] = 1
    item_id: UUID
    matter_invoice_id: UUID
    item_kind: InvoiceItemKind
    time_entry_id: UUID | None
    stage_id: UUID | None
    recurring_run_id: UUID | None
    description: str
    amount_minor: int
    currency: str


class MatterInvoiceView(Strict):
    schema_version: Literal[1] = 1
    matter_invoice_id: UUID
    matter_id: UUID
    location_id: UUID
    book_id: UUID
    invoice_document_id: UUID
    counterparty_id: UUID
    total_minor: int
    currency: str
    title: str
    number: str | None
    invoice_date: date
    due_date: date
    recorded_by: UUID
    recorded_at: AwareDatetime
    items: list[MatterInvoiceItemView]


class MatterInvoiceList(Strict):
    schema_version: Literal[1] = 1
    items: list[MatterInvoiceView]


class PortfolioExportInput(Versioned):
    location_id: UUID


class ProjectExportRecord(Strict):
    schema_version: Literal[1] = 1
    export_id: UUID
    location_id: UUID
    scope: ExportScope
    matter_id: UUID | None
    requested_by: UUID
    matter_count: int
    stage_count: int
    task_count: int
    file_count: int
    time_entry_count: int
    recurring_run_count: int
    invoice_count: int
    recorded_at: AwareDatetime


class ProjectExportList(Strict):
    schema_version: Literal[1] = 1
    items: list[ProjectExportRecord]


class MatterExportBundle(Strict):
    matter: MatterView
    conflict_checks: list[ConflictCheckView]
    stages: list[StageView]
    tasks: list[TaskView]
    files: list[MatterFileView]
    time_entries: list[TimeEntryView]
    recurring_schedules: list[RecurringScheduleView]
    recurring_runs: list[RecurringRunView]
    invoices: list[MatterInvoiceView]


class MatterExportPayload(Strict):
    schema_version: Literal[1] = 1
    export: ProjectExportRecord
    bundle: MatterExportBundle


class PortfolioExportPayload(Strict):
    schema_version: Literal[1] = 1
    export: ProjectExportRecord
    matters: list[MatterExportBundle]


class _InvoiceReceipt(Strict):
    matter_invoice_id: UUID


class _ExportReceipt(Strict):
    export_id: UUID


async def _require_billing_role_if_restricted(
    conn: RuntimeConnection,
    business: UUID,
    matter_id: UUID,
    access_mode: str,
    user_id: UUID,
) -> None:
    if access_mode != "restricted":
        return
    row = await (
        await conn.execute(
            "select matter_role from gba.project_matter_members "
            "where tenant_id = %s and matter_id = %s and user_id = %s and revoked_at is null",
            (business, matter_id, user_id),
        )
    ).fetchone()
    if row is None or str(row[0]) not in ("lead", "billing"):
        raise PermissionDeniedError(
            "Only an active lead or billing member may invoice a restricted matter"
        )


async def _load_invoice(
    conn: RuntimeConnection, business: UUID, matter_id: UUID, matter_invoice_id: UUID
) -> MatterInvoiceView:
    row = await (
        await conn.execute(
            "select id, matter_id, location_id, book_id, invoice_document_id, counterparty_id, "
            "total_minor, currency, title, number, invoice_date, due_date, recorded_by, "
            "recorded_at from gba.project_matter_invoices "
            "where tenant_id = %s and matter_id = %s and id = %s",
            (business, matter_id, matter_invoice_id),
        )
    ).fetchone()
    if row is None:
        raise NotFoundError("Matter invoice not found")
    async with conn.cursor(row_factory=class_row(MatterInvoiceItemView)) as cur:
        await cur.execute(
            "select id as item_id, matter_invoice_id, item_kind, time_entry_id, stage_id, "
            "recurring_run_id, description, amount_minor, currency "
            "from gba.project_matter_invoice_items "
            "where tenant_id = %s and matter_invoice_id = %s order by id",
            (business, matter_invoice_id),
        )
        items = await cur.fetchall()
    return MatterInvoiceView(
        matter_invoice_id=UUID(str(row[0])),
        matter_id=UUID(str(row[1])),
        location_id=UUID(str(row[2])),
        book_id=UUID(str(row[3])),
        invoice_document_id=UUID(str(row[4])),
        counterparty_id=UUID(str(row[5])),
        total_minor=int(row[6]),
        currency=str(row[7]),
        title=str(row[8]),
        number=str(row[9]) if row[9] is not None else None,
        invoice_date=row[10],
        due_date=row[11],
        recorded_by=UUID(str(row[12])),
        recorded_at=row[13],
        items=items,
    )


async def list_matter_invoices(
    conn: RuntimeConnection, business: UUID, matter_id: UUID
) -> MatterInvoiceList:
    await _require_matter_visible(conn, business, matter_id)
    rows = await (
        await conn.execute(
            "select id from gba.project_matter_invoices "
            "where tenant_id = %s and matter_id = %s order by invoice_date desc, id desc",
            (business, matter_id),
        )
    ).fetchall()
    result = [await _load_invoice(conn, business, matter_id, UUID(str(r[0]))) for r in rows]
    return MatterInvoiceList(items=result)


async def create_matter_invoice(
    conn: RuntimeConnection,
    business: UUID,
    matter_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: MatterInvoiceInput,
) -> MatterInvoiceView:
    scope = IdempotencyScope(business, actor, "projects.invoice.create", key)
    fingerprint = commands.fingerprint(
        {"matter_id": str(matter_id), "body": body.model_dump(mode="json")}
    )
    receipt = await commands.claim(conn, scope, fingerprint, _InvoiceReceipt)
    if receipt is not None:
        await _require_matter_visible(conn, business, matter_id)
        return await _load_invoice(conn, business, matter_id, receipt.matter_invoice_id)

    _check_ready()
    await require_module(conn, business, PROJECTS_MODULE)
    matter_loc, _kind, _status, access_mode = await _require_matter_visible(
        conn, business, matter_id, for_update=True
    )
    await _require_billing_role_if_restricted(conn, business, matter_id, access_mode, user_id)

    m_row = await (
        await conn.execute(
            "select client_counterparty_id, currency, code from gba.project_matters "
            "where tenant_id = %s and id = %s",
            (business, matter_id),
        )
    ).fetchone()
    if m_row is None:
        raise NotFoundError("Project matter not found")
    counterparty_id, currency, matter_code = UUID(str(m_row[0])), str(m_row[1]), str(m_row[2])

    cp_rev_row = await (
        await conn.execute(
            "select max(revision) from gba.counterparty_versions "
            "where tenant_id = %s and counterparty_id = %s",
            (business, counterparty_id),
        )
    ).fetchone()
    if cp_rev_row is None or cp_rev_row[0] is None:
        raise InvalidReferenceError("Counterparty not found", field="client_counterparty_id")
    cp_rev = int(cp_rev_row[0])

    minor_row = await (
        await conn.execute("select minor_units from gba.currencies where code = %s", (currency,))
    ).fetchone()
    if minor_row is None:
        raise InvalidReferenceError("Unknown currency", field="currency")
    places = int(minor_row[0])

    billed_items: list[tuple[InvoiceItemKind, UUID | None, UUID | None, UUID | None, str, int]] = []
    time_rows_for_rev: list[tuple[object, ...]] = []

    for te_id in body.time_entry_ids:
        te = await (
            await conn.execute(
                "select stage_id, task_id, staff_user_id, work_date, duration_minutes, "
                "hourly_rate_minor, currency, billable, amount_minor, description, status, "
                "decided_by, decided_at, revision "
                "from gba.project_time_entries "
                "where tenant_id = %s and matter_id = %s and id = %s for update",
                (business, matter_id, te_id),
            )
        ).fetchone()
        if te is None:
            raise InvalidReferenceError(
                "Unknown time entry for this matter", field="time_entry_ids"
            )
        if str(te[10]) != "approved":
            raise ProjectsStateError("Only approved time entries can be billed")
        if not bool(te[7]) or int(te[8]) <= 0:
            raise ProjectsStateError("Non-billable or zero-amount time entries cannot be billed")
        desc = f"[{matter_code}] Time {te[3]} ({te[4]}m): {te[9]}"[:500]
        billed_items.append(("time_entry", te_id, None, None, desc, int(te[8])))
        time_rows_for_rev.append((te_id, *te))

    for st_id in body.stage_ids:
        st = await (
            await conn.execute(
                "select stage_no, title, fixed_fee_minor, status from gba.project_stages "
                "where tenant_id = %s and matter_id = %s and id = %s for update",
                (business, matter_id, st_id),
            )
        ).fetchone()
        if st is None:
            raise InvalidReferenceError("Unknown stage for this matter", field="stage_ids")
        if str(st[3]) != "accepted":
            raise ProjectsStateError("Only accepted stages can be billed")
        if st[2] is None or int(st[2]) <= 0:
            raise ProjectsStateError("Stage has no positive fixed fee to bill")
        desc = f"[{matter_code}] Stage {st[0]}: {st[1]}"[:500]
        billed_items.append(("stage_fee", None, st_id, None, desc, int(st[2])))

    for run_id in body.recurring_run_ids:
        rr = await (
            await conn.execute(
                "select period_start, period_end, fee_minor, billing_status "
                "from gba.project_recurring_runs "
                "where tenant_id = %s and matter_id = %s and id = %s for update",
                (business, matter_id, run_id),
            )
        ).fetchone()
        if rr is None:
            raise InvalidReferenceError(
                "Unknown recurring run for this matter", field="recurring_run_ids"
            )
        if str(rr[3]) != "unbilled":
            raise ProjectsStateError("Recurring run has already been billed")
        if int(rr[2]) <= 0:
            raise ProjectsStateError("Recurring run has zero fee")
        desc = f"[{matter_code}] Recurring period {rr[0]}..{rr[1]}"[:500]
        billed_items.append(("recurring_run", None, None, run_id, desc, int(rr[2])))

    total_minor = sum(item[5] for item in billed_items)
    invoice_doc_id = uuid7()
    fin_lines = tuple(
        InvoiceLineInput(
            line_id=uuid7(),
            counter_account_id=body.revenue_account_id,
            description=item[4][:200],
            amount=from_minor(item[5], places),
        )
        for item in billed_items
    )

    await financial_documents.save_draft(
        conn,
        business_id=business,
        book_id=body.book_id,
        document_id=invoice_doc_id,
        user_id=user_id,
        actor=actor,
        key=f"pro-fin-{key}"[:120],
        body=InvoiceDraftInput(
            expected_revision=0,
            direction="receivable",
            counterparty_id=counterparty_id,
            counterparty_revision=cp_rev,
            currency=currency,
            invoice_date=body.invoice_date,
            due_date=body.due_date,
            control_account_id=body.receivable_account_id,
            title=body.title,
            number=body.number or f"{matter_code}-{str(invoice_doc_id)[:8].upper()}"[:64],
            lines=fin_lines,
        ),
    )

    matter_invoice_id = uuid7()
    async with module_writes(PROJECTS_MODULE):
        await conn.execute(
            "insert into gba.project_matter_invoices "
            "(tenant_id, id, location_id, matter_id, book_id, invoice_document_id, "
            "counterparty_id, total_minor, currency, title, number, invoice_date, "
            "due_date, recorded_by) "
            "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                business,
                matter_invoice_id,
                matter_loc,
                matter_id,
                body.book_id,
                invoice_doc_id,
                counterparty_id,
                total_minor,
                currency,
                body.title,
                body.number,
                body.invoice_date,
                body.due_date,
                user_id,
            ),
        )
        try:
            for kind, item_te_id, item_st_id, item_rr_id, desc, amt in billed_items:
                await conn.execute(
                    "insert into gba.project_matter_invoice_items "
                    "(tenant_id, id, location_id, matter_id, matter_invoice_id, item_kind, "
                    "time_entry_id, stage_id, recurring_run_id, description, amount_minor, "
                    "currency) "
                    "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        business,
                        uuid7(),
                        matter_loc,
                        matter_id,
                        matter_invoice_id,
                        kind,
                        item_te_id,
                        item_st_id,
                        item_rr_id,
                        desc,
                        amt,
                        currency,
                    ),
                )
        except errors.UniqueViolation as exc:
            raise ProjectsStateError(
                "One or more selected time entries, stages, or recurring runs are already billed"
            ) from exc

        for te_row in time_rows_for_rev:
            billed_te_id = te_row[0]
            next_rev = int(str(te_row[14])) + 1
            await conn.execute(
                "update gba.project_time_entries "
                "set status = 'billed', revision = %s, recorded_by = %s, "
                "recorded_at = clock_timestamp() "
                "where tenant_id = %s and id = %s",
                (next_rev, user_id, business, billed_te_id),
            )
            await conn.execute(
                "insert into gba.project_time_entry_revisions "
                "(tenant_id, time_entry_id, revision, location_id, matter_id, stage_id, task_id, "
                "staff_user_id, work_date, duration_minutes, hourly_rate_minor, currency, "
                "billable, amount_minor, description, status, decided_by, decided_at, recorded_by) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'billed', "
                "%s, %s, %s)",
                (
                    business,
                    billed_te_id,
                    next_rev,
                    matter_loc,
                    matter_id,
                    te_row[1],
                    te_row[2],
                    te_row[3],
                    te_row[4],
                    te_row[5],
                    te_row[6],
                    te_row[7],
                    te_row[8],
                    te_row[9],
                    te_row[10],
                    te_row[12],
                    te_row[13],
                    user_id,
                ),
            )

        for run_id in body.recurring_run_ids:
            await conn.execute(
                "update gba.project_recurring_runs set billing_status = 'billed' "
                "where tenant_id = %s and id = %s",
                (business, run_id),
            )

    await commands.audit(
        conn,
        business,
        actor,
        "projects.invoice.created",
        "project_matter_invoice",
        str(matter_invoice_id),
        {
            "matter_id": str(matter_id),
            "invoice_document_id": str(invoice_doc_id),
            "total_minor": total_minor,
        },
    )
    await commands.complete(conn, scope, _InvoiceReceipt(matter_invoice_id=matter_invoice_id))
    return await _load_invoice(conn, business, matter_id, matter_invoice_id)


async def _build_matter_bundle(
    conn: RuntimeConnection, business: UUID, matter_id: UUID
) -> MatterExportBundle:
    matter = await get_matter(conn, business, matter_id)
    checks = (await list_conflict_checks(conn, business, matter_id)).items
    stages = (await list_stages(conn, business, matter_id)).items
    tasks = (await list_tasks(conn, business, matter_id, limit=100)).items
    files = (await list_matter_files(conn, business, matter_id)).items
    time_entries = (await list_time_entries(conn, business, matter_id, limit=100)).items
    schedules = (await list_recurring_schedules(conn, business, matter_id)).items
    runs = (await list_recurring_runs(conn, business, matter_id)).items
    invoices = (await list_matter_invoices(conn, business, matter_id)).items
    return MatterExportBundle(
        matter=matter,
        conflict_checks=checks,
        stages=stages,
        tasks=tasks,
        files=files,
        time_entries=time_entries,
        recurring_schedules=schedules,
        recurring_runs=runs,
        invoices=invoices,
    )


async def list_exports(conn: RuntimeConnection, business: UUID) -> ProjectExportList:
    async with conn.cursor(row_factory=class_row(ProjectExportRecord)) as cur:
        await cur.execute(
            "select id as export_id, location_id, scope, matter_id, requested_by, "
            "matter_count, stage_count, task_count, file_count, time_entry_count, "
            "recurring_run_count, invoice_count, recorded_at "
            "from gba.project_exports where tenant_id = %s order by recorded_at desc, id desc",
            (business,),
        )
        rows = await cur.fetchall()
    return ProjectExportList(items=rows)


async def _load_export_record(
    conn: RuntimeConnection, business: UUID, export_id: UUID
) -> ProjectExportRecord:
    async with conn.cursor(row_factory=class_row(ProjectExportRecord)) as cur:
        await cur.execute(
            "select id as export_id, location_id, scope, matter_id, requested_by, "
            "matter_count, stage_count, task_count, file_count, time_entry_count, "
            "recurring_run_count, invoice_count, recorded_at "
            "from gba.project_exports where tenant_id = %s and id = %s",
            (business, export_id),
        )
        found = await cur.fetchone()
    if found is None:
        raise NotFoundError("Export record not found")
    return found


async def export_matter(
    conn: RuntimeConnection,
    business: UUID,
    matter_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
) -> MatterExportPayload:
    scope = IdempotencyScope(business, actor, "projects.export.matter", key)
    fingerprint = commands.fingerprint({"matter_id": str(matter_id)})
    receipt = await commands.claim(conn, scope, fingerprint, _ExportReceipt)
    if receipt is not None:
        bundle = await _build_matter_bundle(conn, business, matter_id)
        rec = await _load_export_record(conn, business, receipt.export_id)
        return MatterExportPayload(export=rec, bundle=bundle)

    _check_ready()
    await require_module(conn, business, PROJECTS_MODULE)
    matter_loc, _kind, _status, _access = await _require_matter_visible(conn, business, matter_id)
    bundle = await _build_matter_bundle(conn, business, matter_id)

    export_id = uuid7()
    async with module_writes(PROJECTS_MODULE):
        await conn.execute(
            "insert into gba.project_exports "
            "(tenant_id, id, location_id, scope, matter_id, requested_by, matter_count, "
            "stage_count, task_count, file_count, time_entry_count, recurring_run_count, "
            "invoice_count) "
            "values (%s, %s, %s, 'matter', %s, %s, 1, %s, %s, %s, %s, %s, %s)",
            (
                business,
                export_id,
                matter_loc,
                matter_id,
                user_id,
                len(bundle.stages),
                len(bundle.tasks),
                len(bundle.files),
                len(bundle.time_entries),
                len(bundle.recurring_runs),
                len(bundle.invoices),
            ),
        )

    await commands.audit(
        conn,
        business,
        actor,
        "projects.export.matter",
        "project_export",
        str(export_id),
        {"matter_id": str(matter_id)},
    )
    await commands.complete(conn, scope, _ExportReceipt(export_id=export_id))
    rec = await _load_export_record(conn, business, export_id)
    return MatterExportPayload(export=rec, bundle=bundle)


async def export_portfolio(
    conn: RuntimeConnection,
    business: UUID,
    *,
    location_scope: UUID | None,
    user_id: UUID,
    actor: str,
    key: str,
    body: PortfolioExportInput,
) -> PortfolioExportPayload:
    if location_scope is not None and body.location_id != location_scope:
        raise PermissionDeniedError("You can only export matters in your assigned branch")
    scope = IdempotencyScope(business, actor, "projects.export.portfolio", key)
    fingerprint = commands.fingerprint({"location_id": str(body.location_id)})
    receipt = await commands.claim(conn, scope, fingerprint, _ExportReceipt)
    if receipt is not None:
        rec = await _load_export_record(conn, business, receipt.export_id)
        rows = await (
            await conn.execute(
                "select id from gba.project_matters "
                "where tenant_id = %s and location_id = %s order by id",
                (business, body.location_id),
            )
        ).fetchall()
        bundles = [await _build_matter_bundle(conn, business, UUID(str(r[0]))) for r in rows]
        return PortfolioExportPayload(export=rec, matters=bundles)

    _check_ready()
    await require_module(conn, business, PROJECTS_MODULE)
    loc_ok = await (
        await conn.execute(
            "select 1 from gba.locations where tenant_id = %s and id = %s",
            (business, body.location_id),
        )
    ).fetchone()
    if loc_ok is None:
        raise InvalidReferenceError("Unknown branch", field="location_id")

    # PostgreSQL 18 FORCE RLS automatically excludes any restricted matter not granted to actor
    rows = await (
        await conn.execute(
            "select id from gba.project_matters "
            "where tenant_id = %s and location_id = %s order by id",
            (business, body.location_id),
        )
    ).fetchall()
    bundles = [await _build_matter_bundle(conn, business, UUID(str(r[0]))) for r in rows]

    export_id = uuid7()
    async with module_writes(PROJECTS_MODULE):
        await conn.execute(
            "insert into gba.project_exports "
            "(tenant_id, id, location_id, scope, matter_id, requested_by, matter_count, "
            "stage_count, task_count, file_count, time_entry_count, recurring_run_count, "
            "invoice_count) "
            "values (%s, %s, %s, 'portfolio', null, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                business,
                export_id,
                body.location_id,
                user_id,
                len(bundles),
                sum(len(b.stages) for b in bundles),
                sum(len(b.tasks) for b in bundles),
                sum(len(b.files) for b in bundles),
                sum(len(b.time_entries) for b in bundles),
                sum(len(b.recurring_runs) for b in bundles),
                sum(len(b.invoices) for b in bundles),
            ),
        )

    await commands.audit(
        conn,
        business,
        actor,
        "projects.export.portfolio",
        "project_export",
        str(export_id),
        {"location_id": str(body.location_id), "matter_count": len(bundles)},
    )
    await commands.complete(conn, scope, _ExportReceipt(export_id=export_id))
    rec = await _load_export_record(conn, business, export_id)
    return PortfolioExportPayload(export=rec, matters=bundles)
