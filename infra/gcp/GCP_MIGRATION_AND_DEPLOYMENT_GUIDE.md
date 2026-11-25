# GORGONA Platform - Google Cloud Migration & Deployment Guide

GORGONA is architected to be **100% cloud-portable** between Microsoft Azure and Google Cloud with zero business-logic changes:
- Standard PostgreSQL 18 + `FORCE ROW LEVEL SECURITY` (no cloud-specific SQL extensions)
- Standard OIDC/JWT verification (works natively with Google Identity Platform / Firebase Auth / Entra External ID / Auth0)
- Native fail-closed `GBA_TRUSTED_PROXY=google_cloud_lb` boundary (`GoogleCloudLoadBalancerMiddleware` + `X-Gorgona-Edge-Secret`)
- Cloud-agnostic `SmtpEmailTransport` + `TwilioSmsTransport` + `SandboxNotificationTransport`
- Standard OpenTelemetry instrumentation

## 1:1 Azure to Google Cloud Architecture Mapping

| Layer | Azure Staging (Current) | Google Cloud Target |
| --- | --- | --- |
| Edge WAF & TLS | Azure Front Door Premium + WAF DRS 2.1 | Global External Application Load Balancer + **Cloud Armor** (OWASP CRS + rate limiting + custom header `X-Gorgona-Edge-Secret`) |
| App Runtime | Azure Container Apps (`ca-gorgona-staging-api`) | **Cloud Run** (`gorgona-api`, `ingress: internal-and-cloud-load-balancing`, Direct VPC Egress) |
| Migrations & Jobs | Container Apps Jobs (`caj-*-migrate`, `bootstrap`, `ai-jobs`) | **Cloud Run Jobs** (`gorgona-migrate`, `gorgona-bootstrap`, `gorgona-ai-jobs` - zero 1-environment global quota limit) |
| Primary Database | Azure PostgreSQL 18 Flexible Server (Private Endpoint) | **Cloud SQL for PostgreSQL 18** (Private IP / Private Service Connect, HA Regional, 35-day PITR) |
| AI Vector DB | Azure PG18 `pgvector` (`psql-gorgona-ai`) | **Cloud SQL for PostgreSQL 18** with `pgvector` (or AlloyDB) |
| Container Registry | Azure Container Registry (`gorgonaacrga8b00`) | **Artifact Registry** (`us-central1-docker.pkg.dev/<project>/gorgona`) |
| Secrets | Azure Key Vault (Private Endpoint + RBAC) | **Secret Manager** (IAM least-privilege per service account) |
| AI Evidence & Queue | Azure Blob GRS + Service Bus + Azure ML | **Cloud Storage (Dual/Multi-Region)** + **Pub/Sub** + **Vertex AI** |
| Identity (Commercial CIAM) | Microsoft Entra External ID | **Google Identity Platform** (OIDC / self-signup / MFA / password reset) |
| Email / SMS | ACS Email / Twilio | **SMTP (`GBA_EMAIL_PROVIDER=smtp` - SendGrid/Postmark/Workspace)** + **Twilio SMS** |
| Observability | Log Analytics + App Insights + 9 Alerts | **Cloud Logging + Cloud Monitoring + Cloud Trace** |

## Step-by-Step Zero-Code-Change Cutover

1. **Copy Container Images:** Push verified `gorgona-api` and `gorgona-ai` images by digest to Artifact Registry.
2. **Provision Private Data Plane:** Create VPC `gorgona-vpc`, Cloud SQL PostgreSQL 18 (`private-ip` only, `BTREE_GIST` + `pgvector`), and Secret Manager secrets (`gorgona-database-url`, `gorgona-migration-database-url`, `gorgona-edge-secret` >= 32 random chars).
3. **Bootstrap & Migrate:** Run `gorgona-bootstrap` and `gorgona-migrate` Cloud Run Jobs (`infra/gcp/cloudrun-migrate-job.yaml`) - applies all 151 migrations (`0001..0151`).
4. **Deploy API:** Deploy `infra/gcp/cloudrun-api.yaml` (`GBA_TRUSTED_PROXY=google_cloud_lb`).
5. **Attach Global HTTPS LB + Cloud Armor:** Create Serverless NEG -> Backend Service with custom request header `X-Gorgona-Edge-Secret: <secret>` and Cloud Armor OWASP/rate-limit policy; attach custom DNS + Google-managed TLS certificates.
6. **Verify Live:** Check `/health/ready` (`200`), direct `run.app` URL blocked (`403`/`404`), `/v1/onboarding/presets` (`39` industries), `/onboarding/`, `/settings/` Notifications panel, and run the 40-minute soak test before enabling live payments (`GBA_PRODUCTION_AUTHORIZATION`).
