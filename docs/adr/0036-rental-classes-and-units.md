# ADR-0036: Rental module, item classes and units

Status: accepted for package R slice R1 (2026-11-03). Taken by the agent after the owner's "continue", relayed by
the starting session with the instruction to start R1 of RENT-01; the module is registered as `implemented` and
**not enableable**, so no business can use it before acceptance and the owner's word.

## Context

Stage 4 of the master plan continues with RENT-01: "A class booking is separate from the assignment of a unit; a
double issue is impossible; the payment security, damage and refund are recorded separately." Package R's plan is
`docs/plan/PACKAGE_RENT_PLAN_2026-11-03.md`. It serves direction 23 (cars, trucks, equipment, tools, boats,
clothing, inventory, self storage) with one module. The first slice needs what every booking and assignment hangs
on: the class a customer books and the physical units that can be given out.

## Decision

1. **Module.** A new optional module `rental` ("Rental and hire"), depending on `counterparties` and
   `finance_documents` (agreements and settlement go through FIN-03 later). Registered as `implemented`; it
   **cannot be enabled** until acceptance (ADR-0020). `MODULE_REGISTRY_VERSION` becomes 6 (ADR-0019). Writes are
   gated by `gba.require_enabled_module('rental')` and the early module check; reads are not gated.
2. **Permissions.** `rental.read`, `rental.manage` and `rental.approve` (damage charges and security releases, used
   from R5); owners and managers hold all three; permissions version 12. Nothing of rental is delegable in R1.
3. **Class.** A class has a code unique in the business, a name, a meter kind (none, odometer, hours) and a typed
   attribute set (key, label, type text, number or boolean, required or not), replaced whole with its expected
   revision; each revision writes its full attribute set insert-only. A class is company-wide: a branch-limited
   member reads classes but does not write them.
4. **Unit.** A unit is one physical item of a class with an identifier unique in the business (VIN, serial, plate
   or label), a branch, a state (active or retired; retired is final) and values for the class attributes, replaced
   whole with its expected revision; each revision writes its values insert-only. The class and the identifier of a
   unit are fixed. The database checks each value against the class's latest attribute set (known key, type) and,
   at commit, that every required attribute has a value. A branch-limited member sees and writes only its branch's
   units.
5. **Occupancy.** A unit becomes a resource of the shared occupancy model (ADR-0022) in R3, when units are first
   assigned; R1 stores no occupancy.

## Consequences

Classes and units are the catalogue of every later slice. Values are stored as text with their declared type
checked in the database, so a later attribute type needs a new migration. Moving a unit between branches in R1 is a
plain revision; recorded moves with transit occupancy come with R3.
