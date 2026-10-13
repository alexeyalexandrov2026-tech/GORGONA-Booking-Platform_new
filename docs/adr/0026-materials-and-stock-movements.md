# ADR-0026 — Basic materials: owner-linked stock documents, moving-average cost and ledger postings

- Status: **Proposed (2026-10-13)**. Slice J1 is implemented locally (see the
  implementation notes below); nothing else is. The owner chose the twelve options
  of the [package J plan](../plan/PACKAGE_J_PLAN_2026-10-13.md) on 2026-10-13; this text
  follows them. It becomes Accepted only with the technical acceptance of STOCK-01.
- Scope: package J of the owner-approved stage 2; criterion STOCK-01 ("receipt,
  write-off and return of a material are linked to a document and an owner; a repeated
  command does not repeat the movement").
- Base: `fedd0f1` on `main`. Builds on ADR-0004 (idempotency), ADR-0014 (location
  scope), ADR-0015 (legal entities), ADR-0019 (module gates), ADR-0023 (ledger) and
  ADR-0024 (managed journal entries of a package).
- Decision owner: the product owner.

## Context

- The registry has a module `inventory` ("Inventory and customer warehouses"). It is
  `planned` and depends on `products_services`, which is also `planned`, so no
  configuration can enable it today.
- No table holds materials, storage places or stock. The booking catalog (migration
  0002) holds services, variants and add-ons; it is not a list of materials.
- ADR-0023 states that later packages, materials J among them, "post through this
  ledger instead of keeping their own money records". The owner chose that path: stock
  documents carry amounts and post journal entries.
- The ledger posts under `gba.lock_ledger(tenant)` in READ COMMITTED; a trigger refuses
  a closed period, a date before the book's accounting start and an archived account;
  `(book, source kind, source id)` is unique; lines are positive and balanced per entry.
- Ledger tables carry a restrictive policy `gba.current_location_id() is null` for the
  runtime role, and no migration defines a function that runs with its owner's rights.
  A branch-limited member therefore cannot create a journal entry.
- Package H ties each of its entries to its document in the same transaction and
  refuses the generic ledger reversal of such an entry (migration 0021).
- A payable invoice line of package H may debit only an expense or an asset account.
- Platform rules that apply unchanged: forced row-level security, insert-only history,
  the database as the final arbiter, idempotent audited commands, and races counted only
  with an observed wait in `pg_locks`.

## Proposed decision

1. **Module.** Package J implements `inventory` as basic materials. It depends on
   `finance`; its readiness follows the STOCK-01 scenario; the registry version becomes
   3. A published configuration is not altered (ADR-0019). Writes are gated by
   `gba.require_enabled_module('inventory')`; reads and the resolution of an uncertain
   command are not gated.
2. **Materials and storage places.** A material has a code, a name, a unit label typed
   by the business and a quantity scale of 0 to 3 decimal places. A storage place
   belongs to one location and has a code and a name. Both keep insert-only versions
   and an archive flag. The unit, the scale and the place's location never change. An
   archived material or place refuses inbound movements and still allows outbound ones.
3. **Quantities and money.** A quantity is a positive `bigint` count of the smallest
   fraction of the material's unit. An amount is a non-negative `bigint` of minor units
   of the base currency of the owner's book, sent as a decimal string by the currency
   scale. No floating point, no silent rounding of input, no currency conversion.
4. **Documents.** Four kinds: `receipt`, `write_off`, `return`, `transfer`. A document
   is posted by one command with all its lines (at most 100) and is immutable from
   then on; there is no server draft. It names the owner legal entity, the storage
   place (two for a transfer), a reason from a closed list, a document date, an
   optional supplier (a counterparty with the `supplier` role) and an optional supplier
   document number. A receipt line carries its amount.
5. **Movements and balances.** Each line produces one movement (two for a transfer)
   with document, line, material, place, owner, direction and quantity. A unique key on
   document, line and direction refuses a second movement in the database. A trigger
   refuses a movement whose document, line, material, place or owner do not match. A
   row per material, place and owner holds the running balance with
   `check (quantity >= 0)`; only the movement trigger changes it, under that row's
   lock. Movements are the source of truth.
6. **Cost.** Moving average per material and owner legal entity: one row holds the
   total quantity `Q` and the total value `V`. A receipt adds its quantity and amount.
   An outbound quantity `q` leaves at `round(V * q / Q)` in minor units, and at exactly
   `V` when `q = Q`. `V` is never negative and is zero when `Q` is zero. Cost follows
   the order of posting; a backdated document does not revalue earlier write-offs. A
   transfer changes neither `Q` nor `V`.
7. **Posting rules.** A versioned set of seven accounts per book, set by a member with
   `finance.manage`: inventory, receipt clearing, opening balances, surplus, material
   consumption, losses, price difference. The inventory account is an asset account;
   the receipt clearing account is an asset or expense account, so that a supplier's
   bill in package H can use the same account; no archived account; the other six
   differ from the inventory account. The inventory account does not change after the
   first posted document. A document stores the rule version it was posted with.
8. **Journal entries.** A document with a non-zero total posts one entry in the owner's
   book with a new source kind `stock`, the document identifier as source identifier
   and the document date as entry date. Lines are aggregated by account. A zero total
   posts no entry. A trigger ties a `stock` entry to its document of the same
   transaction, book, date and author, and the generic ledger reversal of a `stock`
   entry is refused; a stock document is the only correction.

   | Document | Debit | Credit |
   |---|---|---|
   | Receipt, purchase | Inventory | Receipt clearing |
   | Receipt, opening balance | Inventory | Opening balances |
   | Receipt, surplus | Inventory | Surplus |
   | Write-off, used | Material consumption | Inventory, at average cost |
   | Write-off, damaged, lost, expired or other | Losses | Inventory, at average cost |
   | Return against a receipt line | The account the receipt credited, at the share of the line amount | Inventory, at average cost; the difference goes to price difference |
   | Return against a write-off line | Inventory | The account the write-off debited, at the share of the line cost |
   | Transfer | none | none |

9. **Returns.** A return names lines of an earlier receipt or write-off of the same
   material and owner and moves the opposite way. The total returned against a line
   never exceeds its quantity; the check runs in the database under a lock on the
   source line. A return against a receipt is also bounded by the current balance. The
   share of a line amount is proportional to the quantity, and the return that
   completes the line takes the remainder, so a fully returned line returns its whole
   amount. An entry error is corrected by a return with the reason "entry error".
10. **Transfers.** One document, two movements per line in one transaction, the same
    owner on both sides, no amount and no entry. A transfer between locations needs a
    company-wide owner or manager.
11. **Dates and periods.** The document date is not in the future by the place's local
    date, not in a closed period and not before the accounting start of the book. The
    package never reopens a period.
12. **Locks.** A money document takes `gba.lock_ledger(tenant)` first, then the source
    lines of a return in identifier order, then balance rows in the order material,
    place, owner. A transfer takes only balance rows, in the same order.
13. **Commands.** Posting and every reference-data change use the shared receipts of
    `business/commands.py` with an Idempotency-Key, and an expected revision where a
    version exists. The same key with the same body replays the stored result; with
    another body it is refused. Document, lines, movements, balances, cost, journal
    entry, audit event and receipt are written in one transaction.
14. **Permissions and scope.** Permissions map version 7 adds `inventory.read` and
    `inventory.manage` for owner and manager. Receipts, write-offs and returns are
    posted by a company-wide member who also holds `finance.manage`. A branch manager
    reads quantities and documents of their location, manages its storage places and
    posts transfers inside it. Amounts and cost live in tables with the same
    company-only restrictive policy as the ledger and are returned only to a member
    with `finance.read`. The permissions are not delegable and are not given to
    platform support. Audit events hold identifiers, the document kind and the line
    count, without names, amounts or notes.
15. **Reconciliation.** For each book, the sum of `V` over the materials of its legal
    entity equals the net of the lines of `stock` entries on its inventory account; for
    each material and owner, the place balances sum to `Q` and equal the sum of
    movements. Tests assert both after every scenario.
16. **API and UI.** Routes under `/v1/businesses/{id}/inventory/...` for materials,
    places, posting rules, documents and balances. Two workspace sections, "Materials"
    and "Stock documents", on desktop and mobile, with recovery after a lost answer.

## Bounded change to existing code

- `business/modules.py`: dependency, readiness source, limits and stops of `inventory`;
  registry version 3.
- `auth/permissions.py`: two permissions; version 7.
- `business/module_gate.py`: the module constant.
- New migrations from 0036; migrations 0001–0035 stay unchanged. One of them replaces
  the check constraint of journal source kinds to add `stock` and adds the origin and
  reversal guards, the way package H did, with the matching packaged approvals of the
  ledger schema guard.
- A packaged schema check for the new tables, and their policies in the restoration
  step of `tests/integration/test_location_access.py`.
- `web/components/management-layout.tsx`: two sections.
- No change to booking, occupancy, counterparties, documents or workforce, and no
  change to how the ledger balances, closes periods or reports.

## Alternatives considered

- **Quantities only.** The executor's first recommendation; rejected by the owner. It
  would have left stock value outside the ledger until a later package.
- **FIFO cost layers.** More exact per delivery and more rules for returns; rejected by
  the owner in favour of the moving average.
- **Branch managers posting money documents.** It needs a function that writes ledger
  rows with rights the caller does not have. The project has none, and adding the first
  one is a security decision of its own. Rejected by the owner for this package.
- **Materials without Finance (two modes).** Two behaviours to build and test and a
  revaluation step when a business moves between them. Rejected by the owner.
- **A receipt that creates the supplier's payable.** It ties stock to invoices and
  obligations and makes the supplier mandatory. Rejected by the owner; the receipt
  credits a clearing account that the supplier's bill then debits.
- **Counterparty-owned stock.** That is customer warehouses and 3PL of stage 6.
- **A minimal `products_services` module first.** Two modules to accept instead of one,
  and a material is not necessarily a product for sale.
- **Balance computed from movements under an advisory lock, without a balance row.**
  Direct SQL would bypass the lock and the non-negative rule.
- **Amounts in the same rows as quantities, hidden by the API.** A branch-limited
  session could still read them with SQL; separate company-only tables make the
  database the arbiter.
- **Editable or deletable documents, server drafts, negative balances.** They break the
  history rule or remove the invariant that makes two competing write-offs decidable.

## Implementation notes — slice J1 (2026-10-13)

Slice J1 is commit `39fc819` on the local branch `codex/package-j1-materials`: migration
0036, the packaged schema check, contracts, service and API for materials and storage
places, permissions map version 7 and module registry version 3. It holds no money, no
documents and no movements. Record:
[validation](../plan/evidence/2026-10-13-j1-materials/VALIDATION.md).

Choices made while implementing; none of them changes an owner decision:

1. A storage place code is unique inside its branch, not across the company. A material
   code is unique across the company.
2. The unit label and the quantity scale are columns of the immutable head row of a
   material, next to its code; only the name and the archive flag are versioned.
3. The database itself checks the author of every version, as migration 0035 does for
   workforce: an active owner or manager who is the authenticated user, company-wide
   for a material and covering the branch for a storage place. A violation is SQLSTATE
   `42501`.
4. A version that is not the next one is refused with SQLSTATE `GBS01`, which the
   service maps to 409 `INVENTORY_CONFLICT`.
5. A client that lost the answer to a command reads the record by the identifier it
   chose itself; reads stay open when the module is disabled.

Not implemented yet from decision 2: an archived material or place refuses nothing,
because no movements exist before slice J2.

## Acceptance and status

The matrix J-01–J-14 is in the plan. The module stays closed by the readiness lock until
the acceptance commit; tests enable it only by substituting readiness in fixtures, with
a separate refusal test. This ADR becomes Accepted only together with the technical
acceptance of STOCK-01, by the owner's decision.

## Limits

The posting table is a program mapping after an explicit human choice of accounts, not
accounting or tax advice for a jurisdiction. No FIFO, batches, serial numbers or expiry
dates; no currency conversion and no backdated revaluation; no taxes; no purchase orders
and no automatic payable; no posting of money documents by branch managers; no materials
without Finance; no customer-owned goods; no stock count document, reservations or
automatic consumption by a service; no unit conversion, barcodes, import, export, file
attachments or low-stock notifications; no sale of materials; no transfer between legal
entities; no group reporting. Manual journal entries on the inventory account are not
forbidden and are outside the reconciliation. Deployment and production migrations are
not authorized by this ADR.
