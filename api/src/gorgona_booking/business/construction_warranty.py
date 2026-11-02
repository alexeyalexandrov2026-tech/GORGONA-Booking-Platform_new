"""O6b (package O, BUILD-01): warranty claims, their repair cost and the reconciliation view.

docs/plan/PACKAGE_O6B_DESIGN_2026-11-02.md. A claim is the customer's report of a problem inside
the warranty period the final acceptance records; its state moves by insert-only events (open to
repaired or rejected, repaired to closed or back to open). Its repair cost is an O3b cost link
assigned to it, so each fact still counts once. The reconciliation view derives contract, cost,
billing, retainage and FIN-03 settlement figures and their differences; nothing of it is stored.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from psycopg.errors import CheckViolation, UniqueViolation
from pydantic import AfterValidator, BaseModel, Field, model_validator

from gorgona_booking.booking import idempotency
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.business import financial_documents, settlements
from gorgona_booking.business.construction import (
    ConstructionRevisionConflictError,
    Strict,
    has_contract,
    lock_project,
    request_fingerprint,
    require_construction,
)
from gorgona_booking.business.construction_acceptance import list_acceptances
from gorgona_booking.business.construction_billing import list_applications
from gorgona_booking.business.construction_budget import budget_lines, load_budget
from gorgona_booking.business.construction_contracts import ConstructionNoContractError
from gorgona_booking.business.construction_costs import ConstructionCostReversedError
from gorgona_booking.business.construction_progress import (
    ConstructionFutureDateError,
    SiteDate,
    check_contract,
    load_progress,
    not_blank,
    one_line,
    project_currency,
    site_today,
)
from gorgona_booking.business.ledger_contracts import to_minor
from gorgona_booking.business.module_gate import CONSTRUCTION_MODULE, module_writes
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, DomainError, InvalidReferenceError, NotFoundError

ClaimState = Literal["open", "repaired", "closed", "rejected"]
STATES: tuple[ClaimState, ...] = ("open", "repaired", "closed", "rejected")
MOVES = {("open", "repaired"), ("open", "rejected"), ("repaired", "closed"), ("repaired", "open")}
TAKES_COST = ("open", "repaired")
Title = Annotated[str, Field(min_length=1, max_length=120), AfterValidator(one_line)]
Text = Annotated[str, Field(min_length=1, max_length=4000), AfterValidator(not_blank)]
Label = Annotated[str, Field(min_length=1, max_length=64), AfterValidator(one_line)]
Place = Annotated[str, Field(min_length=1, max_length=200), AfterValidator(one_line)]
Note = Annotated[str, Field(min_length=1, max_length=1000), AfterValidator(not_blank)]


class ConstructionNoWarrantyError(ConflictError):
    code = "CONSTRUCTION_NO_WARRANTY"


class ConstructionOutsideWarrantyError(DomainError):
    code = "CONSTRUCTION_OUTSIDE_WARRANTY"


class ConstructionClaimTransitionError(ConflictError):
    code = "CONSTRUCTION_CLAIM_TRANSITION"


class ConstructionClaimClosedError(ConflictError):
    code = "CONSTRUCTION_CLAIM_CLOSED"


class ConstructionRepairAssignedError(ConflictError):
    code = "CONSTRUCTION_REPAIR_ASSIGNED"


class ClaimInput(Strict):
    schema_version: Literal[1]
    title: Title
    description: Text | None = None
    phase: Label | None = None
    location: Place | None = None
    reported_by: Place
    raised_on: SiteDate


class ClaimEventInput(Strict):
    schema_version: Literal[1]
    expected_sequence: int = Field(ge=0, le=10_000)
    state: ClaimState
    note: Note | None = None

    @model_validator(mode="after")
    def _note_when_needed(self) -> Self:
        if self.state in ("open", "rejected") and self.note is None:
            raise ValueError("rejecting or reopening a claim needs a note")
        return self


class RepairInput(Strict):
    schema_version: Literal[1]
    cost_link: int = Field(ge=1, le=1_000_000)


class ClaimEventView(BaseModel):
    sequence: int
    state: ClaimState
    note: str | None
    recorded_at: datetime


class RepairView(BaseModel):
    cost_link: int
    amount_minor: int
    reversed: bool
    recorded_at: datetime


class ClaimView(BaseModel):
    schema_version: Literal[1] = 1
    project_id: UUID
    number: int
    title: str
    description: str | None
    phase: str | None
    location: str | None
    reported_by: str
    raised_on: date
    state: ClaimState
    events: list[ClaimEventView]
    repairs: list[RepairView]
    repair_minor: int
    recorded_at: datetime


class ClaimSummary(BaseModel):
    number: int
    title: str
    phase: str | None
    raised_on: date
    state: ClaimState
    repair_minor: int


class ClaimList(BaseModel):
    schema_version: Literal[1] = 1
    project_id: UUID
    currency: str
    warranty_starts_on: date | None
    warranty_ends_on: date | None
    repair_minor: int
    items: list[ClaimSummary]


class ReconciliationView(BaseModel):
    schema_version: Literal[1] = 1
    project_id: UUID
    currency: str
    contract_minor: int
    completed_minor: int
    budget_minor: int
    committed_minor: int
    actual_minor: int
    warranty_repair_minor: int
    billed_minor: int
    retained_minor: int
    due_minor: int
    released_minor: int
    held_minor: int
    due_paid_minor: int
    due_credited_minor: int
    retainage_paid_minor: int
    retainage_credited_minor: int
    unissued_documents: int
    contract_minus_billed_minor: int
    completed_minus_billed_minor: int
    billed_minus_settled_minor: int
    retainage_settled_before_release_minor: int
    budget_minus_actual_minor: int
    contract_minus_actual_minor: int
    claims: dict[ClaimState, int]


# Claims -----------------------------------------------------------------------------

_CLAIM = (
    "select number, title, description, phase, location, reported_by, raised_on, created_at "
    "from gba.construction_warranty_claims where project_id = %s "
)
_REPAIRS = (
    "select w.claim, w.cost_link, l.amount_minor, (r.number is not null), w.created_at "
    "from gba.construction_warranty_repairs w join gba.construction_cost_links l "
    "on l.tenant_id = w.tenant_id and l.project_id = w.project_id and l.number = w.cost_link "
    "left join gba.construction_cost_reversals r on r.tenant_id = l.tenant_id "
    "and r.project_id = l.project_id and r.number = l.number where w.project_id = %s "
)


def _repair_minor(repairs: list[RepairView]) -> int:
    return sum(r.amount_minor for r in repairs if not r.reversed)


async def _events(
    conn: RuntimeConnection, project_id: UUID, number: int | None = None
) -> dict[int, list[ClaimEventView]]:
    rows = await (
        await conn.execute(
            "select claim, sequence, state, note, created_at "
            "from gba.construction_warranty_claim_events where project_id = %s "
            "and (%s::integer is null or claim = %s) order by claim, sequence",
            (project_id, number, number),
        )
    ).fetchall()
    found: dict[int, list[ClaimEventView]] = {}
    for row in rows:
        found.setdefault(row[0], []).append(
            ClaimEventView(sequence=row[1], state=row[2], note=row[3], recorded_at=row[4])
        )
    return found


async def _repairs(
    conn: RuntimeConnection, project_id: UUID, number: int | None = None
) -> dict[int, list[RepairView]]:
    rows = await (
        await conn.execute(
            _REPAIRS + "and (%s::integer is null or w.claim = %s) "
            "order by w.claim, w.created_at, w.cost_link",
            (project_id, number, number),
        )
    ).fetchall()
    found: dict[int, list[RepairView]] = {}
    for row in rows:
        found.setdefault(row[0], []).append(
            RepairView(cost_link=row[1], amount_minor=row[2], reversed=row[3], recorded_at=row[4])
        )
    return found


def _state(events: list[ClaimEventView]) -> ClaimState:
    return events[-1].state if events else "open"


async def load_claim(conn: RuntimeConnection, project_id: UUID, number: int) -> ClaimView | None:
    """One claim with its events and repairs, or None (decision 2)."""
    await check_contract(conn, project_id)
    row = await (await conn.execute(_CLAIM + "and number = %s", (project_id, number))).fetchone()
    if row is None:
        return None
    events = (await _events(conn, project_id, number)).get(number, [])
    repairs = (await _repairs(conn, project_id, number)).get(number, [])
    return ClaimView(
        project_id=project_id,
        number=row[0],
        title=row[1],
        description=row[2],
        phase=row[3],
        location=row[4],
        reported_by=row[5],
        raised_on=row[6],
        state=_state(events),
        events=events,
        repairs=repairs,
        repair_minor=_repair_minor(repairs),
        recorded_at=row[7],
    )


async def _warranty(conn: RuntimeConnection, project_id: UUID) -> tuple[date, date] | None:
    """The warranty period of the final acceptance, or None before it."""
    row = await (
        await conn.execute(
            "select accepted_on, warranty_ends_on from gba.construction_acceptances "
            "where project_id = %s and scope = 'final'",
            (project_id,),
        )
    ).fetchone()
    return (row[0], row[1]) if row is not None else None


async def list_claims(conn: RuntimeConnection, project_id: UUID) -> ClaimList:
    """Every claim with its state and repair cost, and the warranty period (decision 2)."""
    await check_contract(conn, project_id)
    currency = await project_currency(conn, project_id)
    rows = await (await conn.execute(_CLAIM + "order by number", (project_id,))).fetchall()
    events = await _events(conn, project_id)
    repairs = await _repairs(conn, project_id)
    items = [
        ClaimSummary(
            number=row[0],
            title=row[1],
            phase=row[3],
            raised_on=row[6],
            state=_state(events.get(row[0], [])),
            repair_minor=_repair_minor(repairs.get(row[0], [])),
        )
        for row in rows
    ]
    period = await _warranty(conn, project_id)
    return ClaimList(
        project_id=project_id,
        currency=currency,
        warranty_starts_on=period[0] if period else None,
        warranty_ends_on=period[1] if period else None,
        repair_minor=sum(item.repair_minor for item in items),
        items=items,
    )


async def _stored(conn: RuntimeConnection, project_id: UUID, body: dict[str, object]) -> ClaimView:
    number = body.get("number")
    view = await load_claim(conn, project_id, number) if isinstance(number, int) else None
    if view is None:
        raise NotFoundError("Claim not found", project_id=str(project_id))
    return view


def _refused(exc: CheckViolation) -> Exception | None:
    """The database's answer to a write it refused, as the error the client sees."""
    name = exc.diag.constraint_name
    if name in (
        "construction_warranty_claims_sequence_check",
        "construction_warranty_claim_events_sequence_check",
    ):
        return ConstructionRevisionConflictError("The claims changed meanwhile; try again")
    if name == "construction_warranty_claims_date_check":
        return ConstructionFutureDateError("The date is after today on the site")
    if name == "construction_warranty_claims_warranty_check":
        return ConstructionOutsideWarrantyError("A claim is raised inside the warranty period")
    if name == "construction_warranty_claims_phase_check":
        return InvalidReferenceError("A claim names a phase of the budget", field="phase")
    if name == "construction_warranty_claim_events_transition_check":
        return ConstructionClaimTransitionError("The claim cannot move this way")
    if name == "construction_warranty_repairs_link_check":
        return ConstructionCostReversedError("The cost link no longer counts")
    if name == "construction_warranty_repairs_claim_check":
        return ConstructionClaimClosedError("A closed or rejected claim takes no new cost")
    return None


