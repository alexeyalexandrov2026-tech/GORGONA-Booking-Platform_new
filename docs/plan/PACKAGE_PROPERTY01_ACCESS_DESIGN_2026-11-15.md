# PROPERTY-01 · 7a · Access boundaries of every Property route

Step 7 of the [PROPERTY-01 plan](PACKAGE_PROPERTY01_PLAN_2026-11-14.md) requires that each role is
checked on its own, and that a request from another company or after the permission is revoked is
refused. Steps 4–6 and the tenant and owner portals need new tables or owner decisions. This slice
checks the routes that exist now. It changes no schema, API or screen.

## Matrix

`test_property_access.py` builds one unit in the home branch with a listing, a showing, a
registered lease and its move-in report through the normal API. It then calls all 19
authenticated routes under `/v1/businesses/{business_id}/property` with real tokens and valid
bodies. Six are reads under `property.read`: objects, listings and showings, each as list and
item. Thirteen need `property.manage`: histories, writes, cancellation, and all lease, term and
move-in routes. A coverage check compares the matrix with the application's OpenAPI paths, so a
new Property route fails the test until it is classified.

| Caller | Expected |
|---|---|
| Company-wide manager | Every read answers 200 |
| Another company's manager | 403 on all 19, nothing written |
| `artist` or `front_desk` of the company | 403 on all 19, nothing written |
| Platform support without membership | 403 on all 19, nothing written |
| Manager of the home branch | 200 on the six reads, 403 on the thirteen others |
| Manager of another branch | Lists are empty, the three items 404, the thirteen others 403 |
| Suspended company manager | 403 on all 19, and a replay of the member's earlier key is refused |
| Reactivated manager | The replay returns the original answer, reads answer 200 |
| Revoked manager | 403 on all 19, the replay is refused, reactivation answers 409 |

"Nothing written" compares the row counts of the eleven Property tables before and after the
refused calls. After revocation the listing history still names the revoked member as the author
of the revision they made. Delegation is not exercised: `DELEGABLE_PERMISSIONS` is pinned by
`test_delegation_contracts.py` and holds no Property permission.

## Not in this slice

Tenant, owner and contractor access with an explicit term and revocation needs a grant model and
migration 0118. Owner changes that keep earlier obligations need step 4. Both remain in the plan.
