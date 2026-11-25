variable "project_id" {
  description = "Google Cloud project ID for the isolated GORGONA environment"
  type        = string
}

variable "region" {
  description = "Primary Google Cloud region"
  type        = string
  default     = "us-central1"
}

variable "environment" {
  description = "GBA_ENV target (staging or production)"
  type        = string
  default     = "staging"

  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "environment must be staging or production."
  }
}

variable "domains" {
  description = "Managed HTTPS domains attached to the Global External Load Balancer"
  type        = list(string)
}

variable "api_image" {
  description = "Pinned Artifact Registry digest for gorgona-api"
  type        = string
}

variable "ai_image" {
  description = "Pinned Artifact Registry digest for gorgona-ai"
  type        = string
}

variable "pg_tier" {
  description = "Cloud SQL PostgreSQL 18 machine tier"
  type        = string
  default     = "db-custom-4-16384"
}

variable "pg_availability_type" {
  description = "ZONAL for staging or REGIONAL (HA) for production"
  type        = string
  default     = "ZONAL"
}

variable "api_min_instances" {
  description = "Minimum warm Cloud Run instances for gorgona-api"
  type        = number
  default     = 1
}

variable "api_max_instances" {
  description = "Maximum Cloud Run instances for gorgona-api"
  type        = number
  default     = 20
}

variable "edge_secret_header_value" {
  description = "Shared >=32 char secret injected by Global LB as X-Gorgona-Edge-Secret"
  type        = string
  sensitive   = true
}

variable "auth_issuer" {
  type = string
}

variable "auth_audience" {
  type = string
}

variable "auth_jwks_url" {
  type = string
}

variable "auth_client_id" {
  type = string
}

variable "auth_scope" {
  type = string
}
