# GORGONA — Third-Party Company Onboarding, Integrations, Quota & US Launch Runbook

**Date:** 2026-11-25  
**Target Environment:** Azure Staging (`rg-gorgona-staging`, `centralus`) → Commercial US Production (pending owner sign-off)

---

## 1. Self-Service Company Onboarding (Step 4)

External companies can register and configure a working GORGONA workspace without platform-administrator intervention once authenticated via OIDC:

| Endpoint / Route | Method | Auth | Purpose |
| --- | --- | --- | --- |
| `/onboarding/` | `GET` | Public shell + OIDC PKCE | Multi-industry onboarding UI (desktop & 390px mobile, WCAG 2 AA verified) |
| `/v1/onboarding/presets` | `GET` | Public | Returns all 39 industries (`1..39`), verified enableable modules, and transparent `pending_module_ids` |
| `/v1/onboarding/status` | `GET` | OIDC Bearer | Returns caller link status, active businesses, and `can_create_business` |
| `/v1/onboarding/businesses` | `POST` | OIDC Bearer + `Idempotency-Key` | Atomically creates/links user, signup record (`0150_self_service_onboarding.sql`), tenant, primary location, owner membership, business profile, and published Configuration v1 |

**Security Invariants Enforced:**
- Zero `SECURITY DEFINER` functions. `gba.tenants` retains `FORCE ROW LEVEL SECURITY` with a `RESTRICTIVE` INSERT policy requiring a verified `gba.self_service_signups` row; any unguarded `INSERT INTO gba.tenants` fails with SQLSTATE `42501`.
- Never auto-enables unverified modules (`enableable=False`); pending vertical modules are disclosed transparently in `pending_module_ids`.

---

## 2. Public Storefronts, GORGONA Marketplace & Partner API (Step 14)

### Customer Booking & Public Storefront Surface
- `GET /v1/customer/bootstrap` — tenant-resolved locations, services, variants, and add-ons (strictly scoped by verified Front Door host `gba.tenant_hosts`).
- `POST /v1/customer/availability` — real-time slot availability under tenant RLS (`404` on cross-tenant resource/location IDs).
- `POST /v1/customer/holds`, `POST /v1/customer/bookings` — idempotent hold and booking creation.
- Public UI routes: `/book/`, `/marketplace/`, `/onboarding/`, `/legal/terms/`, `/legal/privacy/`.

### Marketplace & Storefront Management API (`MARKET-01`, ADR-0040)
- `GET/PUT /v1/businesses/{business_id}/market/storefronts` — explicit `published_fields` allowlist projection (prevents accidental internal data publication).
- `GET/PUT /v1/businesses/{business_id}/market/listings` — catalog publishing with availability sync.
- `GET/PUT /v1/businesses/{business_id}/market/marketplaces` — client-operated marketplaces with **zero GORGONA transaction commission** (direct seller settlement).
- `POST /v1/businesses/{business_id}/market/baskets/checkout`, `GET /orders`, `POST /orders/{id}/refund`, `GET /operator-fees` — multi-seller basket split into isolated single-seller orders and payments.

*(Note: `storefronts` module is `implemented` and E2E-verified in automated PG18 & Chromium suites, currently `enableable=False` pending formal pilot acceptance per ADR-0019.)*

---

## 3. Exact Production Access & External Credentials Checklist (Steps 3, 7, 13)

No paid Production services or live payment/messaging credentials have been connected without owner authorization. Before opening paid Production, provision and inject the following via Azure Key Vault references (never in Git or container images):

### 3.1 Microsoft Entra External ID (CIAM) — Commercial Self-Signup
Current Staging app (`03500fde-1f63-4895-97ca-29855c624402`) uses `signInAudience: AzureADMyOrg` (single workforce tenant). For commercial third-party companies:
1. Create a **Microsoft Entra External ID (CIAM)** tenant (or multi-tenant app registration with self-service sign-up user flow).
2. Enable **Self-Service Sign-Up**, **Self-Service Password Reset (SSPR)**, and **Email OTP / MFA**.
3. Register Production SPA redirect URIs: `https://<prod-domain>/auth/callback/` and `https://<prod-domain>/auth/logout/`.
4. Set Container Apps runtime variables: `GBA_AUTH_ISSUER`, `GBA_AUTH_CLIENT_ID`, `GBA_AUTH_SCOPE`.

### 3.2 Stripe Connect (Live Mode)
Code, webhook signature verification, connected-account onboarding admission, receipt ingress, dispute/review flows, and rental holds are verified (`170/170` PG18 tests). Required for Production:
1. Verified US business entity on Stripe + **Stripe Connect Platform** approval.
2. Live Secret Key (`sk_live_...`), Live Webhook Signing Secret (`whsec_...`), and Connect Client ID stored in Production Key Vault.
3. Configure Stripe webhook endpoint on Production Front Door domain with WAF exclusion/rate rules verified.
4. Complete Stripe PCI-DSS **SAQ-A** attestation (no raw PAN touches GORGONA servers).

