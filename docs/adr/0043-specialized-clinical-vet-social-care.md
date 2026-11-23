# ADR-0043: Qualified Clinical, Veterinary & Social Care Workflows (SPECIAL-02)

- Status: Proposed (implemented behind `clinical_care` module `enableable=False` until jurisdictional acceptance)
- Date: 2026-11-21
- Stage 8 Profiles Covered: `14 healthcare`, `15 animal_services`, `16 social_care`

## Context
Master Plan §10 and §12.5 require qualified clinical, veterinary, and social care modules with strict consent management and sensitive-record protection:
- Patients, animals, and care recipients are modeled explicitly with owner/guardian counterparty links.
- Recording care plans and clinical encounters requires an **active, unrevoked consent** (`care_consents`).
- Revoking consent immediately blocks new encounters/plans (`409 CARE_CONSENT_REQUIRED`) and redacts sensitive `clinical_notes` on read-back while preserving immutable audit history.

## Decision
Implement `SPECIAL-02` behind optional module `clinical_care` (`Readiness.IMPLEMENTED`, `enableable=False`, `MODULE_REGISTRY_VERSION=14`, `PERMISSIONS_VERSION=23` with non-delegable `CARE_READ`/`CARE_WORK`/`CARE_MANAGE`) and migration `0146_special_clinical_vet_social_care.sql` (invoker rights only, tenant RLS + restrictive branch RLS + module write gates).
