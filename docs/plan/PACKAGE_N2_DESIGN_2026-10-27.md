# Package N, slice N2 — tenders (2026-10-27)

Owner 2026-10-27: «Делай как считаешь нужным я доверяю тебе», then «Ок» to "next N2". Plan:
[PACKAGE_N_PLAN_2026-10-26.md](PACKAGE_N_PLAN_2026-10-26.md) (decisions 3, 4, 7); builds on N1
([ADR-0034](../adr/0034-broker-authority-and-carrier-profiles.md)). Branch `codex/package-n2-tenders` from
`590a8f3` (`main` after the package M review fixes).

## Scope

- Migration **0082**:
  - `transport_tenders` — an insert-only offer with a client id: trip, the tendered legs (a non-empty set of leg
    positions of that trip), the carrier (a counterparty), the carrier rate (currency, basis fixed or per mile,
    amount; the same bounds and precision as M7a), terms, an offer time and an expiry;
  - `transport_tender_answers` — insert-only answers: `accepted`, `declined`, `withdrawn`, each with a source
    (`email`, `phone`, `load_board`, `other`), the time it happened and who recorded it.
- State is derived, never stored: `offered` until an answer or the expiry; then `accepted`, `declined`,
  `withdrawn` or `expired`. From `offered`: accept, decline or withdraw before the expiry. From `accepted`: only
  withdraw (the broker takes the load back). Anything else is 409 `TRANSPORT_TENDER_CLOSED`.
- **Eligibility:** offering and accepting are refused (409 `TRANSPORT_BROKER_NOT_ELIGIBLE` /
  `TRANSPORT_CARRIER_NOT_ELIGIBLE`, with the N1 reasons) unless the broker authority and the carrier are eligible
  on the date of the offer or the acceptance, taken in the time zone of the trip's first stop.
- **One accepted tender per leg:** offering and accepting take the advisory lock `gba:trip-tender:<trip>`; an
  accept whose legs overlap another accepted (not withdrawn) tender is 409 `TRANSPORT_LEG_TENDERED`. Two racing
  accepts leave one; the test observes the second waiting on the advisory lock in `pg_locks`.
- **Idempotency:** a repeated offer with the same id and body returns the stored tender, a different body is 409;
  a repeated identical answer returns the tender unchanged.
- Routes under `/v1/businesses/{id}/transport`: `GET trips/{trip}/tenders`, `GET/PUT tenders/{tender}`,
  `POST tenders/{tender}/answers`; all need `transport.broker` and the module; writes go through `module_writes`
  and idempotency `claim`/`complete`.
- **Change to the plan:** a carrier on the platform does not answer in its own company yet; in N2 the broker
  records every answer with its source. Cross-company answering is decided with N4 (tracking by the carrier).
- Next migration after this slice: **0083**.

## Acceptance of N2 (NOT TESTED)

| id | Requirement |
|---|---|
| N2-01 | A tender is offered for some legs of a trip and read back; a repeat with the same body is the same tender, a different body is 409; legs outside the trip are 422 |
| N2-02 | Answers move the state: offered → accepted → withdrawn; offered → declined; offered → withdrawn; after the expiry the tender is expired and cannot be accepted; a closed tender refuses further answers |
| N2-03 | Offering and accepting are refused with the named reasons when the broker authority or the carrier is not eligible on that date |
| N2-04 | A leg has at most one accepted tender; a withdrawn acceptance frees it; two racing accepts on overlapping legs leave one (observed advisory-lock wait) |
| N2-05 | Only owners and managers with `transport.broker` read or write; a front desk, a carrier dispatcher with every transport right, another company and the module off are refused; direct SQL updates and deletes are refused |
| N2-06 | Upgrade 0081 → 0082 keeps every row; the full suite stays green |
