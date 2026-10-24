# ADR-0031: An independent dispatcher works within each carrier's grant

Status: accepted for package M slice M4 (2026-10-24), under the owner's word for package M (2026-10-23):
«Да, добавь модуль «Транспорт и логистика» в реестр модулей как невключаемый до приёмки и начинай пакет M с первого
среза. Готовность BEAUTY-01 и main пока не трогай.» User 2026-10-24: "Continue with M4 the same way." Extends
[ADR-0017](0017-cross-company-delegation.md) (cross-company delegation) to transport (ADR-0028..0030).

## Context

TMS-02: "a dispatcher works only within the scope each carrier granted; revocation and expiry forbid
operations". It also closes the dispatcher part of CORE-03. ADR-0017 already gives two-sided, versioned,
expiring grants with named delegates, a check of both accounts on every request, effective permission = grant
∩ servicer role, location scope, per-request audit and refusal of old receipts after revocation. It deliberately
limited grants to the booking workspace and named "multi-carrier dispatcher workflows" as the next user.

## Decision

1. **Transport rights split by action**, so a carrier can grant exactly what a dispatcher does:
   `transport.read` (see orders, trips, drivers and vehicles), `transport.plan` (orders and trips),
   `transport.assign` (assign, replace and end drivers, trucks and trailers) and `transport.events` (record
   stop events). `transport.manage` now means only registering drivers and vehicles; it is **never delegable**.
   Owners and managers hold all of them; permissions version 9.
2. **Delegable set grows** from the four booking rights to those plus the four transport rights; a grant names
   1 to 8 of them. The database check, the API contract and the web contract change together. Effective
   permission stays grant ∩ the delegate's own role in the servicing company, so only servicer members whose
   role holds a transport right can use it (owners and managers today).
3. **Transport routes opt in** to the delegated path (`allow_delegation`, already location-scoped), except
   driver and vehicle registration. Everything else of ADR-0017 applies unchanged: both accounts locked per
   request, the owner's suspension is not bypassed, a location-limited grant becomes the branch scope, a
   `delegation.access` audit row names the executor, the servicer company, the grant and the permission, and
   authorization runs before idempotency so a replay after revocation reveals nothing.
4. **History stays.** Assignments, their ends and stop events already record the executing user; revocation or
   expiry blocks the next command and never removes earlier facts.
5. **One grant per carrier.** A dispatcher company serving several carriers holds one grant from each; every
   request is decided by the grant of the business it addresses, so rights never carry over between carriers.

## Consequences

The web workspace still shows delegated businesses with booking navigation; transport screens and a dispatcher
board arrive in M6. Broker activity (FMCSA: the role follows the activity) gets its own rights later.
