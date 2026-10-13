# ADR-0026 — Basic materials: owner-linked stock documents and movements

- Status: **Proposed (2026-10-13)**. No code exists. The text uses the recommended
  options of the [package J plan](../plan/PACKAGE_J_PLAN_2026-10-13.md) as working
  defaults; the owner has not chosen yet, and this ADR changes if a choice differs.
- Scope: package J of the owner-approved stage 2; criterion STOCK-01 ("receipt,
  write-off and return of a material are linked to a document and an owner; a repeated
  command does not repeat the movement").
- Base: `fedd0f1` on `main`. Builds on ADR-0004 (idempotency), ADR-0014 (location
  scope), ADR-0015 (legal entities) and ADR-0019 (module gates).
- Decision owner: the product owner. The eight open choices are listed in the plan.

## Context

- The registry has a module `inventory` ("Inventory and customer warehouses"). It is
  `planned` and depends on `products_services`, which is also `planned`, so no
  configuration can enable it today.
- No table holds materials, storage places or stock. The booking catalog (migration
  0002) holds services, variants and add-ons; it is not a list of materials.
- Legal entities belong to the business and are never invented by the platform
  (ADR-0015). A ledger book already requires one.
- The stage 2 plan says packages H, J and K "create money and material effects that
  must land in the entries of G". STOCK-01 itself names no money.
- Platform rules that apply unchanged: forced row-level security by business and
  restrictive location policies, insert-only history, the database as the final
  arbiter, idempotent audited commands, and races counted only with an observed wait
  in `pg_locks`.

## Proposed decision

1. **Module.** Package J implements `inventory` as basic materials only. Its dependency
   becomes `organization`; its readiness follows the STOCK-01 scenario; the registry
   version becomes 3. A published configuration is not altered (ADR-0019). Writes are
   gated by `gba.require_enabled_module('inventory')`; reads and the resolution of an
   uncertain command are not gated.
2. **Materials and storage places.** A material has a code, a name, a unit label typed
   by the business and a quantity scale of 0 to 3 decimal places. A storage place
   belongs to one location and has a code and a name. Both keep insert-only versions
   and an archive flag. The unit, the scale and the place's location never change. An
   archived material or place refuses inbound movements and still allows outbound ones.
3. **Quantities.** A quantity is a positive `bigint` count of the smallest fraction of
   the material's unit, by the material's scale. No floating point and no rounding: a
   value with more decimal places than the scale is refused. Units are not converted.
4. **Documents.** Four kinds: `receipt`, `write_off`, `return`, `transfer`. A document
   is posted by one command with all its lines (at most 100) and is immutable from
   then on; there is no server draft. It names the owner legal entity, the storage
   place (two for a transfer), a reason from a closed list, a document date that is not
   in the future by the place's local date, an optional supplier (a counterparty with
   the `supplier` role) and an optional supplier document number.
5. **Movements and balances.** Each line produces one movement (two for a transfer)
   with document, line, material, place, owner, direction and quantity. A unique key on
   document, line and direction refuses a second movement in the database. Movements
   are inserted only through posting; a trigger refuses a movement whose document, line,
   material, place or owner do not match. A row per material, place and owner holds the
   running balance with `check (quantity >= 0)`; only the movement trigger changes it,
   under that row's lock. Movements are the source of truth; the balance row carries the
   lock and the non-negative rule, and a test reconciles it with the sum of movements.
   Balances follow the order of posting, not the document date.
6. **Returns.** A return names lines of an earlier receipt or write-off of the same
   material and owner and moves the opposite way. The total returned against a line
   never exceeds its quantity; the check runs in the database under a lock on the source
   line. A return to the supplier is also bounded by the current balance. An entry
   error is corrected by a return with the reason "entry error".
7. **Transfers.** One document, two movements per line in one transaction, the same
   owner on both sides. A transfer between locations needs a company-wide owner or
   manager. Ownership is never transferred between legal entities in this package.
8. **Locks.** Balance rows are locked in the order material, place, owner; source lines
   of a return before balance rows, in identifier order. Opposite transfers do not
   deadlock.
9. **Commands.** Posting and every reference-data change use the shared receipts of
   `business/commands.py` with an Idempotency-Key, and an expected revision where a
   version exists. The same key with the same body replays the stored result; with
   another body it is refused. Document, lines, movements, balances, audit event and
   receipt are written in one transaction.
10. **Permissions and scope.** Permissions map version 7 adds `inventory.read` and
    `inventory.manage` for owner and manager. A branch manager works only with storage
    places of their location; the material list is changed by a company-wide manager or
    owner. The permissions are not delegable and are not given to platform support.
    Audit events hold identifiers, the document kind and the line count, without names
    or notes.
11. **No money.** The package stores no price, cost or amount and posts no journal
    entry. No ledger source kind is added. A later costing package must extend these
    movements instead of keeping a second stock record.
12. **API and UI.** Routes under `/v1/businesses/{id}/inventory/...` for materials,
    places, documents and balances. Two workspace sections, "Materials" and "Stock
    documents", on desktop and mobile, with recovery after a lost answer.

## Bounded change to existing code

- `business/modules.py`: dependency, readiness source, limits and stops of `inventory`;
  registry version 3.
- `auth/permissions.py`: two permissions; version 7.
- `business/module_gate.py`: the module constant.
- New migrations from 0036; migrations 0001–0035 stay unchanged.
- A packaged schema check for the new tables, and their policies in the restoration
  step of `tests/integration/test_location_access.py`.
- `web/components/management-layout.tsx`: two sections.
- No change to booking, occupancy, the ledger, financial documents or workforce.

## Alternatives considered

- **Cost and ledger postings now** (plan choice 2B). It needs a costing method, account
  mapping, closed-period rules for every movement and currency handling. STOCK-01 does
  not need it; the master plan places cost in stage 6 and material consumption in
  BEAUTY-01. Deferred, with the movements shaped so that cost can be added to them.
- **Counterparty-owned stock** (3B). That is customer warehouses and 3PL of stage 6.
- **A minimal `products_services` module first** (4B). Two modules to accept instead of
  one, and a material is not necessarily a product for sale.
- **Balance computed from movements under an advisory lock, without a balance row.**
  Direct SQL would bypass the lock and the non-negative rule.
- **Editable or deletable documents.** They break the history rule of the platform.
- **`numeric` or floating-point quantities.** A fixed scale per material is exact and
  matches how money is stored.
- **Server drafts** (8B). More states and rules for the first package; offered as a
  choice because the cost falls on the person typing a long receipt.
- **Negative balances with a warning** (5B). It removes the one invariant that makes
  two competing write-offs decidable.

## Acceptance and status

The matrix J-01–J-12 is in the plan. The module stays closed by the readiness lock until
the acceptance commit; tests enable it only by substituting readiness in fixtures, with
a separate refusal test. This ADR becomes Accepted only together with the technical
acceptance of STOCK-01, by the owner's decision.

## Limits

No cost, prices, journal entries or purchase orders; no batches, serial numbers or
expiry dates; no customer-owned goods; no stock count document, reservations or
automatic consumption by a service; no unit conversion, barcodes, import, export, file
attachments or low-stock notifications; no sale of materials; no transfer between legal
entities; no group reporting. Deployment and production migrations are not authorized
by this ADR.
