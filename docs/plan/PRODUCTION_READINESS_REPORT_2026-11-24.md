# GORGONA Platform — Independent Production Readiness Report (16-Point Audit)

**Audit Date:** 2026-11-24 / 2026-11-25 UTC  
**Repository:** `alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new` (`main` @ `3676f13`, migrations `0001..0151`)  
**Live Staging Environment:** Azure `centralus` (`rg-gorgona-staging`, `rg-gorgona-shared`, `rg-gorgona-ai`), revision `ca-gorgona-staging-api--0000004` (`gorgonaacrga8b00.azurecr.io/gorgona-api@sha256:2e8cca3d0b5dc72953800215e8c2640676cd6f5746afb7cc2003fae2e33174ae`)  
**Subscription:** `5f50de54-70cf-46de-a936-7be73f76201e`

---

## Executive Verdict

| Gate | Status | Honest Assessment |
| --- | --- | --- |
| **Platform Core, Security, Multi-Tenant RLS & Azure Staging Infrastructure** | **VERIFIED & LIVE** | 4/4 Azure Deployment Stacks succeeded (`118` managed resources), Private Link enforced, Front Door Premium WAF live, 40-min live Azure soak test (`6,291` reqs, `0` errors, `0` cross-tenant leaks), CI green on `main` (`PR #25, #26, #27, #29`). |
| **Self-Service Onboarding, Finance, Stripe Sandbox, Email/SMS Sandbox, UI & AI/ML Engine** | **TECHNICALLY VERIFIED** | All 39 industries self-onboard cleanly; 101/101 finance tests, 170/170 Stripe Connect tests, 23/23 Email/SMS outbox tests, 29/29 AI/ML `pgvector` + container tests, 34/34 desktop/mobile/axe UI checks + 8/8 vertical browser suites PASS. |
| **Simultaneous Commercial Launch of All 39 Industries in Paid Production** | **CONDITIONAL GO (External & Pilot Gates Remain)** | **Not yet `PRODUCTION_APPROVED`.** Per ADR-0019 and owner rules, 9 core/universal modules are `technically_verified` (`enableable=True`), while 12 vertical modules (`construction`, `rental`, `property`, `restaurant`, `projects`, `supply`, `storefronts`, `analytics`, `hospitality_events`, `clinical_care`, `assets`, `public_civic`) remain `implemented` (`enableable=False`) awaiting formal pilot acceptance (`pilot_accepted` → `production_approved`). Live Production deployment also requires: (1) Azure Container Apps quota increase `1 → 5`, (2) Production Entra External ID CIAM, Stripe Live, ACS Email, Twilio SMS credentials & custom domain, (3) US legal counsel sign-off on ToS/Privacy/DPA/BAA. |

*No paid Production resources were deployed, no live payment keys were connected, and no unverified modules or compliance certifications were claimed.*

---

## Evidence Summary Across All 16 Roadmap Items

