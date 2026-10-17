# ADR-0026 — Basic materials: owner-linked stock documents, moving-average cost and ledger postings

**2026-10-17 note (K1h, finding, fixed in K1i):** with statistics that do not describe a company, stock document checks can read a material's or company's whole history (found by `test_stock_scale`); three local fixes did not hold in the full suite and were reverted. Status unchanged. See the [finding](../plan/evidence/2026-10-17-k1h-stock-statistics/FINDING.md).

**2026-10-17 note (K1i, local, implemented in `42ead59`, not published):** migration 0047 makes the history keys unique indexes ending with `(tenant_id::text)`, reads source documents by lateral key lookups and compares a document's lines with its movements and valuations by `IS NOT DISTINCT FROM`, so one document's checks cannot read the history whatever the statistics (at most 1 row per node with a 100,016-row history). Status unchanged. See the [validation](../plan/evidence/2026-10-17-k1i-stock-plan-stability/VALIDATION.md).

- Status: **Proposed (2026-10-13)**. Slices J1–J6, both screens and the review fixes are implemented (see the
  implementation notes below); readiness remains locked pending the owner decision. The
  owner chose the twelve options
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

## Implementation notes — slice J2 (2026-10-13)

Slice J2 is commit `f8e1212` on the local branch `codex/package-j2-receipts`, on top of
slice J1: migration 0037, the posting rules of a book and receipts with amounts, with
their movements, balances, moving-average cost and `stock` journal entry. Write-offs,
returns and transfers are not implemented. Record:
[validation](../plan/evidence/2026-10-13-j2-receipts/VALIDATION.md).

Choices made while implementing; none of them changes an owner decision:

1. Posting rules are one versioned table per book, without a separate head row; every
   change takes the ledger posting lock.
2. Documents, lines, movements and balances carry the branch of their place, tied by
   composite foreign keys, so one branch policy covers them. Migration 0037 adds the key
   on storage places that these foreign keys need.
3. Amounts live in three company-only tables: the posting of a document (book, rule
   revision, entry, total), the valuation of each line and the cost of a material for
   an owner.
4. This codebase has no privileged functions, so the rule "only a movement changes a
   balance" is enforced at commit: a deferred check requires every balance to equal the
   sum of its movements, and every cost row to equal the sum of its valuations and the
   balances of its places. The check reads all movements of that material, place and
   owner; its cost with a long history is not measured.
5. The `stock` origin has its own triggers on the journal tables. The functions of
   package H are not rewritten; the ledger schema check takes the approved list of
   source kinds from migration 0037.
6. Reading the journal: `stock` joins the source kinds of view version 2 in the API and
   in the web contract. View version 1 still answers that an upgrade is required. This
   is a change to the ledger contract that the list of bounded changes above did not
   name.
7. A supplier and a supplier document number are accepted only for a purchase.
8. A receipt with a zero total keeps a posting row without an entry and posts nothing.
9. Refusals are typed: `STOCK_BOOK_REQUIRED`, `STOCK_RULES_REQUIRED` and
   `STOCK_ARCHIVED` (409); `STOCK_DATE_INVALID`, `STOCK_QUANTITY_INVALID` and
   `STOCK_AMOUNT_INVALID` (422); a closed month answers `LEDGER_PERIOD_CLOSED` like the
   ledger.
10. A line holds at most 999,999,999,999 smallest fractions of the unit and at most
    999,999,999,999,999 minor units of money.

Implemented from decision 2 for receipts: an archived material and an archived place
take no receipt.

## Implementation notes — slice J3 (2026-10-13)

Slice J3 is commit `565b68f` on the local branch `codex/package-j3-writeoffs`, on top of
slice J2: migration 0038 and write-offs at the moving-average cost, with their outbound
movements, balances, cost and `stock` journal entry. Returns and transfers are not
implemented. Record:
[validation](../plan/evidence/2026-10-13-j3-writeoffs/VALIDATION.md).

Choices made while implementing; none of them changes an owner decision:

1. Migration 0038 adds no table. It replaces the two checks of a document, so that a
   reason belongs to its kind in the database, and five functions.
2. Decision 6 says `round(V * q / Q)`. The database computes it half up with whole
   numbers, `floor((2 * V * q + Q) / (2 * Q))`, so the result never depends on a rounded
   quotient; `q = Q` takes exactly `V`.
