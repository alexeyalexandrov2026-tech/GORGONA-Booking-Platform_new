# Package R, slice R8b — rental screens: rate cards, the agreement and the security (2026-11-11)

Plan: [PACKAGE_RENT_PLAN_2026-11-03.md](PACKAGE_RENT_PLAN_2026-11-03.md), slice R8, acceptance R-09.
Previous slice: [R8a](PACKAGE_R8A_DESIGN_2026-11-09.md); handoff [NEXT_AGENT_PACKAGE_R8B_2026-11-11.md](NEXT_AGENT_PACKAGE_R8B_2026-11-11.md).
Branch `codex/package-r8b-rental-agreement-screens` from the R8a docs commit `454c70f`. Same process: failing tests
first, gates on the VM `gorgona-dev`, a source-bound record, code and docs commits, push for CI without a PR. The owner
said "continue" (relayed by the parent session on 2026-11-11) and gave the word to start the VM.

R8 is split three ways: R8a (done) the catalogue, availability and bookings; **R8b** rate cards, the agreement and the
security; **R8c** handover and return, the settlement, damage charges, refunds and the reconciliation.

## Scope of R8b

- Web only; **no API change and no migration** (next migration stays 0108).
- `web/components/rental.tsx` gains a rate card section and, on the booking page, the agreement and the security;
  `web/lib/rental-contracts.ts` gains strict contracts of the R4a-R5a responses used; `web/lib/rental-api.ts` their
  reads and commands.
- Tests: `web/tests/rental-contracts.spec.ts` (new cases), `web/tests/rental-agreement.spec.ts` (real browser, desktop
  and mobile, `test:management:rental-agreement`) and `api/tests/integration/test_r8b_rental_agreement_browser.py`.

## Decisions (R8b, agent)

1. **Rate cards**: the list per class and branch with version, currency, rates, meter allowance and excess rate; a new
   version names a class, a branch, a currency, at least one of the hour, day, week and month rates and the optional
   meter terms. Money is entered in major units and sent in minor units of the currency; the server decides the
   version and refuses what it does not accept.
2. **The agreement** on the booking page: before acceptance the server's quote for the booking (rental, days and
   total); acceptance records the source (platform, paper, email), who accepted and when; then the versions with their
   period, rental, total, source and who accepted. Extensions and extras stay with the API (R4b, R4c) for now.
3. **The security**: a request with an amount and a method; then the server's state and figures (held, captured,
   released, expired, remaining) and the events; an event names its kind and amount, a reference for a hold and a
   basis for a capture. Capturing needs `rental.approve` on the server; the screen does not decide it.
4. Every figure is the server's; a command keeps its Idempotency-Key until it succeeds; accessibility and times as in
   R8a.

## Acceptance of R8b — NOT TESTED

| id | Requirement | Result |
|---|---|---|
| R8b-01 | Strict contracts accept every R4a-R5a response the screens read and refuse unknown fields and bad values | NOT TESTED |
| R8b-02 | In a real browser (desktop and mobile) an owner adds a rate card, sees the quote, accepts the agreement, requests the security, holds it and captures part with a basis; the database holds them | NOT TESTED |
| R8b-03 | Axe finds no violation; no horizontal scroll on mobile | NOT TESTED |
| R8b-04 | Web static checks and the full suite stay green | NOT TESTED |

## Not in R8b

Agreement extensions and extras on screen, rate card extras, provider evidence on screen (R5b), handover, return and
settlement (R8c); acceptance (R9).
