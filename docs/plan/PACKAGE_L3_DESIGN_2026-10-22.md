# Package L, slice L3 — visit completion and material consumption: design (2026-10-22)

**Status: design; decisions taken by the agent under the owner's full delegation** («Делай как
считаешь нужным и правильным! Я полностью даю тебе право выбора», 2026-10-22). Branch
`codex/package-l3-consumption` from L2c (`f255e6b`). Builds package L decision 4
([plan](PACKAGE_L_PLAN_2026-10-22.md)) on STOCK-01. A platform part: any direction that consumes
materials per service (salons, clinics, workshops, car care) records and posts it the same way.

## What exists (inspected)

- STOCK-01: materials (`stock_items`, quantity as a whole count of the smallest fraction of the unit,
  scale 0–3), storage places per branch, write-off documents (reason `used` debits consumption)
  valued at moving-average cost and posted with one journal entry, idempotent by key.
- Posting a write-off needs a company-wide member with `inventory.manage` and `finance.manage`, under
  the ledger posting lock (`api/stock.py`).
- A booking is HOLD, CONFIRMED, CANCELLED or EXPIRED; its quote snapshot lists every variant and
  add-on line (L2c).

## Decisions

16. **Recipes per variant and per add-on.** `gba.service_materials` lists, for one variant or one
    add-on, the materials and quantities one service uses (at most 20 lines; a quantity in the
    material's smallest unit, like stock). The whole list is replaced at once with the owner's
    expected revision; `catalog.manage` is required; the revision of the variant or add-on moves.
17. **Completing is a fact, not a status.** `POST .../bookings/{id}/complete` records one
    `gba.visit_completions` row for a CONFIRMED booking whose start has passed; the booking stays
    CONFIRMED, so occupancy and every status rule are unchanged. Once per booking; a repeat with the
    same key answers the same, another key `VISIT_ALREADY_COMPLETED`. `booking.write` is required and
    the caller's branch scope applies.
18. **Planned and actual, both kept.** The planned quantity of each material is the sum of the
    recipes of the quote's lines (each variant and add-on, as recipes stand at completion). The
    caller may give the actual quantity of any material (also one the recipes do not name); without
    one the actual equals the planned. `gba.visit_material_uses` keeps both per material.
19. **Posting the consumption is a separate finance step.** `POST .../bookings/{id}/consumption`
    with the owner legal entity, the storage place and the document date posts one write-off (reason
    `used`) of the actual quantities through STOCK-01, at moving-average cost, once per visit (the
    document id is stored on the completion; a repeat answers the same document). It needs the same
    rights as any write-off: a company-wide member with `inventory.manage` and `finance.manage`. A
    visit with nothing to write off records that and posts nothing. A small salon's owner holds every
    right; the screen (L7) may do both steps in one action.
20. **Module gates.** Completion needs only booking. Consumption needs the inventory module; when it is
    off the answer is the module refusal and nothing is posted.
21. **Lineage.** The completion names its booking and, once posted, its stock document; the stock
    document's journal entry is the ledger lineage.

## Acceptance for L3 (NOT TESTED)

| id | Requirement |
|---|---|
| L3-01 | A recipe is replaced whole with the expected revision; a stale revision, an unknown material, a quantity finer than the material's scale and a foreign company's write are refused |
| L3-02 | Completing a started confirmed booking records planned quantities from the recipes of every quoted line; actual quantities replace them per material; both kept |
| L3-03 | A hold, a cancelled booking, a booking not started yet and a second completion are refused; the same key repeats the answer |
| L3-04 | Posting the consumption writes off the actual quantities once at moving-average cost with one journal entry; a repeat posts nothing new |
| L3-05 | Without inventory and finance rights, or with the inventory module off, nothing is posted |
| L3-06 | Branch scope and company isolation hold for the new tables and routes (direct SQL refusals) |
