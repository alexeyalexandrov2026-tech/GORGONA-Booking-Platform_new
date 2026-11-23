# ADR-0045: Staffing, Advisory, Organizations and Public Administration (SPECIAL-04)

- Status: Accepted (implemented, not enableable until jurisdictional acceptance and the owner's word)
- Date: 2026-11-21
- Stage: Stage 8 (Specialized industries: profiles 30, 31, 36, 39)
- Migration: `0148_special_staffing_advisory_orgs_public.sql`

## Context

Master plan §3 defines the remaining four specialized profiles completing 39/39 coverage:
- 30: Finance and insurance advisory
- 31: Staffing and recruiting
- 36: Organizations and associations (memberships, funds, grants)
- 39: Public and municipal administration (citizen service cases, permits)

All four require structured programs, counterparty-linked case workflows with optional
four-eyes (dual-review) governance, approved allocations (placements, mandates, awards,
permits), and immutable insert-only compliance/transparency audit records.

## Decision

1. Register optional module `public_civic` (`Readiness.IMPLEMENTED`, `enableable=False`,
   `MODULE_REGISTRY_VERSION = 16`, `len(MODULES) = 28`, depends on `counterparties`).
2. Add permissions `civic.read`, `civic.work`, `civic.manage` (`PERMISSIONS_VERSION = 25`,
   not delegated).
3. Add four branch-scoped, RLS-protected, module-gated tables in `0148`:
   `gba.civic_programs`, `gba.civic_cases`, `gba.civic_allocations`, and
   `gba.civic_audit_events` (insert-only).
4. Enforce server-side governance invariants:
   - Programs with `requires_dual_review = true` reject self-approval (`CIVIC_DUAL_REVIEW_REQUIRED`)
     when `decided_by == case.recorded_by`.
   - Allocations (placements, mandates, awards, permits) require an `approved` parent case
     (`CIVIC_CASE_NOT_APPROVED`).
   - Closed programs reject new cases; rejected/closed cases cannot be reopened.
