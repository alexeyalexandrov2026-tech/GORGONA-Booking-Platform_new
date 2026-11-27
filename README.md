# AMARKAL Platform — AI-Native US Business Operating System

**Live Production:** [https://www.amarkal-platform.com](https://www.amarkal-platform.com)  
**Operator:** Alexey AAA logistics LLC (United States, USD)  
**Repository:** [`alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new`](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new)

AMARKAL Platform is a multi-tenant, AI-native **US Business Operating System** covering **39 NAICS 2022 industries** in one modular core — with **0% platform transaction commission**, **direct Stripe US payouts** (Cards, Apple Pay, Google Pay, ACH), **governed AI (Cloudflare Workers AI + Native MCP)**, and **1-click Zero-Lock-In portable data export**.

*(Internal package, SQL schema, and GCP resource identifiers such as `gorgona_booking`, `gba.*`, and `gorgona-platform-gcp` are preserved for backward compatibility and zero-downtime operation.)*

---

## Core Architecture & Production Stack

| Layer | Technology & Live Production Topology |
|---|---|
| **Frontend (`web/`)** | Next.js 16 (React 19, TypeScript 6, Turbopack static export — 48 routes), WCAG 2.1 AA editorial UI, PWA (`amarkal-shell-v2`) |
| **Backend API (`api/`)** | Python 3.14, FastAPI, Pydantic v2, `psycopg` 3 async pool — 61 routers, 650+ typed endpoints, zero external ORM bloat |
| **Database** | Cloud SQL **PostgreSQL 18** (`us-central1`) with **155 deterministic SQL migrations** (`0001..0155`), strict `ENABLE + FORCE ROW LEVEL SECURITY`, zero `SECURITY DEFINER`, invoker-only runtime role (`gba_runtime`) |
| **Authentication** | **100% Google Cloud Identity Platform** (Email + Password, Password Reset, One-Click **Continue with Google** GIS + RS256 JWKS verification; zero Microsoft/Entra runtime dependency) |
| **Payments** | **Stripe US Live** (`USD`-only): Checkout Sessions (Cards, Apple Pay, Google Pay, US Bank ACH), optional Stripe Connect, HMAC-SHA256 verified webhooks (`/v1/webhooks/stripe`), session sync, 2-step confirmed refunds |
| **AI & Native MCP** | **Cloudflare Workers AI** (`@cf/meta/llama-3.3-70b-instruct-fp8-fast` + `@cf/meta/llama-4-scout-17b-16e-instruct` Vision) powering **AI Business Architect** (`/v1/onboarding/ai-blueprint`), **Owner AI Command Copilot** (`/v1/businesses/{id}/copilot`), **Customer AI Booking Assistant** (`/v1/customer/assistant`), **Native MCP Server v2.1** (`/v1/mcp` — 7 semantic tools secured by Scoped API Keys & `FORCE RLS`), plus isolated `ai/` learning worker (`gorgona_ai` + `pgvector`) |
| **Email & Storage** | **Resend SMTP** (`smtp.resend.com:587`, DKIM + SPF + DMARC verified on `amarkal-platform.com`) and **Cloudflare R2** (`gorgona-media`, AWS SigV4 stdlib client) |
| **Cloud & Security** | **Google Cloud** (`ADR-0047`): Cloud Run (`GBA_ENV=production`), Global External HTTPS Load Balancer (TLS 1.3), **Cloud Armor WAF** (OWASP + Rate Limit), Secret Manager, HSTS + `Permissions-Policy` + governed `Content-Security-Policy` |

---

## Platform Capabilities

- **60-Second Self-Service Onboarding (`/onboarding/`)**: Describe any US business (or upload a price list / menu photo) to the **AI Business Architect**, review the structured blueprint (NAICS industries, US timezone, services, resources, weekly hours), and launch atomically with human approval.
- **39 US NAICS Industries & Modular Verticals**:
  - **Core & Universal Modules (`enableable=True`)**: Organization, Users & RBAC, Delegations, Counterparties & Agreements, Booking & Resources, Workforce Scheduling & Timesheets, Documents, Inventory & Stock Valuation, Double-Entry Ledger (`FIN-01`), Financial Documents & Settlements (`FIN-02/03`), Prepaid & Gift Balances.
  - **Commercial Verticals (`enableable=True`)**: Transport & Brokerage, Construction & Field Execution, Equipment Rental, Property Management, Restaurant Operations, Project Delivery, Supply Chain (WMS/Manufacturing/Trade), Storefronts & 0%-Commission Marketplaces, Enterprise Governance, Assets & Hospitality Events.
  - **Regulated Verticals (`enableable=False` until formal compliance attestation)**: `clinical_care` (HIPAA BAA required) and `public_civic` (FedRAMP/SEC/FINRA disclosures).
- **Go-Live Launchpad & Zero-Lock-In Data Portability (`/overview/`)**: Real-time 0–100% operational readiness score (`GET /v1/businesses/{id}/readiness`), live 30-day Unit Economics in USD, 0% commission savings tracker, and **1-click Portable Business JSON Export** (`GET /v1/businesses/{id}/export/snapshot`).
- **AMARKAL App Hub & Native MCP (`/integrations/`)**: Connector catalog (QuickBooks Online, Google Calendar, Zapier/Make/n8n, Stripe US, Twilio BYOK, Meta Messaging BYOK), Scoped API Keys, signed webhooks, and **Native MCP Server** (`POST /v1/mcp`) compatible with Claude, ChatGPT, Gemini, and custom AI agents.

---

## Local Development & Verification

Prerequisites: **Python 3.14** + [`uv`](https://docs.astral.sh/uv/), **Node.js 24**, and **PostgreSQL 18** (for DB integration tests).

### 1. Frontend (`web/`)
```bash
cd web
npm ci --ignore-scripts
npm run typecheck
npm run lint
npm run format:check
npm run test:unit
npm run build
```

### 2. Backend API (`api/`)
```bash
cd api
uv sync --locked
uv run ruff format --check src tests tools
uv run ruff check src tests tools
uv run mypy src tests tools
uv run pytest -m "not postgres" -q
```
For full PostgreSQL 18 + RLS + Browser integration verification (3,170+ tests), set `GBA_TEST_ADMIN_DSN` pointing to a disposable PG18 instance and run `uv run pytest`.

### 3. AI Worker (`ai/`)
```bash
cd ai
uv sync --locked
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest -v
```

### 4. Environment Configuration
Copy [`.env.example`](.env.example) for local development. Never commit real credentials or secrets. Production secrets are managed exclusively in **Google Cloud Secret Manager**.

---

## Repository Structure

```text
├── api/                 # Python 3.14 / FastAPI backend, 155 PG18 migrations, tests
├── web/                 # Next.js 16 / React 19 / TypeScript frontend & Playwright suite
├── ai/                  # Tenant-isolated AI learning & pgvector RAG worker (gorgona_ai)
├── infra/gcp/           # Active Google Cloud Terraform & Cloud Run deployment specs (ADR-0047)
├── docs/                # ADRs (0001..0047), architecture specs, runbooks, historical plans
├── Dockerfile           # Deterministic multi-stage non-root production image (Node 24 + Python 3.14)
└── .github/workflows/   # CI (API + PG18 + Playwright + AI + Container) & GCP deploy workflow
```

---

## Governance & Engineering Principles

- **Strict Multi-Tenant Isolation**: Every tenant query runs inside a `FORCE ROW LEVEL SECURITY` transaction scoped via `set_config('app.tenant_id', ..., true)` with invoker-only runtime privileges.
- **Human Control Over AI**: AI Business Architect and Owner AI Command Copilot draft, analyze, and propose — humans review and approve state mutations.
- **Truthful Operations**: Never fabricate availability, payments, compliance certifications, or health checks. Read [`AGENTS.md`](AGENTS.md) before making automated repository changes.
