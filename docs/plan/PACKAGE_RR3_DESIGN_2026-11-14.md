# Package R review fixes — rental history and provider intent

RR-07 and RR-09, based on 38009c2. Migration 0110.

- Handover records the class meter kind. Return and usage use that historical context.
  For earlier inspections, the stored meter reading establishes whether a meter was used.
  Legacy data cannot always distinguish odometer and hours, and no historical readings are rewritten.
- Changed terms are refused after settlement. Usage reads the settlement's recorded agreement
  version when present. Agreement edits and settlement serialize on the existing class lock.
- Links for the same sandbox intent are serialized within a tenant, across classes and branches.
  Scope checks and the provider evidence contract retain their existing behavior.

Verification pending. RR-08 remains a separate allocation-policy decision.
