# Package R — rental (stage 4, RENT-01): plan and proposed decisions (2026-11-03)

**Status: plan, proposed by the agent; not started.** The owner's word "continue" was relayed by the starting
session with the instruction to prepare the plan of the next package, RENT-01, while the O7b gates ran. Production
stays one common launch of all 39 directions (master plan §13); this package is **build order** for stage 4
(master plan: "4. Construction and rental", acceptance RENT-01), not a separate launch. It serves direction 23
"Rent and hire" (cars, trucks, equipment, tools, boats, clothing, inventory, self storage) with one module whose
items carry their own attributes (master plan §9.1). Real estate (PROPERTY-01, §9.2) is the next package.

RENT-01: "A class booking is separate from the assignment of a unit; a double issue is impossible; the payment
security, damage and refund are recorded separately."

## What exists and is reused

Counterparties (customers, drivers and other users of the item); stage-1 documents and versioned files (signed
agreements, inspection photos); branches with their time zones and rights; **shared resource occupancy** (ADR-0022:
exclusion constraints that make two overlapping occupations of one resource impossible in the database); FIN-03
invoices, manual accruals, obligations, external payments and credit notes; the payment provider in sandbox only.
Rental adds no second ledger and no second occupancy model.

## Proposed decisions (to be confirmed before R1)

1. **A new module `rental`** ("Rental and hire"), `implemented` and **not enableable** until acceptance and the
   owner's word, as `transport` and `construction`. It depends on `counterparties` and `finance_documents`.
   Permissions `rental.read`, `rental.manage` and `rental.approve` (damage charges, waivers and releases of
   security above the rule; owners and managers by default).
2. **Item classes and units.** A class (for example "compact car", "excavator 5 t", "kayak", "suit size 50", "storage
   unit 3x3") has attributes from a typed, versioned attribute set per class, a meter kind (none, odometer, hours,
   fuel level) and a home branch. A unit is one physical item of a class with its identifier (VIN, serial, plate or
   label), its branch and its state; a unit is a resource in the shared occupancy model.
3. **A class booking is not a unit.** A booking holds a class for a period with a pickup branch and a return branch.
   It is accepted only while the units of the class that can be at the pickup branch, minus the bookings and
   occupations that overlap, stay at or above zero; the check runs under a lock per class and branch, and two racing
   bookings for the last unit leave one (observed `pg_locks` wait). **Assigning a unit** to a booking is a separate,
   insert-only fact that occupies the unit for the period (ADR-0022 exclusion); a replacement unit is a new
   assignment that ends the earlier one. A double issue of one unit is impossible in the database.
4. **Rates** are versioned rate cards per class and branch: per hour, day, week and month, with long-term rules,
   extras (additional drivers, equipment, insurance products recorded as plain extras), included meter allowance and
   the excess rate. A quote is derived from the rate card in force at the booking; the **agreement** is the accepted
   quote, frozen, with who accepted it, the source (platform, paper, email) and the time; an optional signed copy is a
   document version. An extension or a change is a new insert-only version checked against occupancy.
5. **Security of payment has its own states**, never mixed with charges: requested, held (a provider hold in sandbox
   or a recorded external hold), captured (partly or fully, with a basis), released, expired. A **damage charge** is a
   separate obligation with its basis (a return inspection and its evidence), approved by `rental.approve`; a
   **refund** is a FIN-03 credit or external refund with its own record. Capturing security never edits a charge and
   a charge never edits the security.
6. **Handover and return** are inspections: checklist items with states, meter readings (odometer, hours, fuel),
   damage marks with photos (document versions), the person and the time. Handover opens the actual use; return
   closes it; overdue and excess meter use are derived. A unit returns to another branch only when the agreement
   allows it; its location then changes by a recorded move.
7. **Unavailability**: maintenance, repair and blocks occupy the unit with a reason, so no booking assignment can
   overlap them; a unit moved between branches is occupied in transit.
8. **Final settlement**: one FIN-03 invoice for the agreement from the frozen rates and the recorded use (days,
   extras, excess meter, late return, fuel), credit notes for corrections; the reconciliation per agreement shows
   charged, paid, security held, captured and released, damage charged and refunded, all derived.
9. **Customers on the platform** answer (accept a quote, sign, report a problem) only through a grant; otherwise the
   business records the answer with its source, as in packages N and O.
10. **Time and money**: periods are instants in UTC shown in the branch time zone; money in minor units of the
    agreement currency; one currency per agreement.

## Slices (each: design, failing tests first, gates on the VM, record, code and docs commits, push for CI)

| Slice | Content |
|---|---|
| R1 | Module `rental` (implemented, not enableable), permissions; classes with typed attributes; units as occupancy resources; ADR-0036 |
| R2 | Class bookings with the availability check per class and branch; races on the last unit |
| R3 | Unit assignment and replacement on the shared occupancy (no double issue); maintenance and blocks; moves between branches |
| R4 | Rate cards, quotes and the frozen agreement; extensions and changes as versions |
| R5 | Security of payment states (sandbox or external holds), separate from charges |
| R6 | Handover and return inspections, meters, photos, damage marks; overdue and excess derived |
| R7 | Final settlement through FIN-03, damage charges with approval, refunds; reconciliation per agreement |
| R8 | Screens (catalogue, availability board, booking, agreement, handover, return, settlement); real browser desktop and mobile |
| R9 | Acceptance of RENT-01 and R-01..R-10; independent review only with the owner's consent; readiness on the owner's word |

## Acceptance (all NOT TESTED)

| id | Requirement |
|---|---|
| R-01 | The module cannot be enabled before acceptance; every route refuses when it is off; company and branch scope and direct SQL refusals hold |
| R-02 | A class booking holds no unit; availability per class and branch is derived; two racing bookings for the last unit leave one with an observed wait |
| R-03 | A unit is assigned at most once over any instant (database exclusion); maintenance and blocks exclude assignment; replacement keeps history |
| R-04 | Rate cards are versioned; the agreement freezes the accepted quote; an extension is a new version checked against occupancy |
| R-05 | Security states are separate from charges; capture and release are recorded once with a basis |
| R-06 | Handover and return inspections record meters, damage and photos; overdue and excess are derived |
| R-07 | A damage charge needs `rental.approve` and a return inspection as its basis; a refund is its own record |
| R-08 | The final invoice is derived from the frozen rates and the recorded use; the reconciliation per agreement derives every figure |
| R-09 | Customers on the platform answer only through a grant; otherwise the source is recorded |
| R-10 | Real browser desktop and mobile, keyboard, axe; the full suite stays green |

## Not in this package

Live payment providers and live card holds (sandbox only); telematics and live vehicle data; insurance providers;
jurisdiction-specific rental contracts and tax forms (to be checked against current authoritative sources before
any claim); real estate (PROPERTY-01); dynamic pricing. Readiness of `rental`, enabling it and `main`: only on the
owner's word.