3. The valuation trigger computes the amount of an outbound line and refuses any other.
   A writer still sends the amount, because the posting row with the document total
   precedes the valuations; the service computes it with the same formula under the
   ledger lock. The command of a write-off carries no amount.
4. An outbound movement lowers the balance with one conditional update of the balance
   row: it waits for a concurrent writer of that row and compares with what that writer
   left. A shortage is SQLSTATE `GBS02` in the database and 409 `STOCK_INSUFFICIENT` in
   the API, with the line number and the available quantity. The cost row refuses the
   same way when the owner as a whole holds less.
5. The posting command names its kind: `kind` is required and selects the strict shape
   of a receipt or of a write-off. In slice J2 a body without it was a receipt.
6. The packaged schema check now also verifies `gba.assert_stock_document`, the function
   that the consistency triggers call. Slice J2 verified trigger functions only, so a
   replaced body of this function would not have been noticed.
7. A balance row and a cost row brought to zero stay and read as zero. One line of a
   write-off leaves at most 999,999,999,999,999 minor units, the line limit of slice J2;
   a larger value leaves in parts.

Implemented from decision 2 for write-offs: an archived material and an archived place
still allow outbound movements.

## Implementation notes — slice J4, transfers (2026-10-13)

The first part of slice J4 is commit `0d923a4` on the branch `codex/package-j4-transfers`,
on top of slice J3: migration 0039 and transfers between storage places. Returns are the
second part and are not implemented. Record:
[validation](../plan/evidence/2026-10-13-j4-transfers/VALIDATION.md).

Choices made while implementing; none of them changes an owner decision:

1. Slice J4 is done in two parts, transfers first (migration 0039) and returns second
   (migration 0040). The scope of the package is unchanged.
2. Migration 0039 adds no table. A document gains two nullable columns, the destination
   place and its branch, with a foreign key and a check: only a transfer names a
   destination, and never its own place. The migration replaces the two checks of kinds
   and reasons and five functions.
3. A transfer has one fixed reason, `relocation`; its command carries no reason and no
   amount.
4. A transfer moves no money. Every line has exactly two movements, out of the place of
   the document and into the destination, with the same owner, material and quantity, so
   what the owner holds and its cost row do not change. The database refuses a posting
   row, a valuation and a `stock` journal entry for a transfer. It needs no book and no
   posting rules, and neither the accounting start nor a closed period applies to it.
5. A transfer takes no ledger lock. Balance rows order it with every other document: the
   service locks the rows of both places in the order material, place before it writes,
   and writes the movements in that order. A write-off locks its rows in the same order.
6. Who may transfer is enforced from the membership of the author: a company-wide owner
   or manager, or an owner or manager whose branch is the branch of both places. The API
   runs a transfer in the branch scope of the caller with `inventory.manage` alone; the
   finance right that a receipt and a write-off need is not asked for.
7. A document belongs to the branch it leaves. A transfer between branches is therefore
   read by the source branch, and the destination branch reads its balance. The date is
   not in the future of the source branch.
8. From decision 2: an archived place takes no transfer in and still lets its balance be
   moved out. An archived material is not transferred at all, because a transfer is also
   an inbound movement; its balance leaves by a write-off.
9. The owner legal entity of a transfer is not looked up separately, because a
   branch-limited member cannot read legal entities. An unknown owner holds nothing, and
   the answer is the typed shortage, which discloses nothing.
10. The packaged schema check learned the columns and foreign keys that a later migration
    adds to an earlier table, and adds up insert grants across migrations.

## Implementation notes — slice J4, returns (2026-10-13)

The second part of slice J4 is commit `4bd346c` on the branch `codex/package-j4-returns`,
on top of the transfers: migration 0040 and returns against a source line. Record:
[validation](../plan/evidence/2026-10-13-j4-returns/VALIDATION.md).

Choices made while implementing; none of them changes an owner decision:

1. Migration 0040 adds no table. A document gains its source document; a line gains its
   source document and source line, with a key that lets one return name a source line
   once; a valuation gains the share of the amount of the source line. The migration
   replaces four checks and five functions.
