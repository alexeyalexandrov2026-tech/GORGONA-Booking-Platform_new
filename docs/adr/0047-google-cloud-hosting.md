# ADR-0047: Google Cloud Primary Hosting Topology

- **Status:** Accepted (2026-11-25)
- **Supersedes (Operational Target):** ADR-0012 (Azure Bicep IaC remains preserved as a secondary cloud option)

## Context

On 2026-11-25 the owner migrated GORGONA from Azure to an isolated Google Cloud project (`gorgona-platform-gcp`, region `us-central1`) and decommissioned the Azure resources to eliminate fixed Azure Front Door Premium fees and Azure's single-environment Container Apps subscription cap (`MaxNumberOfGlobalEnvironmentsInSub = 1`), which had blocked live AI worker jobs.

## Decision

GORGONA runs on Google Cloud with strict fail-closed network and tenant-isolation parity:

1. **Data Plane (Private Only):** Cloud SQL PostgreSQL 18 (`gorgona-pg18`, `4 vCPU / 16 GiB RAM`, `100 GB SSD`, `ipv4_enabled=false`, Private Service Access `10.50.16.0/20`, `ssl_mode=ENCRYPTED_ONLY`, 30-day backups + PITR). Runs both `gorgona_booking` (`FORCE RLS`, migrations `0001..0152+`) and `gorgona_ai` (`pgvector`).
2. **Application Runtime:** Cloud Run (`gorgona-api`, `4 vCPU / 4 GiB RAM`, `min=1..20`, Direct VPC Egress `private-ranges-only`, `ingress=internal-and-cloud-load-balancing`). Rejects direct `.run.app` access at both GCP ingress and `GoogleCloudLoadBalancerMiddleware` (`GBA_TRUSTED_PROXY=google_cloud_lb`, `X-Gorgona-Edge-Secret` >= 32 chars verified with `hmac.compare_digest`).
3. **Edge & WAF:** Global External Application Load Balancer (`EXTERNAL_MANAGED`, Premium Tier, Google-managed TLS, HTTP->HTTPS 301 redirect) protected by Cloud Armor (`gorgona-waf-policy`: `--json-parsing=STANDARD`, Rule `100` blocking non-REST methods with `403`, OWASP CRS v3.3 SQLi/XSS/LFI/RCE at sensitivity `1`, Rule `2000` `600 req/min` per IP on `/v1/`).
4. **AI Learning Plane:** Cloud Run Jobs (`gorgona-ai-bootstrap`, `gorgona-ai-migrate`, `gorgona-ai-tick`, `gorgona-ai-health`) triggered every 15 minutes via Cloud Scheduler (`gorgona-ai-tick-schedule`), backed by GCS (`uniform_bucket_level_access`, `public_access_prevention=enforced`) and Google Cloud Pub/Sub (`PubSubSource`).
5. **Infrastructure as Code & CI/CD:** Defined in `infra/gcp/terraform/`, `infra/gcp/cloud-armor-policy.yaml`, and `.github/workflows/deploy-gcp.yml` (Workload Identity Federation, no static keys).

## Consequences

- Zero Azure hosting cost while preserving existing `infra/azure/` Bicep templates and Microsoft Entra ID (free tenant-level OIDC) until custom CIAM migration.
- Both API and AI learning jobs run live in the same isolated VPC with zero environment-count cap.
- `api/src/gorgona_booking/db/bootstrap.py` natively supports managed PG18 non-superuser admin roles (`cloudsqlsuperuser`) without manual intervention.
