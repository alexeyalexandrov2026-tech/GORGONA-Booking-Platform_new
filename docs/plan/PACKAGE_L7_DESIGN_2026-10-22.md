# Package L, slice L7 — screens: design (2026-10-22)

**Status: design; decisions taken by the agent under the owner's full delegation** («Делай как
считаешь нужным и правильным! Я полностью даю тебе право выбора», 2026-10-22; «continue»). Built on
L1–L6 (`1df0a6c`). The screens are platform parts: the words are "specialist", "service", "visit",
never a single direction.

## What exists (inspected)

- The management app (`web/`, Next.js static export) checks every API answer against a strict schema
  chosen by path (`lib/management-contracts.ts`); a write that takes an idempotency key keeps it until
  answered so a retry is safe.
- Browser proof: a Python test starts the API with a fake identity provider and runs a Playwright spec
  against the built app on desktop and mobile, with keyboard use, axe and no horizontal scroll.
- Gaps found: the new `/bookings/{id}/...` routes would be checked against the plain booking schema; a
  recipe can be replaced but not read.

## Decisions

40. **Three screen slices.** L7a, the catalog: stages and materials of a service on the Services
    screen, equipment as a kind on the Staff screen (plus `GET` of a recipe). L7b, the visit desk: on a
    booking, complete it with actual quantities, post the consumption, bill it, accrue the commission
    and redeem a prepaid balance; the commission plan on the Staff screen; selling a prepaid balance.
    L7c, the customer site: choose several services and see the stages of a staged one.
41. **Strict contracts first.** Every new answer gets a strict schema chosen by its exact path before
    a screen reads it; an unrecognized shape is an error on screen, never trusted.
42. **Safe writes.** A write with an idempotency key keeps its key until answered; a stale revision
    reloads and says so; a refusal shows its plain reason.
43. **Proof.** Every slice is proven in a real browser on desktop and mobile: keyboard only, axe
    without violations, no horizontal scroll, and the data it shows read back from the API.
44. **Neutral words.** Shared parts say specialist, service, visit, materials and prepaid balance.

## Acceptance for L7a (NOT TESTED)

| id | Requirement |
|---|---|
| L7-01 | A manager edits the stages of a service (kind, minutes, resource kinds), saves, sees the new duration; a stale revision reloads with a notice |
| L7-02 | A manager edits the materials of a service (material, quantity) and reads them back; a quantity finer than the material allows shows the refusal |
| L7-03 | Equipment can be added as a resource kind |
| L7-04 | Desktop and mobile, keyboard only, axe without violations, no horizontal scroll |
