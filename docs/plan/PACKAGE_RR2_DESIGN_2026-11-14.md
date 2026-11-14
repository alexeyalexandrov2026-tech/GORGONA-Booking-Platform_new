# Package R review fixes — refunds and linked financial drafts

RR-05, RR-06 and RR-10, based on RR1 at 254a1ed.

- Rental reconciliation reports a voided credit and preserves its original amount and number.
  A void releases both the overall refund quota and the amount reserved against invoice lines.
  Each active credit consumes its allocation once, even after issue creates another version.
- A linked settlement, damage invoice or refund credit cannot acquire another draft revision.
  Ordinary draft edits and FIN-03 issue and void transitions retain their behavior.
- The damage record preserves the complete reason. Its FIN-03 line uses the charge number.
- Migration 0109 preserves history. RR-07 meter and settlement changes follow separately.

Verification pending.
