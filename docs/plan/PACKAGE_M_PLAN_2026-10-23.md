# Package M — transport (TMS-01..03): plan and decisions (2026-10-23)

**Status: plan; decisions taken by the agent under the owner's full delegation** («Делай как считаешь
нужным и правильным! Я полностью даю тебе право выбора», 2026-10-22; «Делай как считаешь нужным, я доверяю
тебе», 2026-10-23). Branch `codex/package-m-plan` from `e6f0aff` (head of package L). No code yet. Production
stays one common launch of all 39 directions; this package is **build order** for stage 3 (carrier, then the
independent dispatcher, then broker/3PL), not a transport launch.

**One decision needs the owner's word before any code (see decision 1):** adding a `transport` module to the
module registry changes the readiness registry.

## Why this package now

Stage 3 of the master plan is "Beauty and TMS": BEAUTY-01 is complete (package L, acceptance record
L-01..L-12 PASS). The TMS criteria:

| id | Master plan criterion |
|---|---|
| TMS-01 | An interstate trip with several loads and stops, partial delivery and vehicle replacement keeps its history |
| TMS-02 | A dispatcher works only within the scope each carrier granted; revocation and expiry forbid operations |
| TMS-03 | Stale telematics and unknown hours-of-service never give a positive clearance; a repeated event never changes a delivery twice |

The master plan §7.2-7.6 lists the full TMS cycle (order, load card, rate, plan, assignment, checks,
dispatch, pickup, transit, delivery, closing, invoice, settlements, fleet, analytics) and states the model:
**shipment order, load, leg, trip and stop exist separately**, so one trip carries several loads, a load can
be split between trips, partial delivery and transfers between legs are possible, and a driver or vehicle can
change while the history stays. TMS-02 also closes the open dispatcher part of CORE-03 ("independent
businesses in a group or dispatch keep their owners; revoking a grant blocks the next command").

## What exists (inspected 2026-10-23)

- No transport code; the catalog knows the industry "Transportation and logistics" (NAICS 48-49) only as a
  profile choice.
- Shared occupancy (ADR-0022): `resource_allocations` with an exclusion constraint; resources of kinds
  artist, chair, room, equipment, staff; staff reservations of several resources all or none (L-04 proven).
- Cross-company delegation grants (ADR-0017, `business/delegations.py`): the owner business issues terms, the
  servicing business accepts and names delegates; revocation; today delegation covers exactly the booking
  workspace.
- Counterparties, documents, finance (FIN-01..03 invoices, obligations, settlements, credit notes), workforce
  (people, shifts), inventory; module gates (`require_module`, `MODULE_DISABLED`).

## Decisions (agent, under the owner's delegation)

1. **A `transport` module** ("Transport and logistics"), optional, depending on counterparties and
   organization, **registered as not enableable** until its acceptance. *This changes the module registry and
   therefore needs the owner's word before the first code slice.* Without it, the work stays in this plan.
2. **Separate entities, as the master plan says:** shipment order (customer request), load (contents, weight,
   dimensions, requirements, shipper, consignee), leg (a load's movement between two stops), trip (one vehicle
   run with ordered stops) and stop (place, time zone, time window, kind pickup/delivery). A load is placed on
   trips through legs; one trip carries several loads; a load may be split by quantity across legs.
3. **History is never overwritten.** Assignments of driver, truck and trailer to a trip are insert-only
   periods; a replacement closes one period and opens the next. Stop events are insert-only facts.
4. **Vehicles and drivers occupy time in the shared occupancy** (new resource kinds `truck` and `trailer`;
   drivers are workforce people): a trip holds its assigned resources for its planned span; a replacement moves
   the hold atomically (all or none), like L2 stages.
5. **Interstate times are stored in UTC with each stop's own time zone**; windows are checked in the stop's
   zone. Distances and routes come from a connector later; the plan does not invent them.
6. **Events are idempotent facts.** A trip event (arrived, loaded, departed, delivered, partial delivery,
   exception) carries a source event id; a repeat with the same id answers the same fact and changes nothing
   (TMS-03 second half). Partial delivery records delivered quantity per load; the rest stays open.
7. **Clearance is never assumed.** Hours-of-service rules are versioned profiles; telematics and ELD data
   carry source and freshness. A clearance is positive only with fresh, known data; stale or missing data
   gives "not cleared — unknown", never "cleared" (TMS-03 first half). The plan stores no real ELD data;
   tests use FAKE sources.
8. **The dispatcher acts only inside a carrier's grant** (ADR-0017 extended): per carrier, per action
   (assign, dispatch, record events, see documents, see finance), per period and per named delegate;
   revocation or expiry blocks the next command and keeps the audit of earlier actions (TMS-02, CORE-03).
   Broker activity has its own permissions later (FMCSA: the role follows the actual activity).
9. **Money follows FIN-03** (later slices): the customer invoice from the agreed rate, settlements to drivers,
   owner-operators and the dispatch fee as separate obligations with stable ids (§7.5); nothing is paid twice.
10. **Words stay neutral** and US-specific rules (HOS, IFTA) live in versioned profiles, so other countries'
    rules can be added without code changes.

## Slices (each: failing tests first, gates, record, code and docs commits)

| Slice | Content |
|---|---|
| M1 | Module (after the owner's word); shipment orders, loads, stops, legs, trips (migration 0074); company scope and direct SQL refusals |
| M2 | Assignments of driver, truck and trailer with periods; shared occupancy holds; vehicle replacement keeps history; races with observed `pg_locks` waits |
| M3 | Stop events as idempotent facts; partial delivery; a repeated event changes nothing |
| M4 | Dispatcher scope on carrier grants (TMS-02, CORE-03 dispatcher part); revocation and expiry block the next command |
| M5 | Hours-of-service profiles and telematics freshness; clearance never positive on stale or unknown data (TMS-03) |
| M6 | Screens: dispatch board, trip page, stop events, carrier grants; real browser desktop and mobile, keyboard, axe |
| M7 | Money: customer invoice from the agreed rate; settlement obligations per recipient (§7.5) |
| M8 | Acceptance: TMS-01..03, one independent review (owner's consent), record; readiness only on the owner's word |

## Acceptance (all NOT TESTED)

| id | Requirement |
|---|---|
| M-01 | Shipment order, load, leg, trip and stop are separate; one trip carries several loads; a load splits across legs |
| M-02 | An interstate trip keeps each stop's time zone and window; times are stored in UTC |
| M-03 | Replacing the driver, truck or trailer closes one period and opens the next; the old periods stay |
| M-04 | Assignments hold time in the shared occupancy all or none; two racing assignments leave one (observed wait) |
| M-05 | Partial delivery records quantities; the rest stays open; refusal and damage are recorded facts |
| M-06 | A repeated event with the same source id changes nothing |
| M-07 | A dispatcher acts only within the carrier's granted actions, period and delegates; revocation and expiry block the next command; the audit stays |
| M-08 | Stale or missing telematics and unknown hours-of-service never give a positive clearance |
| M-09 | Branch scope, company isolation and finance rights hold for every new table and route (direct SQL refusals) |
| M-10 | Without the transport module each step is refused and writes nothing |
| M-11 | Screens: real browser, desktop and mobile, keyboard and axe; complete pagination |
| M-12 | Full suite, CI, one independent review, regression of BOOKING, FIN-01-03, WORK-01, STOCK-01, BEAUTY-01 |

## Out of scope

Route optimisation and maps, ELD and telematics provider connections (later connectors; tests use FAKE
sources), IFTA reports, fleet maintenance, factoring, the customer and driver portals beyond what the slices
name, and any production or live provider action.
