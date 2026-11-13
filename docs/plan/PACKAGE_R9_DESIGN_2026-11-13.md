# Package R, slice R9 — acceptance of rental (RENT-01) (2026-11-13)

The owner said "OK" on 2026-11-13 after R8c, under full delegation («Делай как считаешь нужным я доверяю тебе»),
and added «Нет, мы работаем на сервере. Мы не работаем локально.»: the whole slice runs on the VM `gorgona-dev`
(the branch, the edits, every run, the record, the commits and the push). Branch
`codex/package-r9-rental-acceptance` from `7eafa7b` (R8c docs). Plan:
[PACKAGE_RENT_PLAN_2026-11-03.md](PACKAGE_RENT_PLAN_2026-11-03.md), slice R9. Model: the N7 acceptance of package N
([PACKAGE_N7_DESIGN_2026-10-29.md](PACKAGE_N7_DESIGN_2026-10-29.md)).

## Found while preparing R9: R-09 does not hold

- The agreement acceptance, change and period change accept the source `platform` from a business member, and the
  screen offers "Platform". No customer answers on the platform yet: that needs a grant (plan decision 9, R4b
  decision 2) and is not built. A member can therefore record "the customer accepted on the platform" with no grant
  behind it.
- Construction refuses the same source for the same reason (O2, O6a).
- **Fix:** the three agreement inputs take `paper` or `email` only (422 otherwise); the screen offers Paper and
  Email. As in construction, the database check keeps `platform` reserved for the customer's own answer through a
  grant, and the view contract still reads it. No migration; the next migration stays 0108.

## Scope

- The fix above, failing tests first:
  - the end-to-end test below refuses `platform` on acceptance, change and period change;
  - `web/tests/rental-agreement.spec.ts` checks that the Source options are Paper and Email.
- One end-to-end test, `api/tests/integration/test_r9_rental_acceptance.py`, of a whole rental through the API and
  PostgreSQL (FAKE data):
  - two cars of one class; two class bookings take both, and a third overlapping booking is refused
    (`RENTAL_UNAVAILABLE`); a booking holds no unit until one is assigned;
  - the agreement freezes the quote, and a later rate card version does not change it;
  - one unit cannot be issued to two overlapping bookings (`RENTAL_UNIT_BUSY`);
  - a maintenance block after the period refuses an extension into it (`RENTAL_UNIT_BUSY`); an extension that
    fits is agreement version 2;
  - the security is requested, held and partly captured with a basis;
  - the handover and the return record the meters and a new dent; the return is late; the usage derives the
    overdue hours and the excess;
  - the settlement invoice is rental, excess and late from the frozen terms; it leaves the security as it was;
  - the damage charge on the new dent needs `rental.approve` and refuses the old mark; it leaves the settlement as
    it was;
  - an external refund is its own record; the rest of the security is released once;
  - the reconciliation derives every figure;
  - the rows are read back; direct SQL updates are refused; with the module off, writes are refused.
- An acceptance record, `docs/plan/evidence/2026-11-13-r9-acceptance/ACCEPTANCE.md`:
  - RENT-01 and R-01..R-10, each with its proof from R1–R9 and its limits;
  - the slices with their code commits, suites and CI;
  - the independent review stays open.

## Not in this slice

- The independent review (one extra agent) needs the owner's consent; it stays open in the record.
- Readiness of rental, enabling it, `main`, a PR, deployment and live providers: only on the owner's word.

## Acceptance of R9 — PASS (code `2388cda`, [checks](evidence/2026-11-13-r9-acceptance/CHECKS.json))

| id | Requirement | Result |
|---|---|---|
| R9-01 | The agreement refuses the source `platform` on acceptance, change and period change; the screen offers only Paper and Email | PASS |
| R9-02 | The end-to-end test passes on PostgreSQL with the rows read back | PASS |
| R9-03 | The record maps RENT-01 and R-01..R-10 to proofs and limits, with the review open | PASS |
| R9-04 | Web static checks and the full suite stay green; one executor, one disposable cluster | PASS |

The R9 checks cover the staff write fix. R-09 remains PARTIAL because the customer grant flow is open.