async def _begin(
    conn: RuntimeConnection,
    business: UUID,
    actor: str,
    kind: str,
    key: str,
    subject: str,
    body: BaseModel,
    project_id: UUID,
) -> tuple[IdempotencyScope, ClaimView | None]:
    """Claim the idempotency key; a replay answers with the claim it wrote."""
    await require_construction(conn, business)
    scope = IdempotencyScope(business, actor, kind, key)
    fingerprint = request_fingerprint(subject, body)
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is None:
        return scope, None
    if stored.request_hash != fingerprint:
        raise IdempotencyKeyReusedError("Key was used for another request")
    return scope, await _stored(conn, project_id, stored.body)


async def _write(conn: RuntimeConnection, statement: str, values: tuple[Any, ...]) -> None:
    try:
        async with module_writes(CONSTRUCTION_MODULE), conn.transaction():
            await conn.execute(statement, values)
    except CheckViolation as exc:
        mapped = _refused(exc)
        if mapped is None:
            raise
        raise mapped from exc


async def record_claim(
    conn: RuntimeConnection,
    business: UUID,
    project_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: ClaimInput,
) -> ClaimView:
    """Record the next warranty claim, open (decision 2)."""
    scope, replayed = await _begin(
        conn, business, actor, "construction.warranty_claim", key, str(project_id), body, project_id
    )
    if replayed is not None:
        return replayed
    await lock_project(conn, project_id)
    if not await has_contract(conn, project_id):
        raise ConstructionNoContractError("A warranty claim needs a contract")
    period = await _warranty(conn, project_id)
    if period is None:
        raise ConstructionNoWarrantyError("A warranty claim needs the final acceptance")
    if body.raised_on > await site_today(conn, project_id):
        raise ConstructionFutureDateError("The date is after today on the site")
    if not period[0] <= body.raised_on <= period[1]:
        raise ConstructionOutsideWarrantyError(
            "A claim is raised inside the warranty period",
            warranty_starts_on=period[0].isoformat(),
            warranty_ends_on=period[1].isoformat(),
        )
    phases = {str(line["phase"]) for line in await budget_lines(conn, project_id)}
    if body.phase is not None and body.phase not in phases:
        raise InvalidReferenceError("A claim names a phase of the budget", field="phase")
    latest = await (
        await conn.execute(
            "select coalesce(max(number), 0) from gba.construction_warranty_claims "
            "where project_id = %s",
            (project_id,),
        )
    ).fetchone()
    number = int(latest[0] if latest else 0) + 1
    await _write(
        conn,
        "insert into gba.construction_warranty_claims (tenant_id, project_id, number, title, "
        "description, phase, location, reported_by, raised_on, created_by) "
        "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            business,
            project_id,
            number,
            body.title,
            body.description,
            body.phase,
            body.location,
            body.reported_by,
            body.raised_on,
            user_id,
        ),
    )
    view = await load_claim(conn, project_id, number)
    assert view is not None  # noqa: S101 - saved above
    await idempotency.complete(conn, scope, 200, {"number": number})
    return view