| # | Roadmap Item | Status | Concrete Evidence |
| --- | --- | --- | --- |
| **1** | **CI/CD (PR #25, #26, #27, #29) & Azure Staging Deploy** | **DONE** | PR #25 (`ddbaad4`), PR #26 (`00d6dc6`), PR #27 (squashed into `main`), PR #29 (`3676f13`) all passed full GitHub Actions CI (`api` + `ai`) and merged into `main`. Live Staging running `ca-gorgona-staging-api--0000004` (`Healthy`, 100% traffic) with migrations `0001..0151` applied (`caj-gorgona-staging-migrate-hepzafi`: `Succeeded`). |
| **2** | **Azure Front Door, WAF, JWT, RBAC & Cross-Tenant Security Audit** | **DONE** | All 6 private data-plane resources have `publicNetworkAccess=Disabled`. `wafgorgonastaging` updated: DRS 2.1 `911100` disabled for REST mutations, `Authorization` excluded, custom `DisallowedHttpMethods` (priority 50) blocks `TRACE/PROPFIND/MKCOL` (`405`). Live probes: SQLi=`403`, XSS=`403`, PathTraversal=`403`, NoToken/AlgNone/Malformed/WrongAud=`401`, cross-tenant Host B→A=`404`. Live WAF logs confirmed in Log Analytics (`6,380` access + `6,324` WAF entries). Live headers verified on `/onboarding/`: `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `X-Frame-Options: DENY`, `CSP: frame-ancestors 'none'`, `HSTS`. |
| **3** | **Microsoft Entra ID Setup & Staff Invitations** | **DONE (Staging); CIAM Documented for Prod** | Registered `/auth/callback/` and `/auth/logout/` URIs on `GORGONA Staging` (`03500fde-1f63-4895-97ca-29855c624402`). Live Staging staff invitation create (`201`, SHA-256 token hash) → revoke (`204`) → members (`200`) verified. Commercial self-signup requires Entra External ID (CIAM) documented in `docs/runbooks/THIRD_PARTY_ONBOARDING_AND_INTEGRATIONS.md`. |
| **4** | **Self-Service Onboarding (39 Industries)** | **DONE & LIVE ON STAGING** | Migration `0150_self_service_onboarding.sql` (invoker-only, `FORCE RLS`, `RESTRICTIVE` insert policy on `gba.tenants`, zero `SECURITY DEFINER`). Live on Staging: `GET /onboarding/` (`200`), `GET /v1/onboarding/presets` (`39` industries), `GET /v1/onboarding/status` (`200`), `POST /v1/onboarding/businesses` (atomic idempotent workspace creation + Configuration v1). Verified in PG18 tests (`test_self_service_onboarding.py`, `test_tenant_isolation.py`). |
| **5** | **Full 39-Industry Technical Acceptance** | **TECHNICAL E2E DONE; PILOT PENDING** | Real PG18 E2E self-service onboarding & workspace verification across **39/39 industries** (`ALL_39_INDUSTRIES_ONBOARDING_AND_WORKSPACE_PASS=39/39`, zero unverified modules auto-enabled) + **17 vertical workflow suites (`37 passed / 0 failed` in `71.25s`)** covering construction, rental, property, restaurant, projects, supply/WMS/manufacturing/trade, storefronts/marketplaces, enterprise SSO/reporting, hospitality/events, clinical care, assets, and public civic. |
| **6** | **Full Financial Audit** | **DONE** | **14 financial PG18 integration suites: `101 passed / 0 failed` in `103.92s`** (double-entry ledger, multi-currency trial balances, closed periods, invoices, manual accruals, `P+C+R<=A` reserves, external payments, corrections, credit notes, voids, refunds, prepaid, commissions, construction retainage, rental settlement, restaurant split billing, projects billing, property move-out). |
| **7** | **Stripe Connect, Email & SMS Sandbox Readiness** | **DONE & LIVE ON STAGING** | **Stripe Connect:** 6 real PG18 suites (`170 passed / 0 failed` in `121.28s`). **Email & SMS (PR #29):** migration `0151_notification_outbox.sql` (`FORCE RLS`), `SandboxNotificationTransport`, `AzureCommunicationEmailTransport` (HMAC-SHA256), `TwilioSmsTransport` (stdlib `HTTPSConnection`, zero extra runtime deps), 4 templates, PII masking + SHA-256 hash, 3-attempt retry & dead-lettering (`23/23` PG18 tests + `4/4` production container tests). Verified live on Azure Staging: Email (`sbx-email-...`) & SMS (`sbx-sms-...`) dispatched & persisted to Azure PG18 outbox. |
| **8** | **Azure AI/ML End-to-End Verification** | **ENGINE VERIFIED; JOBS STACK QUOTA-BLOCKED** | `gorgona-ai` stack deployed (`54` resources, private PG18 `pgvector`, GRS evidence storage, private Key Vault, Service Bus, ML workspace `mlw-gorgona-ai-ga8b00`, `cpu-train` `Standard_D4ds_v4` `minNodeCount: 0`, ACR image `gorgona-ai@sha256:2c530dee...`). Executed full **29/29 AI/ML tests (`GBA_REQUIRE_AI_POSTGRES=1 GBA_REQUIRE_AI_CONTAINER=1`)**: PII/contact redaction, non-production `learning_scope='none'` block, benchmark leakage gate, tenant-scoped RAG search, worker RLS isolation, explicit model promotion/rollback, non-root container health. **Honest blocker:** `gorgona-ai-jobs` runtime Container Apps Environment in `westus3` is blocked by subscription quota `MaxNumberOfGlobalEnvironmentsInSub = 1` (Step 13). |
| **9** | **Full UI Audit (Desktop, Mobile 390px, Accessibility, Perf)** | **DONE** | Real Chromium audit across **17 routes × 2 viewports (`1280x800` & `390x844`) = 34 checks**: **`0` WCAG 2 AA `axe-core` violations, `0` horizontal overflows, `0` JS errors, `avg 264ms / max 277ms` load**. Fixed WCAG contrast regression (`3.25 → >10:1`) in `management-layout.tsx` footer. Executed **8/8 interactive E2E vertical browser suites** (`GBA_REQUIRE_BROWSER=1`, real PG18 + OIDC PKCE + Chromium): **`8 passed / 0 failed` in `219.51s`**. |
| **10** | **Live Azure Staging Load & 40-Minute Soak Test** | **DONE** | Executed real **40-minute live soak test (`2,404.9s`)** against `gba-stg-a` & `gba-stg-b` through Azure Front Door Premium: **`6,291` requests**, **`0` unexpected errors (`0.00%`)**, **`0` cross-tenant leaks (`785/785` Host B→A probes = `404`)**. Client E2E latency: `p50=259.3ms`, `p95=483.4ms`, `p99=758.7ms` (zero drift). Server-side Application Insights: `200 OK` `p50=40ms`, `p95=72ms`, `p99=152ms`, `Errors5xx=0`. Autoscale config verified (`1..3` replicas @ 50 concurrent reqs, liveness/readiness/startup probes). |
| **11** | **Backups, PG18 PITR, DR, Rollback, Alerts & Audit Logs** | **DONE** | Staging PG18 (`psql-gorgona-staging-ga8b00`): `Ready`, `backupRetentionDays=7`, `earliestRestoreDate=2026-11-24T10:08:39Z`. AI PG18 (`psql-gorgona-ai-ga8b00`): `Ready`, `backupRetentionDays=35`, `geoRedundantBackup=Enabled`. Instant Container Apps rollback verified (`--0000003` kept `Healthy` alongside `--0000004`). All 9 Azure Monitor alerts enabled; App Insights & Front Door WAF/Access logs actively ingesting. PG18 `pg_dump`/`pg_restore` drill verified in `OPS-01`. |
| **12** | **Per-Resource Azure Cost Audit & Production Sizing** | **DONE** | Full SKU & MTD cost audit completed (details below). Already applied zero-risk Staging optimization: deactivated idle zero-traffic revisions (`--kvck4bd`, `--0000001`, `--0000002`), cutting idle Staging Container Apps compute by 50%. Flagged `gorgona-dev` VM (`Standard_D8as_v6`, `$52.91` MTD) for deallocation when idle (~`$250/mo` savings). |
| **13** | **Azure Container Apps Quota Request & Dependencies** | **DONE** | Verified via ARM usages API: `ManagedEnvironmentCount = 1/1`. Ready-to-submit quota request (`1 → 5`) and complete external dependencies list documented in `docs/runbooks/THIRD_PARTY_ONBOARDING_AND_INTEGRATIONS.md`. |
| **14** | **Storefronts, Marketplace & Partner API Readiness** | **DONE** | Audited `/v1/customer/*` & `/v1/businesses/{id}/market/*` contracts, `published_fields` allowlist projection, zero-commission client marketplaces, single-seller order isolation, and third-party onboarding runbook. |
| **15** | **US Commercial Legal & Technical Readiness** | **DONE (Tech); COUNSEL REVIEW REQUIRED** | Live `/legal/terms/` and `/legal/privacy/` (`HTTP 200` on Staging, `0` axe violations), US data residency (`centralus`), PII masking/redaction, and explicit non-claims for HIPAA/BAA, FedRAMP, SOC 2, and PCI Level 1 documented. |
| **16** | **Final Independent Audit & Plan/Status/Registry Update** | **DONE** | Updated `GORGONA_MASTER_PLAN.md`, `GORGONA_IMPLEMENTATION_STATUS.md`, this `PRODUCTION_READINESS_REPORT_2026-11-24.md`, and the complete 39-industry readiness registry below. |

---

## Complete 39-Industry Readiness Registry

> **Honest Status Policy (ADR-0019):**
> - **Self-Service Core Modules (`enableable=True`, Live on Staging):** `organization`, `users_access`, `booking_resources`, `counterparties`, `documents`, `finance`, `finance_documents`, `inventory`, `workforce`.
> - **Vertical Modules (`enableable=False` until formal pilot acceptance):** `restaurant`, `storefronts`, `supply`, `projects`, `hospitality_events`, `clinical_care`, `construction`, `assets`, `property`, `rental`, `transport`, `analytics`, `public_civic`.
> - Every single industry (`1..39`) can self-register today and immediately operate on the verified core modules while transparently displaying pending vertical modules.

| ID | Code | Industry (NAICS) | Primary Vertical Module | Code & PG18 E2E | UI / Mobile / Axe | Registry Status | US Launch / Pilot Gate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `beauty` | Beauty and personal care (81) | `booking_resources` (verified) | PASS (`39/39` + `BEAUTY-01`) | PASS (`0` axe) | `technically_verified` (core); profile `planned` | Pilot acceptance → Prod |
| 2 | `restaurants` | Restaurants and food service (72) | `restaurant` | PASS (`REST-01`) | PASS (`/restaurant/`) | `implemented` (`enableable=False`) | Pilot acceptance + POS/tax |
| 3 | `retail` | Retail (44-45) | `storefronts` | PASS (`MARKET-01`) | PASS (`/marketplace/`) | `implemented` (`enableable=False`) | Pilot acceptance + sales tax |
| 4 | `ecommerce` | E-commerce (44-45, 51) | `storefronts` | PASS (`MARKET-01`) | PASS (`/marketplace/`) | `implemented` (`enableable=False`) | Pilot acceptance + Stripe Live |
| 5 | `wholesale` | Wholesale (42) | `supply` | PASS (`SUPPLY-01`) | PASS (`/supply/`) | `implemented` (`enableable=False`) | Pilot acceptance |
| 6 | `legal` | Legal services (54) | `projects` | PASS (`PRO-01`) | PASS (`/projects/`) | `implemented` (`enableable=False`) | Pilot + bar trust/confidentiality rules |
| 7 | `accounting` | Accounting and tax (54) | `projects` | PASS (`PRO-01`) | PASS (`/projects/`) | `implemented` (`enableable=False`) | Pilot + CPA retention rules |
| 8 | `consulting` | Consulting (54) | `projects` | PASS (`PRO-01`) | PASS (`/projects/`) | `implemented` (`enableable=False`) | Pilot acceptance |
| 9 | `creative` | Marketing and creative services (54) | `projects` | PASS (`PRO-01`) | PASS (`/projects/`) | `implemented` (`enableable=False`) | Pilot acceptance |
| 10 | `technology` | IT and software (51, 54) | `projects` | PASS (`PRO-01`) | PASS (`/projects/`) | `implemented` (`enableable=False`) | Pilot acceptance |
| 11 | `media` | Media and telecom (51) | `projects` | PASS (`PRO-01`) | PASS (`/projects/`) | `implemented` (`enableable=False`) | Pilot acceptance |
| 12 | `education` | Education (61) | `hospitality_events` | PASS (`SPECIAL-01`) | PASS (`/specialized/`) | `implemented` (`enableable=False`) | Pilot + FERPA/COPPA review if applicable |
| 13 | `fitness` | Sports and fitness (71) | `hospitality_events` | PASS (`SPECIAL-01`) | PASS (`/specialized/`) | `implemented` (`enableable=False`) | Pilot acceptance |
| 14 | `healthcare` | Healthcare and rehabilitation (62) | `clinical_care` | PASS (`SPECIAL-02`) | PASS (`/specialized/`) | `implemented` (`enableable=False`) | **HIPAA BAA & clinical security audit REQUIRED** |
| 15 | `animal_services` | Veterinary and animal services (54, 81) | `clinical_care` | PASS (`SPECIAL-02`) | PASS (`/specialized/`) | `implemented` (`enableable=False`) | Pilot + state vet board rules |
| 16 | `social_care` | Social services and care (62) | `clinical_care` | PASS (`SPECIAL-02`) | PASS (`/specialized/`) | `implemented` (`enableable=False`) | **HIPAA / state privacy review REQUIRED** |
| 17 | `hospitality` | Hospitality and tourism (72, 56) | `hospitality_events` | PASS (`SPECIAL-01`) | PASS (`/specialized/`) | `implemented` (`enableable=False`) | Pilot + local occupancy tax |
| 18 | `events` | Events, culture and entertainment (71) | `hospitality_events` | PASS (`SPECIAL-01`) | PASS (`/specialized/`) | `implemented` (`enableable=False`) | Pilot acceptance |
| 19 | `construction` | Construction and design (23, 54) | `construction` | PASS (`BUILD-01`) | PASS (`/construction/`) | `implemented` (`enableable=False`) | Pilot + lien/retainage legal review |
| 20 | `field_services` | Field and home services (23, 56, 81) | `assets` | PASS (`SPECIAL-03`) | PASS (`/specialized/`) | `implemented` (`enableable=False`) | Pilot acceptance |
| 21 | `automotive` | Automotive sales and services (44-45, 81) | `assets` | PASS (`SPECIAL-03`) | PASS (`/specialized/`) | `implemented` (`enableable=False`) | Pilot acceptance |
| 22 | `real_estate` | Real estate (53) | `property` | PASS (`PROPERTY-01`) | PASS (`/property/`) | `implemented` (`enableable=False`) | Pilot + state landlord-tenant/Fair Housing |
| 23 | `rental` | Rental and leasing (53) | `rental` | PASS (`RENT-01`) | PASS (`/rental/`) | `implemented` (`enableable=False`) | Pilot + deposit/damage terms |
| 24 | `logistics` | Transportation and logistics (48-49) | `transport` | Protected module (untouched) | Existing `/transport/` | `implemented` (`enableable=False`) | Separate `TMS-01..03` acceptance |
| 25 | `warehousing` | Warehouse operators (48-49) | `supply` | PASS (`SUPPLY-01`) | PASS (`/supply/`) | `implemented` (`enableable=False`) | Pilot acceptance (3PL bailment) |
| 26 | `manufacturing` | Manufacturing (31-33) | `supply` + `assets` | PASS (`SUPPLY-01`/`SPECIAL-03`) | PASS (`/supply/`, `/specialized/`) | `implemented` (`enableable=False`) | Pilot acceptance |
| 27 | `agriculture` | Agriculture, forestry and fishing (11) | `assets` | PASS (`SPECIAL-03`) | PASS (`/specialized/`) | `implemented` (`enableable=False`) | Pilot acceptance |
| 28 | `utilities` | Energy and utilities (22) | `assets` | PASS (`SPECIAL-03`) | PASS (`/specialized/`) | `implemented` (`enableable=False`) | Pilot + NERC/utility regulatory check |
| 29 | `mining` | Mining and extraction (21) | `assets` | PASS (`SPECIAL-03`) | PASS (`/specialized/`) | `implemented` (`enableable=False`) | Pilot + MSHA/OSHA safety compliance |
| 30 | `finance` | Finance and insurance (52) | `public_civic` | PASS (`SPECIAL-04`) | PASS (`/specialized/`) | `implemented` (`enableable=False`) | **SEC/FINRA/state insurance review REQUIRED** |
| 31 | `staffing` | Recruiting and staffing (56) | `public_civic` | PASS (`SPECIAL-04`) | PASS (`/specialized/`) | `implemented` (`enableable=False`) | Pilot + EEOC/employment rules |
| 32 | `security` | Security services (56) | `assets` | PASS (`SPECIAL-03`) | PASS (`/specialized/`) | `implemented` (`enableable=False`) | Pilot + state guard licensing |
| 33 | `facilities` | Cleaning and facilities (56, 81) | `assets` | PASS (`SPECIAL-03`) | PASS (`/specialized/`) | `implemented` (`enableable=False`) | Pilot acceptance |
| 34 | `environment` | Environmental and waste (56) | `assets` | PASS (`SPECIAL-03`) | PASS (`/specialized/`) | `implemented` (`enableable=False`) | Pilot + EPA manifest rules |
| 35 | `personal_services` | Other personal services (81) | `hospitality_events` | PASS (`SPECIAL-01`) | PASS (`/specialized/`) | `implemented` (`enableable=False`) | Pilot acceptance |
| 36 | `organizations` | Organizations and associations (81) | `public_civic` | PASS (`SPECIAL-04`) | PASS (`/specialized/`) | `implemented` (`enableable=False`) | Pilot acceptance |
| 37 | `research` | Scientific and research services (54) | `projects` | PASS (`PRO-01`) | PASS (`/projects/`) | `implemented` (`enableable=False`) | Pilot acceptance |
| 38 | `company_management` | Management of companies (55) | `analytics` | PASS (`ENTERPRISE-01`) | PASS (`/enterprise/`) | `implemented` (`enableable=False`) | Pilot acceptance |
| 39 | `public_administration` | Public administration (92) | `public_civic` | PASS (`SPECIAL-04`) | PASS (`/specialized/`) | `implemented` (`enableable=False`) | **Not FedRAMP/StateRAMP authorized** |

---

## Step 12 — Azure Per-Resource Cost Audit & Economically Optimized Production Sizing

### Current Subscription Resource & Spend Audit (Observed 2026-11-24)

| Resource Group | Resource / SKU | Observed MTD / Run-Rate | Optimization Action |
| --- | --- | --- | --- |
| `rg-gorgona-dev` | `gorgona-dev` (`Standard_D8as_v6`, 8 vCPU / 32 GB, running 24/7) + Public IP + Disk | **`$55.52` MTD** (`$52.91` VM; ~`$260–$280/mo` if 24/7) | **BIGGEST SAVINGS:** Deallocate VM whenever not actively building/testing (owner approval required before stopping) — cuts dev compute cost by **85–90%** (`~$25/mo` disk only). |
| `rg-gorgona-staging` | `afd-gorgona-staging` + `wafgorgonastaging` (`Premium_AzureFrontDoor`) | `$2.66` partial day (~`$330/mo` base + Private Link) | Required for Private Link to internal Container Apps. In Production, share one Front Door Premium profile across custom domains rather than duplicating profiles. |
| `rg-gorgona-staging` | `psql-gorgona-staging-ga8b00` (`Standard_D2ds_v5`, 64 GB, Single-Zone) | `$0.80` partial day (~`$145/mo`) | For non-prod Staging, can downsize to `Standard_B2s` (~`$55/mo`) when not load-testing; keep `Standard_D2ds_v5` + Zone-Redundant HA in Production. |
| `rg-gorgona-staging` | `ca-gorgona-staging-api` (`0.5 vCPU / 1 GiB`, `minReplicas: 1`) | `$0.59` partial day (~`$28/mo` per active replica) | **ALREADY APPLIED:** Deactivated idle 0%-traffic revisions (`--kvck4bd`, `--0000001`, `--0000002`), cutting active replicas from `4` → `2` (**50% immediate savings** while preserving instant rollback). |
| `rg-gorgona-staging` | `kv-gba-stg-ga8b00` + 2 Private Endpoints | ~`$15/mo` | Optimal — required for zero public DB/KV exposure. |
| `rg-gorgona-ai` | `psql-gorgona-ai-ga8b00` (`Standard_B1ms`, 32 GB, 35d Geo-Backup) + `stevidga8b00gba` (`GRS`) + `sb-gorgona-ai` (`Basic`) + `mlw-gorgona-ai` (`cpu-train` `minNodeCount: 0`) + 3 PEs | ~`$50–$65/mo` idle | Already cost-optimized (`B1ms` burstable, ML compute scales to `0`, Service Bus `Basic`). |
| `rg-gorgona-shared` | `gorgonaacrga8b00` (`Standard`), `log-gorgona-shared`, `appi-gorgona-shared` | `$0.00` MTD (~`$20–$35/mo` run-rate) | Optimal shared observability & registry across all stacks. |
| `rg-gorgona-ai-jobs` | `vnet-gorgona-ai-jobs` (only resource) | **`$0.00/mo`** | Free VNet pre-linked to Private DNS; ready for `gorgona-ai-jobs` after quota increase. |

### Recommended Production Configurations (Without Reducing Security or Reliability)

| Tier | Architecture | Security & Reliability Preserved | Est. Monthly Cost (USD) |
| --- | --- | --- | --- |
| **Option A: Lean Commercial Launch (Recommended First)** | Shared Front Door Premium + WAF DRS 2.1 + Private Link; Container Apps `0.5 vCPU / 1 GiB` (`minReplicas: 2`, `maxReplicas: 8`, 2 AZs); PG18 `Standard_D2ds_v5` (128 GB, 35-day Geo-Redundant Backup, Same-Zone/Zone-Redundant HA); Shared ACR Standard + Log Analytics (30d retention); AI PG18 `B1ms` + ML `minNodes=0`; ACS Email + Twilio pay-per-use; `gorgona-dev` VM deallocated. | **100% preserved:** Zero public DB/KV/API ingress, OWASP WAF, `FORCE RLS`, multi-replica API, 35-day PITR + Geo-Backup, full App Insights/WAF alerting. | **~$720 – $860 / mo** *(+ variable Email/SMS usage)* |
| **Option B: High-Scale Enterprise Production** | Dedicated Front Door Premium + WAF; Container Apps `1 vCPU / 2 GiB` (`minReplicas: 3`, `maxReplicas: 20`); PG18 `Standard_D4ds_v5` Zone-Redundant HA + Read Replica + 35-day Geo-Backup; Service Bus Standard + Private Endpoint; Log Analytics 90d retention + Defender for Cloud. | Full multi-AZ active-active compute, dedicated read replica for heavy reporting/BI, 90-day audit retention. | **~$1,650 – $2,100 / mo** |

---

## Remaining Owner Decisions Before Paid Production Launch

1. **Approve Deallocating `gorgona-dev` VM when idle** (immediate ~$250/mo savings; disk & worktrees remain intact).
2. **Submit Azure Support Quota Request** (`MaxNumberOfGlobalEnvironmentsInSub`: `1 → 5`) to unblock `gorgona-ai-jobs` and `gorgona-production`.
3. **Choose Production Sizing (Option A vs Option B)** and authorize creating `rg-gorgona-production`.
4. **Provide Production Credentials via Key Vault**: Entra External ID (CIAM), Custom Domain/DNS, Stripe Connect Live, ACS Email verified domain, Twilio A2P 10DLC SMS.
5. **US Legal Counsel Sign-Off & Pilot Acceptance**: Finalize ToS/Privacy/DPA/HIPAA BAA boundaries and authorize moving vertical modules from `implemented` → `pilot_accepted` → `production_approved`.
