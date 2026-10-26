# Package M — fixes from the independent review (2026-10-26)

User 2026-10-26: "Да: проведи одну независимую проверку пакета M одним дополнительным агентом, исправь находки,
затем предложи обновление main." One extra read-only agent reviewed `ad21888..395c775` (M6a..M8; M1..M5 where M7
depends on them). Each finding below was checked against the code before it was accepted. Branch
`codex/package-m-review-fixes` from `89fae0e` (N1 docs). Migration **0081**.

## Findings and decisions

| id | Severity | Finding (verified) | Decision |
|---|---|---|---|
| R-01 | high | A transport order invoice or pay accrual draft can be edited through the generic FIN-03 draft routes: the freeze checks only visit invoices, commissions and prepaid sales (`financial_documents._linked_to_visit`). | The freeze also covers `transport_order_invoices` and `transport_pay_accruals`; FIN-03 refuses with `FINANCIAL_DOCUMENT_LINKED` (409). |
| R-02 | high | A leg loaded below plan never closes: open is planned − resolved, while resolved can never exceed loaded and a started trip cannot be re-planned. The order is never billable and the trip's pay never accrues. Contradicts ADR-0030 decision 3. | Loading is final once the trip has **departed the leg's pickup stop**: from then on open = loaded − resolved; before, open = planned − resolved (unchanged). Same rule on the trip page. ADR-0030 amended. |
| R-03 | medium | After the order invoice exists, the order's loads can still be added, enlarged or restored and carried unbilled. | Migration 0081: a trigger on loads (an insert, or an update of quantity, removal or order) refuses under the order's rate lock once the order is invoiced (a new leg needs more load, since an invoiced order is fully planned and resolved); the API answers `TRANSPORT_ORDER_INVOICED` (409). ADR-0033 amended. |
| R-04 | medium | The trip edit form rebuilds each stop window from the start date and the end's clock time: a window over 24 h is cut, a zero-length window becomes 24 h, and an overnight window across a DST change is off by an hour. | The form keeps an end date per stop and converts it with the business zone (`businessTimeToInstant`). |
| R-05 | low | A huge per-mile product returns 500 (pydantic `ValidationError` inside the service). | Bound the computed amount; refuse with 422 `TRANSPORT_AMOUNT_TOO_LARGE`. |
| R-06 | low | A fixed rate, an extra line and a fixed pay amount accept 3 decimals and are silently rounded. | Refuse an amount with more decimals than the currency's minor units (422); per-mile and percent rates keep their precision. |
| R-07 | low | Any unique violation on a pay component is reported as "recipient already has this component", even a concurrent identical retry on the component's own id. | On the primary-key clash reload and compare; identical → the stored component (200), different → 409. |
| R-08 | low | Docs contradict code: M7a-06 says nothing is read with the module off, but reads continue (the module registry's rule); the module description still says "no … money yet". | Correct M7a-06 in the M7a record (reads continue, writes refused, as for every module) and the module description. No behaviour change. |
| R-09 | low | The grant form offers "Plan trips" although a delegate cannot plan on the screen. | The option is labelled "Plan trips (API only)". |

## Acceptance (NOT TESTED)

| id | Requirement |
|---|---|
| RF-01 | FIN-03 refuses to edit a transport order invoice draft and a pay accrual draft (409 `FINANCIAL_DOCUMENT_LINKED`) |
| RF-02 | A leg planned for 10, loaded 8, departed and delivered 8 is closed: the order is invoiced and the trip's pay accrues; before departure the same leg is still open |
| RF-03 | Once invoiced, adding, enlarging or removing a load is refused (409); editing anything else on the order still works; upgrade 0080 → 0081 keeps every row |
| RF-04 | Editing a trip keeps a two-day window, a zero-length window and an overnight window across the 2026-11-01 DST change exactly |
| RF-05 | A per-mile product beyond the limit is refused with 422, not 500 |
| RF-06 | A fixed amount with more decimals than the currency allows is refused with 422 |
| RF-07 | A concurrent identical pay component under a new key returns the stored component; a different one is 409 |
| RF-08 | The full suite stays green |
