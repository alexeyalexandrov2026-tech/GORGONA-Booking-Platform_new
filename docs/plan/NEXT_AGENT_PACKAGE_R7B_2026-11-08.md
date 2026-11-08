# Handoff — package R after R7a; next is R7b (2026-11-08)

Read [NEXT_AGENT_PACKAGE_R7_2026-11-07.md](NEXT_AGENT_PACKAGE_R7_2026-11-07.md) and [PACKAGE_R7A_DESIGN_2026-11-07.md](PACKAGE_R7A_DESIGN_2026-11-07.md)
first; same delegation and process.

| Slice | Branch | Design | Code | Docs | Migration | CI |
|---|---|---|---|---|---|---|
| R6b | `codex/package-r6b-rental-usage` | `af3f01f` | `010692f` | `0432c98` | none | run 42438106172 success |
| R7a | `codex/package-r7a-rental-settlement` | `5f968b9` | `31cf73d` | the docs commit with this file | 0106 | pushed with this commit; check it first |

Next migration **0107**. Run folder `C:/Users/alexa/AppData/Local/GorgonaBookingTests/package-r7a-20261107-5f968b9` (`adapt_r7a_record.py`).

Next: **R7b** damage charges with `rental.approve` and a return inspection (its new damage marks) as their basis, written
as their own FIN-03 receivable invoice draft and linked like the settlement; refunds as their own records (a FIN-03
credit note against the settlement or damage invoice, or a recorded external refund). Then **R7c** the
reconciliation per agreement (charged, paid, security held, captured and released, damage charged and refunded, all
derived). A capture of security never edits a charge and a charge never edits the security (rental plan decision 5).

Pattern: the business record and its FIN-03 draft are written in one request; add each new linking table to
`financial_documents._linked_to_visit`. Test books are in USD (`test_stock.entity_with_book`), so test cards use USD.
