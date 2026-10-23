# Package L9 — closing the two BEAUTY-01 gaps (2026-10-23)

Owner's word 2026-10-23: «Доделай оба пробела BEAUTY-01 (правила платы за отмену и неявку, отмена комиссии
после возврата) тем же порядком работы. Готовность и main пока не трогай.» Same process as package L: design,
failing tests first, one executor and one disposable PostgreSQL 18 cluster per run, gates, a source-bound record,
push for CI only. Readiness and `main` are not touched. Words stay neutral: visit, service, specialist, fee.

Gaps from the [acceptance record](evidence/2026-10-23-l8c-acceptance/ACCEPTANCE.md):

- **L-06:** cancellation and no-show lines are named by a finance user, not computed from a published policy.
- **L-07:** a refund does not reverse the commission.

## Slices

| Slice | Content |
|---|---|
| L9a | Versioned fee policy (migration 0072), no-show fact, billing computes the late-cancellation and no-show fee, settings form and a desk step |
| L9b | Commission reversal after a refund (migration 0073), computed per service line, once, with lineage; desk step |
| L9c | Acceptance record updated: L-06 and L-07 re-checked |

## L9a decisions

76. **A fee policy is published in versions.** `gba.visit_fee_policies` keeps insert-only versions per business:
    free cancellation minutes before the start (0 to 525600), a late-cancellation fee and a no-show fee, each
    either a percentage (basis points, 0 to 10000) of the visit's priced total or a fixed amount in hundredths
    of the main currency unit (as catalog prices), or none. A new version needs the expected current version
    (0 for the first); a stale one is a conflict. Publishing needs settings rights; reading needs booking read.
77. **The version in force when the visit was booked applies.** The latest version published at or before the
    booking's creation; none means no fee. A later version never changes an older visit.
78. **A no-show is a recorded fact.** `gba.visit_no_shows` records once that a confirmed visit whose start has
    passed did not happen, with the version that applies. It needs booking write rights like a completion.
    A completed visit cannot be a no-show and a no-show cannot be completed; a no-show visit cannot be moved
    or cancelled (as a recorded visit, L8 decision 60).
79. **Billing follows the policy.** A cancelled visit (not cancelled by its own reschedule) is billed one line,
    "Late cancellation fee", when it was cancelled later than the free window and the version has that fee; a
    no-show visit is billed one line, "No-show fee". A percentage rounds half up to the currency's minor units;
    a fixed amount converts exactly (L8 decision 55). Without a fee under the policy the visit is not billable.
    Fee lines typed by a user are accepted only on a confirmed, attended visit (other fees); on a cancelled or
    no-show visit they are refused (`VISIT_FEE_FROM_POLICY`). The fee line uses the revenue account named for
    the invoice. The cancellation time is the booking's own status event.
80. **Screens.** Settings show the current fee policy and publish a new version; the visit desk offers "Mark as
    no-show" for a confirmed visit after its start with no completion, and then shows the fee that applies.

| id | Requirement (L9a, PASS locally in `8a90567`) |
|---|---|
| L9-01 | Versions are insert-only; a stale version is refused; another company sees none |
| L9-02 | A visit uses the version in force when it was booked; a later version does not change it |
| L9-03 | A late cancellation is billed its fee (percentage and fixed, 0-, 2- and 3-decimal currencies); an early one, a rescheduled one or one without a fee is not billable |
| L9-04 | A no-show is recorded once, only after the start and without completion; it is billed its fee; completion, reschedule and cancel are refused |
| L9-05 | Typed fee lines on a cancelled or no-show visit are refused; on an attended visit they still work |
| L9-06 | Settings form and desk step in a real browser, desktop and mobile, keyboard, axe |

## L9b decisions

81. **A refund is an issued credit note on the visit invoice that is not a prepaid redemption.** Its lines
    name the invoice lines they reduce; only service lines change the commission (fees and tips do not).
82. **The reversal is computed, once per refund, with lineage.** For every commission line the cumulative
    reversal is the line times the refunded share of its service (the service line and its add-ons), half up;
    the new reversal is that target minus what was already reversed. It is one FIN-03 credit note on the
    commission accrual, issued at once, recorded in `gba.visit_commission_reversals` (one row per refund, also
    when nothing is to reverse). A finance user starts it; the server computes every amount. The accrual must
    be issued first (`VISIT_COMMISSION_NOT_ISSUED`); a part already paid to the payee becomes FIN-03's refund
    obligation and needs its control account. Accrual lines are matched to services in quote order by name.
83. **Read and screen.** The commission read shows the reversals and the amount still to reverse; the desk
    offers "Reverse commission" when a refund is not yet reversed.
84. **Once under a race.** Two reversals of one visit leave one, after an observed `pg_locks` wait.
85. **A redemption settles; a refund is reversed (found while writing the L9b tests).** L5 refused a commission
    on any credited visit invoice ("handled by hand"), so a visit settled by a prepaid unit never earned its
    specialist's commission. The accrual now counts prepaid redemption credits as settlement; a refund credit no
    longer blocks it either: the accrual follows the quote and the refund is reversed by decision 82 (the read
    shows the amount to reverse at once).

| id | Requirement (L9b, NOT TESTED) |
|---|---|
| L9-07 | A full refund reverses the whole commission; a partial refund of one service reverses only its share |
| L9-08 | Two refunds reverse cumulatively without drift; a refund of fees only records a zero reversal |
| L9-09 | A redemption credit is not a refund; a draft accrual is refused; a paid accrual needs the refund account |
| L9-10 | Two racing reversals leave one after an observed wait; lineage rows are permanent and company scoped |
| L9-12 | A visit settled by a prepaid unit and a payment earns its commission; a refund before the accrual is reversed after it |
| L9-11 | Desk step in a real browser, desktop and mobile, keyboard, axe |

## Limits named now

- The cancellation time is taken from the booking's status event; a voided refund after its reversal is not
  re-reversed automatically (the void stays a FIN-03 decision and is visible in the lineage).
- The customer site keeps showing the business's own policy text; the structured fee is shown in settings and
  on the desk.
