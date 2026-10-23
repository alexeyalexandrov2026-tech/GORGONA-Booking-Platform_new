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

## L7b split (added during L7b, same delegation)

L7b1: on a confirmed booking, the **visit desk** completes the visit (optional actual quantities;
planned and actual shown) and writes its materials off (owner, storage place of the visit's branch,
date); `GET .../bookings/{id}/completion` reads a completion back (`booking.read`, branch scope).
L7b2: the visit invoice, the commission, prepaid redemption, the commission plan and prepaid sales.

| id | Requirement (L7b1, NOT TESTED) |
|---|---|
| L7-05 | A started visit is completed from the desk with an actual quantity; planned and actual are shown and read back after a reload |
| L7-06 | Its materials are written off from the desk once; the database holds the write-off of the actual quantity |
| L7-07 | Desktop and mobile, keyboard only, axe without violations, no horizontal scroll |

## L7b2 split (added during L7b2, same delegation)

L7b2a: the visit desk gets **Billing** — one draft invoice of the visit (book, customer, receivable and
revenue accounts, number, date); finance issues it and records the payment on its own screens; the desk
then shows "paid of total" and, once the visit is paid, accrues the specialist's commission once (expense
and payable accounts, number, date). The Staff screen gets the **commission plan** of a specialist (who is
paid, currency, rules of one service or of all other services, each a percentage or a fixed amount). Two
reads are added for the screens: `GET .../staff/{id}/commission` and `GET .../bookings/{id}/commission`
(`finance.read`). L7b2b: selling a prepaid balance and redeeming it from the desk.

| id | Requirement (L7b2a, NOT TESTED) |
|---|---|
| L7-08 | A manager saves a specialist's commission plan (payee, rule for all other services, percentage) and reads it back |
| L7-09 | A confirmed visit is billed from its desk as a draft invoice; after finance issues and settles it, the desk shows it paid in full |
| L7-10 | The commission of the paid visit is accrued once from the desk; the database holds the accrual of the plan's amount |
| L7-11 | Desktop and mobile, keyboard only, axe without violations, no horizontal scroll |

## L7b2b decisions (added 2026-10-23, same delegation)

45. **A Prepaid screen.** A new "Prepaid" screen lists the business's prepaid balances (customer, package
    of a service or certificate, remaining units or value, usable or waiting for payment), filtered by
    customer, and sells one: a package names a service and its units, a certificate only a value; the sale
    is a draft invoice line on a prepayment liability (L6 decision 34). Finance issues and settles it on its
    own screens; the balance becomes usable once its invoice is paid in full.
46. **One list read.** `GET /v1/salons/{id}/prepaid` (`finance.read`, company-wide data like every FIN-03
    read): balances in creation order, at most 50 a page with an `after` cursor, optionally of one
    customer. A balance is shown with its sale invoice, as the L6 view already is.
47. **Redemption on the desk.** When the visit invoice is issued and still open, the desk's Billing lists
    the usable balances of the invoice's customer in its currency and redeems one with a credit number and
    a date (L6 decisions 36-38: a credit note issued at once). The desk then shows what was credited. A
    credited visit's commission stays a manual matter (L5).

| id | Requirement (L7b2b, NOT TESTED) |
|---|---|
| L7-12 | The list read returns balances in creation order, pages with a cursor, filters by customer, needs finance read rights and never shows another business's balance |
| L7-13 | A manager sells a package from the Prepaid screen; after finance issues and settles its invoice the screen shows it usable |
| L7-14 | The package is redeemed from the desk of an issued visit invoice; the desk shows the credit; the database holds one redemption and one used unit |
| L7-15 | Desktop and mobile, keyboard only, axe without violations, no horizontal scroll |

## L7c decisions (added 2026-10-23, same delegation)

Branch `codex/package-l7c-customer-site` from the L7b2b head (`ee2b57b`). The guest API is already done
(L2b, L2c: decisions 8-15); this slice is the customer site only. No migration, no API change.

48. **Several services in one visit.** On the Service step, "Add another service" adds a line, up to four
    after the first (five in all, decision 12). Each line has its own service select (named by
    `aria-label`, "Service 2" ... "Service 5"), its own optional add-ons and a "Remove service N"
    button. A line offers only services not already chosen in the visit and in the first service's
    currency. "Continue to times" waits until every added line has a service.
49. **Compatibility shown, server decides.** An add-on is offered on a line when, across the whole visit,
    it is in the visit's currency, chosen on no other line, its requirements are provided by some line
    or other chosen add-on, and it neither provides nor conflicts with anything already provided (the
    same rules as decision 12). Everything else (a service whose component is already in the visit, a
    visit over 720 minutes, a specialist who does not serve every service) is judged by the server; its
    refusal is shown in its own plain words. A refusal of the visit itself (`INCOMPATIBLE_SELECTION`,
    `SERVICE_NOT_BOOKABLE`, `ADD_ON_NOT_BOOKABLE`) offers no "Retry", since the same request cannot
    succeed; every other failure keeps "Retry availability" as before.
50. **Only one specialist.** The specialist list on the Times step holds the specialists of the branch
    who serve **every** service of the visit (decision 14). Changing any line clears the chosen
    specialist, the time and the quote.
51. **The summary is the server's quote.** The summary lists every quote line in order (each service
    followed by its add-ons) with its price, then the visit total and duration. A version 2 quote also
    lists its stages in order, in plain words and minutes: "With your specialist", "Processing — your
    specialist is free meanwhile", "Finish". The review and the confirmation name the services of the
    visit.
52. **Requests unchanged for one service.** Availability and the hold send `extra_lines` only when the
    visit has more than one service; a one-service request is byte-identical to today's (decision 11),
    so its idempotency fingerprint is the same.
53. **Contracts reused, never loosened.** The strict `quoteSchema` (version 1 or 2) parses every answer;
    the pure helpers that build the request and judge add-ons live in `web/lib/visit.ts` with unit
    tests.

| id | Requirement (L7c, NOT TESTED) |
|---|---|
| L7-16 | The web helpers: a one-service request has no `extra_lines`; a visit sends them in order; add-on compatibility follows decision 49; a two-line version 2 quote parses strictly |
| L7-17 | A guest chooses a staged service and a second service, sees both lines with prices, the visit total and duration and the stages in order; holds and confirms; the database holds one confirmed booking whose quote has both services and whose intervals hold the specialist, chair and equipment as planned |
| L7-18 | A visit the server refuses (a component already in the visit) shows the server's plain reason and offers no retry |
| L7-19 | Only specialists serving every service are offered |
| L7-20 | Desktop and mobile, keyboard only, axe without violations, no horizontal scroll; the old one-service journey still passes |