async def _current(conn: RuntimeConnection, project_id: UUID, number: int) -> ClaimView:
    await lock_project(conn, project_id)
    view = await load_claim(conn, project_id, number)
    if view is None:
        raise NotFoundError("Claim not found", project_id=str(project_id), number=number)
    return view


async def move_claim(
    conn: RuntimeConnection,
    business: UUID,
    project_id: UUID,
    number: int,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: ClaimEventInput,
) -> ClaimView:
    """The next move of a claim, on the events the client saw (decision 3)."""
    scope, replayed = await _begin(
        conn,
        business,
        actor,
        "construction.warranty_event",
        key,
        f"{project_id}:{number}",
        body,
        project_id,
    )
    if replayed is not None:
        return replayed
    current = await _current(conn, project_id, number)
    if body.expected_sequence != len(current.events):
        raise ConstructionRevisionConflictError(
            "The claim moved meanwhile", sequence=len(current.events)
        )
    if (current.state, body.state) not in MOVES:
        raise ConstructionClaimTransitionError(
            "The claim cannot move this way", state=current.state, to=body.state
        )
    sequence = len(current.events) + 1
    await _write(
        conn,
        "insert into gba.construction_warranty_claim_events (tenant_id, project_id, claim, "
        "sequence, state, note, created_by) values (%s, %s, %s, %s, %s, %s, %s)",
        (business, project_id, number, sequence, body.state, body.note, user_id),
    )
    view = await load_claim(conn, project_id, number)
    assert view is not None  # noqa: S101 - read above
    await idempotency.complete(conn, scope, 200, {"number": number})
    return view