2. One return names one source document. A line names a line of it and a quantity; the
   material is the material of that line and the command carries no amount.
3. The reasons follow the source: `supplier_return` or `entry_error` against a receipt,
   `unused` or `entry_error` against a write-off. The database refuses the others.
4. A return has its own storage place: where the material leaves from or comes back to.
   It need not be the place of the source document, because a transfer may have moved
   the material since.
5. The limit of decision 9 is checked by the line trigger under `for update` of the
   source line. A line never changes, so the runtime role had no right to lock one: it
   now holds UPDATE on one column of a line, and the immutability trigger still refuses
   every change. The refusal is SQLSTATE `GBS03`, 409 `STOCK_RETURN_EXCEEDED` in the API.
   Returns are money documents and queue on the ledger lock first, so this row lock is a
   second line of defence.
6. The share of a line amount is taken from what is left of the line: left amount times
   the returned quantity over the left quantity, half up with whole numbers. It is
   proportional to the quantity, the return that completes the line takes the remainder,
   and no share can exceed what is left. The valuation trigger computes it and refuses
   any other.
7. The account that a return moves for its source comes from the posting rules the
   source was posted with; the price-difference account comes from the current rules,
   which the return itself is posted with.
8. A journal entry carries one line per account, so two accounts that coincide are
   netted. The whole-document check compares the set of accounts and amounts for every
   kind of money document instead of two lines in a fixed order.
9. The total of a document is what it moves on the inventory account. A return of a
   receipt can post an entry with a zero total, when only the receipt account and the
   difference move; the table check therefore asks for an entry only when the total is
   above zero, and the whole-document check decides the rest.
10. A return to the supplier may name the supplier and the supplier's document number.
    The supplier is not compared with the supplier of the receipt.
11. The date of a return is not compared with the date of its source: cost follows the
    order of posting, as decision 6 says. From decision 2, an archived place and an
    archived material let a return leave and take none in.

## Implementation notes — review fixes (2026-10-14)

An independent read-only review of J1–J4 found no critical or high defect. Commit
`33a3ec6` on `codex/package-j-review-fixes` fixes its findings M1, L1, L2, L4, L5 and part of L3:
[record](../plan/evidence/2026-10-14-j-review-fixes/VALIDATION.md),
[review](../plan/evidence/2026-10-13-j-review/REVIEW.md).

1. Every writer takes the balance rows that exist before it inserts new ones, in the
   order material, place: receipts and returned write-offs now do so too, so they no
   longer deadlock with transfers. A deadlock that PostgreSQL still breaks answers
   409 `STOCK_BUSY`, and the same command with the same key can be repeated.
2. Migration 0041 replaces the balance and cost checks: a row that no movement or
   valuation explains is refused at commit, even when it holds zero.
3. The accounts of an entry are checked before anything is written; an archived one
   answers 409 `STOCK_ACCOUNT_ARCHIVED` with its `account_id`. Archiving an account
   stays allowed (owner's delegation of 2026-10-14; the executor's decision).
4. The supplier of a document is read only together with the amounts.
5. The schema guard refuses rewrite rules on the stock and journal tables and checks
   the grantee of insert rights. Names, units and supplier document numbers refuse C1
   control characters.

## Implementation notes — slice J5a, the Materials screen (2026-10-14)

Commit `afda55b` on `codex/package-j5-screens`:
[record](../plan/evidence/2026-10-14-j5-screens/VALIDATION.md). The executor split J5 in
two, as J4: J5a is this screen, J5b the Stock documents screen.

1. An uncertain command is settled by its key: `POST .../inventory/commands/{key}/resolve`
   and `/cancel`, the approach of the workforce screens without a new table. The reference
   names the operation, the subject and the version the command produces (0 for a
   document). A discard claims the key with a 410 marker, at most 20 per person a day, and
   is audited; the late copy of the command is refused as a reused key.
2. The screen `/materials/` shows materials, places, balances, the cost at the moving
   average and the accounts of materials, each only to whom the server serves it. Without
   a ledger book it explains that the accounts belong to the owner's book and links to the
   ledger.
3. The browser keeps only the key and the reference of an unconfirmed change, never a
   name, quantity, amount or token. No migration.

## Implementation notes — slice J5b, the Stock documents screen (2026-10-14)

