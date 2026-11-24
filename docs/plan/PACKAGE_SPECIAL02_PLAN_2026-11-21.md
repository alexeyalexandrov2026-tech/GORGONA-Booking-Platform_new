# Package Plan: SPECIAL-02 (Healthcare, Veterinary & Social Care)

Date: 2026-11-21
ADR: `docs/adr/0043-specialized-clinical-vet-social-care.md`
Profiles: `14 healthcare`, `15 animal_services`, `16 social_care`

## Deliverables
- Migration `0146_special_clinical_vet_social_care.sql` (`care_subjects`, `care_consents`, `care_plans`, `care_encounters`).
- Business & API layer (`/v1/businesses/{id}/care/...`) enforcing active-consent gates on writes and consent-based redaction of sensitive `clinical_notes` after revocation.
- Unit contract tests, integration tests (active consent -> care plan & encounter -> consent revocation blocks new encounters & redacts notes + branch isolation), and upgrade test `0145 -> 0146`.