async def record_repair(
    conn: RuntimeConnection,
    business: UUID,
    project_id: UUID,
    number: int,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: RepairInput,
) -> ClaimView:
    """Assign a cost link of the project to a claim as its repair cost (decision 4)."""
    scope, replayed = await _begin(
        conn,
        business,
        actor,
        "construction.warranty_repair",
        key,
        f"{project_id}:{number}",
        body,
        project_id,
    )
    if replayed is not None:
        return replayed
    current = await _current(conn, project_id, number)
    link = await (
        await conn.execute(
            "select (r.number is not null), w.claim from gba.construction_cost_links l "
            "left join gba.construction_cost_reversals r on r.tenant_id = l.tenant_id "
            "and r.project_id = l.project_id and r.number = l.number "
            "left join gba.construction_warranty_repairs w on w.tenant_id = l.tenant_id "
            "and w.project_id = l.project_id and w.cost_link = l.number "
            "where l.project_id = %s and l.number = %s",
            (project_id, body.cost_link),
        )
    ).fetchone()
    if link is None:
        raise NotFoundError(
            "Cost link not found", project_id=str(project_id), number=body.cost_link
        )
    if link[1] is not None:
        raise ConstructionRepairAssignedError("This cost is already a repair", claim=link[1])
    if link[0]:
        raise ConstructionCostReversedError("The cost link no longer counts", number=body.cost_link)
    if current.state not in TAKES_COST:
        raise ConstructionClaimClosedError(
            "A closed or rejected claim takes no new cost", state=current.state
        )
    try:
        await _write(
            conn,
            "insert into gba.construction_warranty_repairs (tenant_id, project_id, cost_link, "
            "claim, created_by) values (%s, %s, %s, %s, %s)",
            (business, project_id, body.cost_link, number, user_id),
        )
    except UniqueViolation as exc:
        raise ConstructionRepairAssignedError("This cost is already a repair") from exc
    view = await load_claim(conn, project_id, number)
    assert view is not None  # noqa: S101 - read above
    await idempotency.complete(conn, scope, 200, {"number": number})
    return view


