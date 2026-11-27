# AMARKAL Platform v2.11.0 — Production SRE Uptime Checks, Alert Policies & Cost Guardrails

resource "google_monitoring_notification_channel" "ops_email" {
  count        = var.ops_alert_email != "" ? 1 : 0
  display_name = "AMARKAL Operations Email"
  type         = "email"
  labels = {
    email_address = var.ops_alert_email
  }
}

locals {
  alert_channels = var.ops_alert_email != "" ? [google_monitoring_notification_channel.ops_email[0].name] : []
  primary_domain = length(var.domains) > 0 ? var.domains[0] : "www.amarkal-platform.com"
}

# 1. Global HTTPS Uptime Check on /health/ready (verifies live PostgreSQL 18 connectivity)
resource "google_monitoring_uptime_check_config" "health_ready" {
  display_name = "AMARKAL Production /health/ready"
  timeout      = "10s"
  period       = "60s"

  http_check {
    path         = "/health/ready"
    port         = 443
    use_ssl      = true
    validate_ssl = true
    accepted_response_status_codes {
      status_value = 200
    }
  }

  monitored_resource {
    type = "uptime_url"
    labels = {
      project_id = var.project_id
      host       = local.primary_domain
    }
  }
}

# 2. Global HTTPS Uptime Check on /.well-known/agent.json (A2A & MCP discovery health)
resource "google_monitoring_uptime_check_config" "agent_card" {
  display_name = "AMARKAL A2A Discovery /.well-known/agent.json"
  timeout      = "10s"
  period       = "300s"

  http_check {
    path         = "/.well-known/agent.json"
    port         = 443
    use_ssl      = true
    validate_ssl = true
    accepted_response_status_codes {
      status_value = 200
    }
  }

  monitored_resource {
    type = "uptime_url"
    labels = {
      project_id = var.project_id
      host       = local.primary_domain
    }
  }
}

# 3. Alert Policy: Uptime Check Failure
resource "google_monitoring_alert_policy" "uptime_down" {
  display_name = "AMARKAL Production /health/ready Down"
  combiner     = "OR"

  conditions {
    display_name = "Uptime check failing from >= 2 probes"
    condition_threshold {
      filter          = "metric.type=\"monitoring.googleapis.com/uptime_check/check_passed\" AND resource.type=\"uptime_url\" AND metric.labels.check_id=\"${google_monitoring_uptime_check_config.health_ready.uptime_check_id}\""
      duration        = "120s"
      comparison      = "COMPARISON_LT"
      threshold_value = 1
      aggregations {
        alignment_period     = "60s"
        per_series_aligner   = "ALIGN_NEXT_OLDER"
        cross_series_reducer = "REDUCE_COUNT_FALSE"
        group_by_fields      = ["resource.label.host"]
      }
    }
  }

  notification_channels = local.alert_channels
}

# 4. Alert Policy: Cloud Run 5xx Spike
resource "google_monitoring_alert_policy" "cloudrun_5xx" {
  display_name = "AMARKAL Cloud Run HTTP 5xx Error Rate"
  combiner     = "OR"

  conditions {
    display_name = "gorgona-api 5xx responses > 5 per minute"
    condition_threshold {
      filter          = "metric.type=\"run.googleapis.com/request_count\" AND resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"gorgona-api\" AND metric.labels.response_code_class=\"5xx\""
      duration        = "120s"
      comparison      = "COMPARISON_GT"
      threshold_value = 5
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_RATE"
      }
    }
  }

  notification_channels = local.alert_channels
}

# 5. Alert Policy: Cloud Run p95 Latency > 2500ms
resource "google_monitoring_alert_policy" "cloudrun_latency_p95" {
  display_name = "AMARKAL Cloud Run p95 Latency High"
  combiner     = "OR"

  conditions {
    display_name = "gorgona-api p95 request latency > 2500ms"
    condition_threshold {
      filter          = "metric.type=\"run.googleapis.com/request_latencies\" AND resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"gorgona-api\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 2500
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_PERCENTILE_95"
      }
    }
  }

  notification_channels = local.alert_channels
}

# 6. Alert Policy: Cloud SQL PostgreSQL 18 CPU > 80%
resource "google_monitoring_alert_policy" "cloudsql_cpu_high" {
  display_name = "AMARKAL Cloud SQL PG18 High CPU"
  combiner     = "OR"

  conditions {
    display_name = "gorgona-pg18 CPU utilization > 80%"
    condition_threshold {
      filter          = "metric.type=\"cloudsql.googleapis.com/database/cpu/utilization\" AND resource.type=\"cloudsql_database\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0.8
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MEAN"
      }
    }
  }

  notification_channels = local.alert_channels
}

# 7. Optional Monthly Budget Guardrail (activates when billing_account_id is supplied)
resource "google_billing_budget" "monthly_guardrail" {
  count           = var.billing_account_id != "" ? 1 : 0
  billing_account = var.billing_account_id
  display_name    = "AMARKAL Production Monthly Budget (${var.monthly_budget_usd} USD)"

  budget_filter {
    projects = ["projects/${var.project_id}"]
  }

  amount {
    specified_amount {
      currency_code = "USD"
      units         = tostring(var.monthly_budget_usd)
    }
  }

  threshold_rules {
    threshold_percent = 0.5
  }
  threshold_rules {
    threshold_percent = 0.8
  }
  threshold_rules {
    threshold_percent = 1.0
  }
}
