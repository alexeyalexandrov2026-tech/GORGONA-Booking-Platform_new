terraform {
  required_version = ">= 1.7.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# 1. Private VPC + Direct VPC Egress subnet + Private Service Access for Cloud SQL
resource "google_compute_network" "vpc" {
  name                    = "gorgona-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "run_subnet" {
  name                     = "gorgona-run-subnet"
  region                   = var.region
  network                  = google_compute_network.vpc.id
  ip_cidr_range            = "10.50.0.0/24"
  private_ip_google_access = true
}

resource "google_compute_global_address" "psa_range" {
  name          = "gorgona-psa-range"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 20
  address       = "10.50.16.0"
  network       = google_compute_network.vpc.id
}

resource "google_service_networking_connection" "psa" {
  network                 = google_compute_network.vpc.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.psa_range.name]
}

# 2. Artifact Registry
resource "google_artifact_registry_repository" "gorgona" {
  location      = var.region
  repository_id = "gorgona"
  format        = "DOCKER"
  description   = "GORGONA Booking API and AI Learning Plane container images"
}

# 3. Least-Privilege Service Accounts
resource "google_service_account" "api" {
  account_id   = "gorgona-api-sa"
  display_name = "GORGONA Cloud Run API Runtime SA"
}

resource "google_service_account" "jobs" {
  account_id   = "gorgona-jobs-sa"
  display_name = "GORGONA DB Bootstrap & Migration Jobs SA"
}

resource "google_service_account" "ai" {
  account_id   = "gorgona-ai-sa"
  display_name = "GORGONA AI Learning Plane SA"
}

resource "google_service_account" "scheduler" {
  account_id   = "gorgona-scheduler-sa"
  display_name = "GORGONA Cloud Scheduler SA"
}

# 4. Cloud SQL PostgreSQL 18 (Private IP Only, TLS ENCRYPTED_ONLY, 30d Backups + PITR)
resource "google_sql_database_instance" "pg18" {
  name                = "gorgona-pg18"
  database_version    = "POSTGRES_18"
  region              = var.region
  deletion_protection = true

  depends_on = [google_service_networking_connection.psa]

  settings {
    tier              = var.pg_tier
    availability_type = var.pg_availability_type
    disk_type         = "PD_SSD"
    disk_size         = 100
    disk_autoresize   = true

    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.vpc.id
      ssl_mode        = "ENCRYPTED_ONLY"
    }

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
      start_time                     = "03:00"
      transaction_log_retention_days = 7
      backup_retention_settings {
        retained_backups = 30
      }
    }
  }
}

# 5. AI Evidence Storage (GCS) + Event Intake (Pub/Sub)
resource "google_storage_bucket" "ai_evidence" {
  name                        = "gorgona-ai-evidence-${var.project_id}"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  versioning {
    enabled = true
  }
}

resource "google_pubsub_topic" "ai_intake" {
  name = "gorgona-ai-intake"
}

resource "google_pubsub_subscription" "ai_intake_sub" {
  name  = "gorgona-ai-intake-sub"
  topic = google_pubsub_topic.ai_intake.id
}

# 6. Cloud Armor WAF (Rule 100 non-REST block + OWASP CRS v3.3 sensitivity=1 + JSON parsing + Rate limit)
resource "google_compute_security_policy" "waf" {
  name = "gorgona-waf-policy"

  advanced_options_config {
    json_parsing = "STANDARD"
    log_level    = "NORMAL"
  }

  rule {
    action      = "deny(403)"
    priority    = 100
    description = "Block non-REST HTTP methods at edge"
    match {
      expr {
        expression = "request.method != 'GET' && request.method != 'HEAD' && request.method != 'POST' && request.method != 'PUT' && request.method != 'PATCH' && request.method != 'DELETE' && request.method != 'OPTIONS'"
      }
    }
  }

  rule {
    action      = "deny(403)"
    priority    = 1000
    description = "OWASP SQLi protection (Paranoia Level 1 for JSON REST APIs)"
    match {
      expr {
        expression = "evaluatePreconfiguredWaf('sqli-v33-stable', {'sensitivity': 1})"
      }
    }
  }

  rule {
    action      = "deny(403)"
    priority    = 1010
    description = "OWASP XSS protection"
    match {
      expr {
        expression = "evaluatePreconfiguredWaf('xss-v33-stable', {'sensitivity': 1})"
      }
    }
  }

  rule {
    action      = "deny(403)"
    priority    = 1020
    description = "OWASP LFI/Path Traversal protection"
    match {
      expr {
        expression = "evaluatePreconfiguredWaf('lfi-v33-stable', {'sensitivity': 1})"
      }
    }
  }

  rule {
    action      = "deny(403)"
    priority    = 1030
    description = "OWASP RCE protection"
    match {
      expr {
        expression = "evaluatePreconfiguredWaf('rce-v33-stable', {'sensitivity': 1})"
      }
    }
  }

  rule {
    action      = "throttle"
    priority    = 2000
    description = "API 600 req/min rate limit per IP"
    match {
      expr {
        expression = "request.path.startsWith('/v1/')"
      }
    }
    rate_limit_options {
      conform_action = "allow"
      exceed_action  = "deny(429)"
      enforce_on_key = "IP"
      rate_limit_threshold {
        count        = 600
        interval_sec = 60
      }
    }
  }

  rule {
    action      = "allow"
    priority    = 2147483647
    description = "Default allow"
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
  }
}

