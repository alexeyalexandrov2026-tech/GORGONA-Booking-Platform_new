# Project instructions for coding agents

## Brand, Scope & Active Repository
- **Brand:** **AMARKAL Platform** — AI-native US Business OS (`https://www.amarkal-platform.com`), operated by Alexey AAA logistics LLC.
- **Active Repository:** `alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new`. Internal package/SQL/GCP identifiers (`gorgona_booking`, `gba.*`, `gorgona-platform-gcp`) stay intact for compatibility; all user-facing UI, copy, metadata, and AI prompts must use **AMARKAL Platform** (never `GORGONA` or legacy hospitality wording).
- **Target Market:** 100% United States (`USD`, US IANA timezones, all **39 NAICS 2022 industries** at once, 0% platform commission, zero vendor lock-in). Never narrow scope to a single industry. KA Nails is a separate project outside this repository's scope.

## Active Production Stack (Zero Microsoft / Zero Azure Runtime)
- **Cloud Hosting (`ADR-0047`):** Google Cloud (`gorgona-platform-gcp`, `us-central1`) — Cloud Run (`GBA_ENV=production`), private Cloud SQL PostgreSQL 18, Global External HTTPS Load Balancer, Cloud Armor WAF, Artifact Registry, Secret Manager, Cloud Scheduler, Pub/Sub.
- **Auth:** 100% **Google Cloud Identity Platform** (`securetoken.google.com/gorgona-platform-gcp`) with Email+Password and One-Click Google Sign-In (`GIS`). Never introduce Microsoft Entra ID or Azure dependencies.
- **Payments:** **Stripe US Live** (`USD` Checkout: Cards, Apple Pay, Google Pay, US Bank ACH, Connect, HMAC-SHA256 webhooks).
- **Email & AI & Media:** **Resend SMTP** (`smtp.resend.com:587`), **Cloudflare Workers AI** (`Llama 3.3 70B` + `Llama 4 Scout Vision`), **Cloudflare R2** (`gorgona-media`).

## Non-Negotiable Engineering Invariants
1. **Multi-Tenant Isolation:** Keep `ENABLE + FORCE ROW LEVEL SECURITY` on every tenant table (`gba.*` and `ai.*`), invoker-only runtime role, zero `SECURITY DEFINER`, and short DB transactions (never hold open PostgreSQL connections across slow external LLM/HTTP calls).
2. **Human Control Over AI:** AI Business Architect, Customer AI Booking Assistant, and Owner AI Command Copilot must remain grounded in live verified data and keep humans in control of state mutations. Always name the customer AI feature "AI Booking Assistant" (`ai_assistant`).
3. **Truthfulness & Security:** No fake bookings, payments, availability, webhooks, auth, or health checks. Never print, commit, or request raw secrets (`sk_live_`, `rk_live_`, `whsec_`, `re_`, DB passwords).
4. **Workflow Discipline:** Work in small, reviewable branches and Pull Requests. Run Ruff, strict mypy, pytest, TypeScript, ESLint, Prettier, and Next.js build checks locally before opening a PR. Obtain owner authorization before production deploys or schema migrations. Report exact checks and outcomes honestly (`PASS`, `FAIL`, `BLOCKED`, `NOT TESTED`).
