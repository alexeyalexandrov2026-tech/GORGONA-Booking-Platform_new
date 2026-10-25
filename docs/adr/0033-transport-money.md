# ADR-0033: Transport money goes through FIN-03, one obligation per recipient and component

Status: accepted for package M slice M7a (2026-10-25), under the owner's word for package M (2026-10-23) and
the user's 2026-10-25 "Continue with M7 the same way." Builds on ADR-0028..0032 and FIN-03 (invoices,
obligations, settlements, credit notes); package M's plan, decision 9; master plan §7.5.

## Context

Master plan §7.5: agreed formulas (a fixed amount, per mile, a percentage of an agreed base, extras, the
dispatch fee); every obligation to a recipient has a stable identity (owner company, recipient, source,
component), so a driver's pay and the dispatch fee for one trip are different obligations; nothing is reserved
or paid beyond an obligation's open balance, a repeat never pays twice, and a change of amount is a linked
correction, never a new original accrual. FIN-03 already gives receivable and payable documents, obligations
with their open balance, atomic reservation and confirmed payment, and credit notes. Package L used it for the
visit invoice (L4) and the commission accrual (L5).

## Decision

1. **The customer's agreed rate belongs to the order** and is kept as insert-only versions replaced with the
   expected revision: a currency and either a fixed amount for the order or an amount per mile. Once the order
   is invoiced its rate never changes; a change after that is a FIN-03 credit note.
2. **One customer invoice per order**, a FIN-03 receivable draft linked to the order once: a freight line from
   the rate (fixed, or per mile × billed miles rounded half up to the currency's minor units) and up to 20
   named extra lines (detention, lumper, …), each to a named account. The order is billable only when every
   load is fully planned and no leg carrying its loads has an open quantity (delivered, refused or damaged
   closes it). Issuing and payment are FIN-03's own routes.
3. **Pay components are stable obligations' sources.** A trip's component has its own id, a recipient
   counterparty, a role (`driver`, `owner_operator`, `dispatch_fee`, `other`), a currency and a formula: a fixed
   amount, an amount per mile, or a percentage of an agreed base amount. It is registered once with fixed
   details (like the fleet, ADR-0029); one recipient has at most one component per role on a trip.
4. **One accrual per component**, a FIN-03 payable manual accrual linked to the component once, only when the
   trip has no open leg quantity; a per-mile component takes the billed miles with the accrual. Different
   components are different obligations; FIN-03 settlements keep every payment within the open balance, and a
   repeated command answers the same accrual. Corrections are FIN-03 credit notes on the accrual.
5. **Money is a company-wide finance task:** writes need `finance.manage`, reads `finance.read`, never a
   delegate (a carrier's dispatcher keeps the transport actions of ADR-0031 only). Invoice and accrual run
   under the ledger lock like L4 and L5; the transport and finance modules must be enabled.
6. **Branch scope:** order money is company-wide like orders; trip components and accruals follow their trip's
   branch.

## Consequences

Advances, deductions, fuel surcharges as formulas, factoring and quick pay stay later (their own decisions);
extras are named lines today. Pay and invoices appear on the screens in M7b.
