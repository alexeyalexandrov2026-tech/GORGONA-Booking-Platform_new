# Package N slice N8 — fixes of the independent review (design)

Owner 2026-10-30: "Yes, run review", then "Start N8", under full delegation. The one independent review of
package N (one read-only agent, HEAD `4861b85`) found RN-01..RN-09; each is fixed here with a failing test
first. Branch `codex/package-n8-review-fixes` from `4861b85` (N7 docs). Migration `0086`.

## Fixes

| id | Defect | Fix | Proof (failing first) |
|---|---|---|---|
| RN-01 high | The tender accrual's FIN-03 draft stays editable (R-01 again) | `financial_documents` freezes a draft linked from `transport_tender_accruals` | Draft save after accrual: 409 `FINANCIAL_DOCUMENT_LINKED` |
| RN-02 high | A re-plan moves the legs and stops under an accepted tender | `save_trip` refuses 409 `TRANSPORT_TRIP_TENDERED` while an open offer or an accepted, not withdrawn tender covers the trip, under the `gba:trip-tender` lock; 0086 trigger refuses leg and stop insert, update and delete for such a trip | API 409 and direct SQL refused |
| RN-03 med | Carrier A's departure at a shared stop closes carrier B's leg | A carrier records events only at stops whose every leg is its own accepted leg; else 403 `TRANSPORT_EVENT_OUT_OF_SCOPE` | A departs shared stop 1: 403; B's leg stays open |
| RN-04 med | Withdraw after accrual lets the same legs be paid twice; rate versions change after accrual | Withdrawal, a new proposal and an answer to one are refused after accrual (409 `TRANSPORT_ALREADY_ACCRUED`), in the API and in 0086; 0086 refuses agreeing a version of a withdrawn tender; `accrue` takes `gba:trip-tender` and reads the answers under it | Accrue then withdraw / propose: 409; SQL refused |
| RN-05 med | A carrier sets its own answer time (backdates past expiry or eligibility) | A carrier's platform answer takes the server time; `occurred_at` is no longer accepted from a carrier (422); the screen sends the time of the click, not of the panel's mount | Carrier answer with an old time: 422; expired offer: 409 `TRANSPORT_TENDER_CLOSED` |
| RN-06 med | Unlinking a carrier widens its rights | The restriction applies to every servicer holding `transport.tender` or present in any link version | N4-04, unlink, event on an untendered stop: 403 |
| RN-07 med | A linked carrier reads the broker's whole book | For a carrier servicer, `GET /trips` lists only trips with its accepted legs, other trips 404; orders, drivers and vehicles 403 | Carrier `GET /trips` lists one trip; `GET /orders` 403 |
| RN-08 low | The margin adds carrier pay in different currencies | `carrier_cost` and `margin` are null and `currencies_differ` true when currencies differ; the screen shows the currency | USD invoice, CAD tender: null |
| RN-09 low | Legs already run by the broker's own fleet can be tendered | A tender on a leg with any stop event, or on a trip not planned, is refused 409 `TRANSPORT_LEG_STARTED` | Tender after an event: 409 |

Record claims corrected in `ACCEPTANCE.md`: N7 is rewritten so the tenders come before any event and each
carrier company records its own leg's events (a true brokered flow); TMS-01/02, N-03, N-07, N-08 cite N8; N-09
becomes PARTIAL (keyboard-only not run); the N6 authority-save fix gets a browser test that delays the read
and sees "Save authority" disabled.

## Limits kept

- A carrier on its own trip still sees the stop places of the other legs of that trip.
- Readiness, enabling transport, `main`, PR, deployment: only on the owner's word.

## Acceptance of N8 (PASS, 2026-10-30)

Code `b6cd7ef`; evidence [CHECKS.json](evidence/2026-10-30-n8-review-fixes/CHECKS.json); run folder
`GorgonaBookingTests/package-n8-20261030-c59e116` (STATE.md has every run and slip).

| id | Requirement | Result |
|---|---|---|
| N8-01 | Each RN fix has a test that failed before the fix (red run recorded) | PASS: red-1 and red-2 saw the intended defect for every RN (RN-03, RN-06, RN-07 only in red-2; the setup slip is recorded) |
| N8-02 | 0086 upgrade test on PostgreSQL 18; insert-only and RLS unchanged | PASS: `test_n8_upgrade` upgrades a non-empty 0085 database keeping every row |
| N8-03 | The full suite green; one executor, one disposable cluster | PASS in gates-5: static PASS, focused 844 passed, full 2665 passed, 4 skipped. Gates-1..4 failed and are kept: mypy (fixed); Playwright install files vanished (reinstalled on the owner's word); the runner's git call crashed (0xC0000142); `test_i4_browser` "read ECONNRESET" (an existing test, passed alone and in gates-5, cause open) |
| N8-04 | ACCEPTANCE.md corrected with the review closed and its findings listed | PASS: [ACCEPTANCE.md](evidence/2026-10-29-n7-acceptance/ACCEPTANCE.md) |