# Reconciliation ---------------------------------------------------------------------


@dataclass(frozen=True)
class Totals:
    """The figures the differences are taken from, in minor units of the project's currency."""

    contract_minor: int
    completed_minor: int
    budget_minor: int
    actual_minor: int
    billed_minor: int
    retained_minor: int
    released_minor: int
    due_settled_minor: int
    retainage_settled_minor: int


def differences(t: Totals) -> dict[str, int]:
    """Decision 5: what is still open between the figures; retainage settled early never below 0."""
    return {
        "contract_minus_billed_minor": t.contract_minor - t.billed_minor,
        "completed_minus_billed_minor": t.completed_minor - t.billed_minor,
        "billed_minus_settled_minor": (
            t.billed_minor - t.due_settled_minor - t.retainage_settled_minor
        ),
        "held_minor": t.retained_minor - t.released_minor,
        "retainage_settled_before_release_minor": max(
            t.retainage_settled_minor - t.released_minor, 0
        ),
        "budget_minus_actual_minor": t.budget_minor - t.actual_minor,
        "contract_minus_actual_minor": t.contract_minor - t.actual_minor,
    }


def _minor(amount: str, scale: int) -> int:
    """A balance figure in minor units; zero is a balance too (to_minor accepts only amounts)."""
    return 0 if Decimal(amount) == 0 else to_minor(amount, scale)


@dataclass
class _Settled:
    paid: int = 0
    credited: int = 0
    unissued: int = 0


async def _settle(
    conn: RuntimeConnection,
    business: UUID,
    book: UUID,
    document: UUID | None,
    kind: Literal["invoice", "manual_accrual"],
    into: _Settled,
) -> None:
    """Add what is paid and credited on a pay-application document's FIN-03 obligation."""
    if document is None:
        return
    view = await financial_documents.load_invoice(conn, business, book, document, kind=kind)
    if view is None:
        raise NotFoundError("Financial document not found", document_id=str(document))
    if view.obligation_id is None:
        into.unissued += 1
        return
    owed = await settlements.load_obligation(conn, business, book, view.obligation_id)
    if owed is None:
        raise NotFoundError("Obligation not found", obligation_id=str(view.obligation_id))
    into.paid += _minor(owed.paid, owed.minor_units)
    into.credited += _minor(owed.credited, owed.minor_units)


async def load_reconciliation(
    conn: RuntimeConnection, business: UUID, project_id: UUID
) -> ReconciliationView:
    """The project's figures and their differences, all derived (decision 5)."""
    await check_contract(conn, project_id)
    currency = await project_currency(conn, project_id)
    progress = await load_progress(conn, project_id)
    budget = await load_budget(conn, project_id)
    billing = await list_applications(conn, business, project_id)
    acceptances = await list_acceptances(conn, project_id)
    claims = await list_claims(conn, project_id)
    documents = await (
        await conn.execute(
            "select book_id, invoice_document_id, retainage_document_id "
            "from gba.construction_pay_applications where project_id = %s order by number",
            (project_id,),
        )
    ).fetchall()
    due, held = _Settled(), _Settled()
    for book, invoice, retainage in documents:
        await _settle(conn, business, book, invoice, "invoice", due)
        await _settle(conn, business, book, retainage, "manual_accrual", held)
    found = differences(
        Totals(
            contract_minor=billing.contract_minor,
            completed_minor=progress.completed_minor,
            budget_minor=budget.budget_minor,
            actual_minor=budget.actual_minor,
            billed_minor=billing.billed_to_date_minor,
            retained_minor=billing.retained_minor,
            released_minor=acceptances.released_minor,
            due_settled_minor=due.paid + due.credited,
            retainage_settled_minor=held.paid + held.credited,
        )
    )
    counts: dict[ClaimState, int] = dict.fromkeys(STATES, 0)
    for item in claims.items:
        counts[item.state] += 1
    return ReconciliationView(
        project_id=project_id,
        currency=currency,
        contract_minor=billing.contract_minor,
        completed_minor=progress.completed_minor,
        budget_minor=budget.budget_minor,
        committed_minor=budget.committed_minor,
        actual_minor=budget.actual_minor,
        warranty_repair_minor=claims.repair_minor,
        billed_minor=billing.billed_to_date_minor,
        retained_minor=billing.retained_minor,
        due_minor=billing.due_minor,
        released_minor=acceptances.released_minor,
        due_paid_minor=due.paid,
        due_credited_minor=due.credited,
        retainage_paid_minor=held.paid,
        retainage_credited_minor=held.credited,
        unissued_documents=due.unissued + held.unissued,
        claims=counts,
        **found,
    )