Commit `c3da59d` on `codex/package-j5b-stock-documents`:
[record](../plan/evidence/2026-10-14-j5b-stock-documents/VALIDATION.md). With it slice J5
is complete.

1. The screen `/stock-documents/` lists, opens and posts receipts, write-offs, transfers
   and returns through the routes of J2–J4; no server change and no migration. A branch
   manager posts transfers only, reads no amounts and knows the owner as "Company".
2. The command centre of J5a is shared by both inventory screens: one unconfirmed
   inventory command per person and business, settled by its key; a document names no
   version.
3. A refusal of the server is shown next to the submit button with a named text.

## Implementation notes — acceptance preparation, M2 (2026-10-14)

Commit `35227cd` on `codex/package-j-acceptance-prep`:
[record](../plan/evidence/2026-10-14-j6-acceptance-prep/VALIDATION.md).

1. Migration 0042 gives every movement its place in the history of its balance and the
   balance after it, and every valuation the quantity and value after it. Only the insert
   triggers write them, from the head of the history after checking the stored total
   against it; the checks at commit compare a total with that head. A forged total is
   refused as before.
2. The guard of a stock journal entry finds its document by key; it read every stock
   document of the company. Two indexes that the new keys begin with are dropped.
3. A total that a document would carry past its limit is refused by name:
   `STOCK_QUANTITY_INVALID` or `STOCK_AMOUNT_INVALID`.
4. Measured with 100,000 movements of one balance: a posting took 960 ms before and 43 ms
   after (45 ms with no history). Migration 0042 rewrites every movement and valuation:
   like 0037, it needs a maintenance window when deployed.

## Implementation notes — review of J5 and J6, part 1 (2026-10-14)

An independent read-only review found that the commit-time checks of migration 0042 passed
a forged total when the session changed its company or branch before commit, because an
unseen total equalled an unseen head. Migration 0043 (`f366afe`) refuses a total that a
check cannot see. [Review](../plan/evidence/2026-10-14-j5-j6-review/REVIEW.md),
[record](../plan/evidence/2026-10-14-j5-j6-review-fixes/VALIDATION.md).

## Implementation notes — J5/J6 review fixes part 2 (completed 2026-10-15)

Commit `7b96fec`: paginated client catalogues, refusal of an unknown return material,
the distinct document-total bound and command subject checks. The new-destination race
uses two different sources and identifies the INSERT wait on the leader in pg_locks.
No schema change. [Record](../plan/evidence/2026-10-14-j5-j6-review-fixes-part2/VALIDATION.md).

L1: intermediate balance_after/quantity_after/value_after values backfilled by 0042 are approximate: transaction ids order transaction starts, not commit order; final totals remain the authoritative reconciliation. L4: cancellation tombstones expire after 24 hours with idempotency keys; a late command after expiry can be executed. These are recorded limits, not fixes. Earlier review L6: migrations 0037 and 0042 require a maintenance window and coordinated application/schema deployment; no deployment is authorized. The platform-wide current-user/current-tenant function body guard remains outside Package J. Review-2 gaps 3–5 remain unmeasured or untested as described in REVIEW.md; no new claim closes them. Additional pre-existing UI follow-up, confirmed by code inspection only: DocumentForm filters archived materials and places out of outbound selectors too, although the API permits supported outbound operations. This slice preserves that UI behavior; browser validation of that gap is NOT TESTED (web/components/stock-documents.tsx, open/usable selectors).

## Implementation notes — K1i, plans independent of statistics (2026-10-17)

Commit `42ead59` (package K branch, local): migration 0047 replaces `stock_movements_sequence_key` and
`stock_valuations_sequence_key` by unique indexes of the same names and the same uniqueness, with the
company last as `(tenant_id::text)`; source-document lookups in three triggers use `LEFT JOIN LATERAL
… LIMIT 1` on the full key; `assert_stock_document` compares by `IS NOT DISTINCT FROM`. The inventory
guard approves both indexes by exact definition. `test_stock_scale` checks the plan with
`auto_explain` (at most 100 rows per stock-table node; observed 1). Full suite 2056 passed, 4 skipped.
[Record](../plan/evidence/2026-10-17-k1i-stock-plan-stability/VALIDATION.md).

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
