# ADR-0034: Broker authority and carrier profiles are dated facts; unknown is never eligible

Status: accepted for package N slice N1 (2026-10-26), under the owner's full delegation and the user's
"Continue with N1 the same way." (2026-10-26). Builds on ADR-0028 (transport module) and ADR-0032 (clearance
never positive on stale or unknown data); package N's plan, decisions 1, 2 and 7.

## Context

Master plan §7.4: "the broker profile has its own permissions; distributing loads among carriers on one's own
may require broker authority; the role follows the actual activity" (FMCSA). Package N lets a business place a
customer's load with another carrier (N2). Before that, the business's own broker authority and each carrier's
authority, insurance and safety rating must be recorded, with where each fact came from and when it was
checked, and the platform must never treat a missing, expired or stale fact as fine.

## Decision

1. **Broker authority** of a business: insert-only versions replaced with the expected revision — a
   jurisdiction (`US` today), the authority number, the surety bond or trust reference, a status (`active` or
   `withdrawn`), the date it takes effect, an optional expiry, the source of the statement and the date it was
   last checked. The platform records what the business states; it does not certify it (no live FMCSA lookup).
2. **Carrier profile** of a counterparty: insert-only versions with the expected revision — jurisdiction,
   authority number (may be unknown), liability and cargo insurance expiry dates (each may be unknown), a safety
   rating (`satisfactory`, `conditional`, `unsatisfactory`, `unrated`), source and check date.
3. **Eligibility is computed for a date, never stored.** A broker may tender on a date only with an active,
   effective, unexpired authority checked within the last 90 days. A carrier is eligible on a date only with a
   known authority, liability and cargo insurance known and unexpired, a rating other than `unsatisfactory`,
   and a check within the last 90 days. Every failing condition is a named reason; no profile is a reason too.
4. **`transport.broker`** is a new right of owners and managers (permissions version 10), needed to read and
   write broker authority and carrier profiles. In N1 it is **not delegable** (the plan's "delegable only
   explicitly" waits for N2, where tendering exists; widening the grant check then is its own change). A
   carrier's dispatcher never has it.
5. Company-wide (no branch), tenant isolation, the transport module gate, select and insert only.

## Consequences

N2 refuses a tender unless both the broker and the carrier are eligible on the tender's date. The 90-day check
window is a constant today; per-jurisdiction rules can become versioned profiles later.