# 7. Cloud Run Service (gorgona-api, 4 vCPU / 4 GiB, internal-and-cloud-load-balancing only)
resource "google_cloud_run_v2_service" "api" {
  name     = "gorgona-api"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"

  template {
    service_account                  = google_service_account.api.email
    max_instance_request_concurrency = 50

    scaling {
      min_instance_count = var.api_min_instances
      max_instance_count = var.api_max_instances
    }

    vpc_access {
      egress = "PRIVATE_RANGES_ONLY"
      network_interfaces {
        network    = google_compute_network.vpc.name
        subnetwork = google_compute_subnetwork.run_subnet.name
      }
    }

    containers {
      image = var.api_image
      ports {
        container_port = 8000
      }
      resources {
        limits = {
          cpu    = "4"
          memory = "4Gi"
        }
      }
      env {
        name  = "GBA_ENV"
        value = var.environment
      }
      env {
        name  = "GBA_CUSTOMER_WEB_DIR"
        value = "/app/web"
      }
      env {
        name  = "GBA_DB_POOL_MAX_SIZE"
        value = "15"
      }
      env {
        name  = "GBA_TRUSTED_PROXY"
        value = "google_cloud_lb"
      }
      env {
        name  = "GBA_AUTH_ISSUER"
        value = var.auth_issuer
      }
      env {
        name  = "GBA_AUTH_AUDIENCE"
        value = var.auth_audience
      }
      env {
        name  = "GBA_AUTH_JWKS_URL"
        value = var.auth_jwks_url
      }
      env {
        name  = "GBA_AUTH_CLIENT_ID"
        value = var.auth_client_id
      }
      env {
        name  = "GBA_AUTH_SCOPE"
        value = var.auth_scope
      }
      env {
        name = "GBA_DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = "gorgona-database-url"
            version = "latest"
          }
        }
      }
      env {
        name = "GBA_EDGE_SECRET"
        value_source {
          secret_key_ref {
            secret  = "gorgona-edge-secret"
            version = "latest"
          }
        }
      }
      env {
        name  = "GBA_CF_MODEL"
        value = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
      }
      env {
        name = "GBA_CF_ACCOUNT_ID"
        value_source {
          secret_key_ref {
            secret  = "gorgona-cf-account-id"
            version = "latest"
          }
        }
      }
      env {
        name = "GBA_CF_API_TOKEN"
        value_source {
          secret_key_ref {
            secret  = "gorgona-cf-api-token"
            version = "latest"
          }
        }
      }
    }
  }
}

# 8. Global External HTTPS Load Balancer + Serverless NEG + Edge Secret + HTTP->HTTPS Redirect
resource "google_compute_global_address" "lb_ip" {
  name = "gorgona-lb-ip"
}

resource "google_compute_managed_ssl_certificate" "cert" {
  name = "gorgona-managed-cert"
  managed {
    domains = var.domains
  }
}

resource "google_compute_region_network_endpoint_group" "api_neg" {
  name                  = "gorgona-api-neg"
  network_endpoint_type = "SERVERLESS"
  region                = var.region
  cloud_run {
    service = google_cloud_run_v2_service.api.name
  }
}

resource "google_compute_backend_service" "api_backend" {
  name                  = "gorgona-api-backend"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  security_policy       = google_compute_security_policy.waf.id
  custom_request_headers = [
    "X-Gorgona-Edge-Secret:${var.edge_secret_header_value}"
  ]

  backend {
    group = google_compute_region_network_endpoint_group.api_neg.id
  }

  log_config {
    enable      = true
    sample_rate = 1.0
  }
}

resource "google_compute_url_map" "https" {
  name            = "gorgona-url-map"
  default_service = google_compute_backend_service.api_backend.id
}

resource "google_compute_target_https_proxy" "https" {
  name             = "gorgona-https-proxy"
  url_map          = google_compute_url_map.https.id
  ssl_certificates = [google_compute_managed_ssl_certificate.cert.id]
}

resource "google_compute_global_forwarding_rule" "https" {
  name                  = "gorgona-https-rule"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  ip_address            = google_compute_global_address.lb_ip.address
  port_range            = "443"
  target                = google_compute_target_https_proxy.https.id
}

resource "google_compute_url_map" "http_redirect" {
  name = "gorgona-http-redirect-map"
  default_url_redirect {
    https_redirect         = true
    redirect_response_code = "MOVED_PERMANENTLY_DEFAULT"
    strip_query            = false
  }
}

resource "google_compute_target_http_proxy" "http_redirect" {
  name    = "gorgona-http-proxy"
  url_map = google_compute_url_map.http_redirect.id
}

resource "google_compute_global_forwarding_rule" "http_redirect" {
  name                  = "gorgona-http-rule"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  ip_address            = google_compute_global_address.lb_ip.address
  port_range            = "80"
  target                = google_compute_target_http_proxy.http_redirect.id
}

# 9. Cloud Scheduler (every 15 min) for AI Learning Plane (gorgona-ai-tick)
resource "google_cloud_scheduler_job" "ai_tick" {
  name        = "gorgona-ai-tick-schedule"
  region      = var.region
  description = "Run GORGONA AI dataset_cut + rag_refresh every 15 minutes"
  schedule    = "*/15 * * * *"
  time_zone   = "UTC"

  http_target {
    http_method = "POST"
    uri         = "https://${var.region}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${var.project_id}/jobs/gorgona-ai-tick:run"
    oauth_token {
      service_account_email = google_service_account.scheduler.email
      scope                 = "https://www.googleapis.com/auth/cloud-platform"
    }
  }
}
