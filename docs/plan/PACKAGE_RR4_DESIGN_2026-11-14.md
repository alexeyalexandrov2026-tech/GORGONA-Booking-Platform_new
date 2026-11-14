# RR-08 — whole-period feasibility for rental class bookings

Owner decision: confirm only when one unit can serve each booking for its entire interval. Keep the
unit choice provisional until an assignment is recorded. No new occupancy source or provisional
allocation row.

Use active units in the pickup branch and current bookings with half-open periods. Existing current
assignments pin the unit. Maintenance blocks restrict available units across each entire booking.
Find a compatible allocation of the still-unassigned bookings, with backtracking when a greedy
selection would reject a feasible plan. Include the transitive overlap group. Keep the existing peak
check as a cheap necessary bound. Do not treat an exhausted search budget as a confirmed capacity
shortage. The authority check runs under the class lock and must also guard mutations to blocks,
assignments, booking periods and unit capacity. Cancellations and block releases only restore
capacity. Availability should expose feasible whole-period capacity, with the existing peak figure
retained for context.

Acceptance cases: alternating blocks; two feasible bookings where greedy ordering fails; adjacent
periods; a new reservation, extension, pinned assignment, unit move or maintenance block that would
strand an accepted booking; availability on the exact same interval as a booking command; observed
PostgreSQL lock waits for concurrent capacity changes. Benchmark before completion.

Implementation notes. Use half-open overlap groups found by ordering periods and breaking when the
next start meets the maximum end of preceding intervals. Pin existing assignments and remove units
whose block overlaps any portion of each candidate booking. Search assignments in order of fewest
eligible units. Iterate with an explicit stack, so large fleets do not use database call-stack depth.
Keep the fast peak rejection. Bound pathological search by returning a distinct retryable database
error if it cannot be resolved inside the search budget. Benchmark the bound and the common case.
Guard existing mutations with named SQL checks, defer checks for compound assignment and period
writes until their final state is visible, and flush them inside the existing error mapping.
