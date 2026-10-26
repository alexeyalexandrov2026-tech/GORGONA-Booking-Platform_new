# Package N — freight broker and 3PL (stage 3, TMS third contour): plan and decisions (2026-10-26)

**Status: plan; decisions taken by the agent under the owner's full delegation** («Делай как считаешь нужным,
я доверяю тебе», 2026-10-23; «Делай как считаешь нужным я доверяю тебе», 2026-10-24) and the user's
"continue" of 2026-10-26 after package M. Branch `codex/package-n-plan` from `395c775` (package M acceptance).
No code yet. Production stays one common launch of all 39 directions; this package is **build order** for
stage 3 ("carrier, then the independent dispatcher, then broker/3PL"), not a separate launch.

## Why this package now

Stage 3 of the master plan is "Beauty and TMS". BEAUTY-01 is technically verified (owner's word 2026-10-24);
the carrier and the independent dispatcher are package M (technically accepted locally, its independent
review kept open by the owner on 2026-10-26). The broker/3PL contour is the last part of stage 3. Master plan
§7.1 lists "freight broker" and "forwarder and 3PL" as profiles of direction 24; §7.4 ends: "the broker
profile has its own permissions; by FMCSA's clarification, distributing loads among carriers on one's own may
require broker authority; the role follows the actual activity".

## What exists (package M)

Orders, loads, trips, stops, legs; drivers, vehicles and assignments with periods; stop events as idempotent
facts; dispatcher scope on carrier grants; hours-of-service and telematics clearance; the customer's agreed
rate, the order's FIN-03 invoice and pay components accrued as FIN-03 obligations; screens for all of it. A
trip is always run by the business's own fleet: there is no way to hand a load to another carrier.

## Decisions (agent, under the owner's delegation)

1. **Brokerage is an activity, recorded as such.** A business brokers when it places a customer's load with
   another carrier for that carrier's rate. The transport module gains a **broker capability** of the business:
   its broker authority number (US: an FMCSA MC number of the broker type) and its surety bond or trust
   reference, kept as insert-only versions with a source. Without a recorded, current authority the business
   **cannot tender** a load to another carrier (the role follows the activity, master plan §7.4). The platform
   records the facts the business states; it does not certify them (no live FMCSA lookup in this package; a
   connector is a later decision).
2. **Carriers are counterparties with a carrier profile**: authority number, insurance (kind, limit, expiry),
   safety rating, each with its source and the date it was checked. A tender is refused when the carrier's
   authority is missing or the insurance has expired or is unknown — the same rule as TMS-03: unknown is never
   "fine".
3. **A tender places a load (one leg or a whole trip) with one carrier** for a carrier rate (fixed or per
   mile, currency) and terms; it is an insert-only offer with its own id: offered, accepted, declined,
   withdrawn, expired. Accepting produces a **rate confirmation**: a versioned document with the agreed rate and
   terms (the documents of stage 1), never edited afterwards; a change is a new version both sides accept.
4. **A carrier on the platform answers in its own company** (the two companies stay separate, ADR-0017); an
   external carrier's answer is recorded by the broker with its source (email, phone, load board) and time.
   One leg has at most one accepted tender at a time; racing acceptances leave one (observed wait).
5. **The tendered work is tracked with the same stop events** (ADR-0030): the carrier's dispatcher (on the
   platform, through a grant) or the broker records them with their source; a repeated event changes nothing.
6. **Money through FIN-03** (ADR-0033 extended): the customer invoice stays the order's; the carrier's pay is
   one payable obligation per accepted tender (a stable id: broker company, carrier, tender), accrued once
   when the tendered legs are closed; the margin (customer revenue less carrier cost) is shown per order and
   never stored as a second truth. Quick pay and factoring stay later.
7. **Permissions:** `transport.broker` (tender, record carrier answers, carrier profiles) is its own right,
   given to owners and managers, delegable only explicitly; a carrier's dispatcher never gets it by default.
8. **3PL / forwarder** in this package means the same tender flow for multi-leg moves (a load's legs
   tendered to different carriers); warehouse 3PL (receiving, storage, fulfilment) is stage 6, not here.
9. **Words stay neutral**: "broker authority" and "insurance" are stored as typed facts with a jurisdiction,
   so other countries' rules can be added later without code changes.

## Slices (each: failing tests first, gates, record, code and docs commits)

| Slice | Content |
|---|---|
| N1 | Broker capability (authority versions) and carrier profiles (authority, insurance, safety) as facts with source; migration 0080; permission `transport.broker` |
| N2 | Tenders: offer, accept, decline, withdraw, expire; one accepted tender per leg; races; refused without a current broker authority or with an expired or unknown carrier insurance |
| N3 | Rate confirmation documents (versioned; both sides accept a change); a carrier on the platform answers in its own company |
| N4 | Tracking of tendered work with stop events from the carrier's dispatcher or the broker; idempotent |
| N5 | Money: the carrier's payable obligation per accepted tender (FIN-03), accrued once on closed legs; margin per order |
| N6 | Screens: broker board (loads to cover, tenders, carriers), carrier profiles, rate confirmations; real browser desktop and mobile |
| N7 | Acceptance: TMS-01..03 for brokered loads, N-01..N-09, independent review only with the owner's consent; readiness only on the owner's word |

## Acceptance (all NOT TESTED)

| id | Requirement |
|---|---|
| N-01 | A business without a current broker authority cannot tender a load; with one it can |
| N-02 | A carrier with missing authority or expired or unknown insurance is never tendered to |
| N-03 | A tender is an insert-only offer; one leg has at most one accepted tender; two racing acceptances leave one (observed wait) |
| N-04 | Acceptance produces a rate confirmation; a change is a new version both sides accept; old versions stay |
| N-05 | A carrier on the platform answers in its own company; an external carrier's answer is recorded with its source |
| N-06 | Tendered work is tracked with stop events from the carrier side or the broker; a repeat changes nothing |
| N-07 | The carrier's pay is one FIN-03 obligation per accepted tender, accrued once; the margin is computed, never stored twice |
| N-08 | `transport.broker` is its own right; a dispatcher never gets it by default; company scope and direct SQL refusals hold |
| N-09 | Real browser desktop and mobile, keyboard, axe; the full suite stays green |

## Not in this package

Live FMCSA, insurance or load-board connectors (DAT is the first board adapter after access, master plan §7.6);
quick pay and factoring; warehouse 3PL (stage 6); customs and international multimodal moves (stage 8).
