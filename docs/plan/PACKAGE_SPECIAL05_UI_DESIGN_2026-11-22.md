# Package SPECIAL-05 Design — Unified `/specialized/` UI (2026-11-22)

- Branch: `codex/package-special-05-specialized-ui`
- Migration: none (uses `0145`–`0148`, latest stays `0148`)
- Purpose: Single 4-tab responsive workspace (`/specialized/`) uniting all Stage 8 specialized domains (`hospitality_events`, `clinical_care`, `assets`, `public_civic`) covering all remaining industry profiles through 39/39:
  1. **Venues & Programs** (`SPECIAL-01`, profiles 12, 13, 17, 18, 35)
  2. **Care & Consents** (`SPECIAL-02`, profiles 14, 15, 16) — proves consent gating & note redaction upon revocation
  3. **Assets & Field Safety** (`SPECIAL-03`, profiles 27, 28, 29, 32, 33, 34) — proves critical-incident automatic `out_of_service` lock
  4. **Civic & Dual-Review** (`SPECIAL-04`, profiles 30, 31, 36, 39) — proves four-eyes self-approval block and approval-gated allocation
- Verification: `npm run format:check`, `typecheck`, `lint`, `test:unit`, `next build`, `ruff`, `mypy`, and real Chromium desktop + mobile (390px) E2E with axe-core & PG18 read-back.
