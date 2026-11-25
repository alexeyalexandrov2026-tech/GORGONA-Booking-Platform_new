output "load_balancer_ip" {
  value = google_compute_global_address.lb_ip.address
}

output "cloud_sql_private_ip" {
  value = google_sql_database_instance.pg18.private_ip_address
}

output "cloud_run_service_url" {
  value = google_cloud_run_v2_service.api.uri
}

output "artifact_registry_repo" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.gorgona.repository_id}"
}