### 3.3 Transactional Email — Azure Communication Services (ACS)
Implemented in `notifications/transports.py` (`AzureCommunicationEmailTransport`, REST API `2023-03-31`, HMAC-SHA256 signing over stdlib `http.client.HTTPSConnection`) and `0151_notification_outbox.sql`. Currently running in zero-spend `sandbox` mode on Staging. Required for Production:
1. Provision Azure Communication Services + Email Communication Service + verified custom domain (`SPF`, `DKIM`, `DKIM2`, `DMARC` DNS TXT/CNAME records).
2. Set in Production Key Vault / Container App:
   - `GBA_NOTIFICATIONS_MODE=live`
   - `GBA_ACS_EMAIL_ENDPOINT` (`https://<acs-resource>.unitedstates.communication.azure.com`)
   - `GBA_ACS_EMAIL_ACCESS_KEY`
   - `GBA_ACS_EMAIL_SENDER` (`DoNotReply@<verified-domain>`)

### 3.4 Transactional SMS — Twilio Programmable SMS
Implemented in `notifications/transports.py` (`TwilioSmsTransport`, REST API `2010-04-01`, E.164 validation, PII masking + SHA-256 hash, 3-attempt retry + dead-lettering). Currently running in zero-spend `sandbox` mode on Staging. Required for Production:
1. Twilio Live Account + US **A2P 10DLC** Brand & Campaign registration (mandatory for US carrier delivery) + Toll-Free or 10DLC number.
2. TCPA consent capture and `STOP`/`HELP` keyword handling verified with counsel.
3. Set in Production Key Vault / Container App:
   - `GBA_NOTIFICATIONS_MODE=live`
   - `GBA_TWILIO_ACCOUNT_SID`
   - `GBA_TWILIO_AUTH_TOKEN`
   - `GBA_TWILIO_FROM_NUMBER` (E.164 `+1...`)

### 3.5 Custom Domains & DNS
- Production apex/wildcard DNS domain (`app.<domain>`, `*.<domain>`), Azure Front Door managed TLS certificates, and custom domain validation TXT records.

---

## 4. Azure Container Apps Quota Increase Request (Step 13)

Observed live via Azure Resource Manager API (`providers/Microsoft.App/locations/centralus/usages`):
- **Subscription ID:** `5f50de54-70cf-46de-a936-7be73f76201e`
- **Quota Name:** `MaxNumberOfGlobalEnvironmentsInSub` (`ManagedEnvironmentCount`)
- **Current Usage / Limit:** `1 / 1` (`cae-gorgona-staging` occupies the single allowed environment)
- **Requested New Limit:** **`5`** (covers `cae-gorgona-staging`, `cae-gorgona-ai-jobs` in `westus3`, `cae-gorgona-production` in `centralus`, plus 2 spare slots for blue/green DR)
- **Azure Portal Path:** *Help + support → Create a support request → Service and subscription limits (quotas) → Quota type: Azure Container Apps → Global Managed Environments per Subscription*.
- **Blocked Stack:** `gorgona-ai-jobs` (`westus3` VNet `vnet-gorgona-ai-jobs` is already provisioned at `$0/mo` and linked to `rg-gorgona-ai` Private DNS; once quota is approved, run `infra/azure/stack-up.ps1` for `gorgona-ai-jobs`).

---

## 5. US Commercial Launch Legal & Technical Readiness (Step 15)

Live on Azure Staging:
- `/legal/terms/` — Terms of Service (multi-tenant SaaS terms, customer ownership of business data, Stripe Connect merchant-of-record boundary, acceptable use, limitation of liability).
- `/legal/privacy/` — Privacy Policy (data categories, Azure `centralus` US hosting, PII masking in notification outbox & AI evidence redaction, CCPA/CPRA & US state privacy access/deletion rights).

**Honest Compliance & Regulatory Boundaries (Zero Unverified Claims):**
- **Healthcare / Veterinary / Social Care (Industries 14, 15, 16 — `clinical_care`):** Consent-gated records and revocation redaction are implemented and verified technically, **however GORGONA does NOT claim HIPAA compliance until a formal HIPAA risk assessment, administrative safeguards, and executed Business Associate Agreements (BAAs) with Microsoft Azure and customers are in place.** Do not enable `clinical_care` for PHI until legal sign-off.
- **Legal, Accounting, Finance & Insurance (Industries 6, 7, 30):** Platform provides operational workflows and audit trails; customers remain responsible for state bar, CPA, SEC/FINRA, and state insurance commissioner licensing and recordkeeping rules.
- **Public Administration (Industry 39 — `public_civic`):** Transparency audit logs and dual-review workflows are implemented; **GORGONA does NOT claim FedRAMP or StateRAMP authorization.**
- **Payments (All Industries):** Cardholder data is handled exclusively via Stripe Connect; GORGONA stores zero PAN/CVV and requires SAQ-A completion before live card processing.
- **Security Attestations:** Technical controls (Private Link, Front Door WAF, `FORCE RLS`, non-root containers, audit logs) are implemented and tested; **SOC 2 Type I/II certification has NOT yet been audited by an independent CPA firm.**
- **Action Required Before US Commercial Launch:** Final review and execution of `/legal/terms/`, `/legal/privacy/`, Data Processing Addendum (DPA), and US state business registration/tax nexus configuration by qualified US counsel.
