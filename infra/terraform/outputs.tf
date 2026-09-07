output "project_id" {
  description = "Google Cloud project hosting FoodMind."
  value       = var.project_id
}

output "artifact_bucket_name" {
  description = "Bucket name to set as GCS_BUCKET."
  value       = module.ingestion_artifacts.bucket_name
}

output "evaluation_artifact_bucket_name" {
  description = "Bucket name for versioned evaluation strategy artifacts."
  value       = try(module.evaluation_artifacts[0].bucket_name, null)
}

output "ingestion_service_account_email" {
  description = "Service account email to use for Kestra workload identity or a local key."
  value       = google_service_account.ingestion.email
}

output "github_actions_service_account_email" {
  description = "Service account email used by GitHub Actions WIF."
  value       = google_service_account.github_actions.email
}

output "github_workload_identity_provider" {
  description = "Provider resource name for google-github-actions/auth."
  value       = google_iam_workload_identity_pool_provider.github_actions.name
}

output "openai_secret_name" {
  description = "Secret Manager secret containing OPENAI_API_KEY."
  value       = module.gcp_secrets.openai_secret_name
}

output "gemini_secret_name" {
  description = "Secret Manager secret containing GEMINI_API_KEY."
  value       = module.gcp_secrets.gemini_secret_name
}

output "vertex_ai_api_service" {
  description = "Vertex AI API enabled for the project."
  value       = module.vertex_ai.api_service
}

output "gke_cluster_name" {
  description = "GKE cluster to target with Helm."
  value       = module.gke.cluster_name
}

output "artifact_registry_repository" {
  description = "Artifact Registry repository URL for container images."
  value       = module.gke.artifact_repository_url
}

output "gke_workload_service_account_email" {
  description = "Google service account used through GKE Workload Identity."
  value       = module.gke.workload_service_account_email
}

output "cloud_sql_connection_name" {
  description = "Cloud SQL connection name consumed by the Cloud SQL Auth Proxy."
  value       = module.cloud_sql.connection_name
}

output "cloud_sql_foodmind_password" {
  description = "Password for the foodmind application database user."
  value       = module.cloud_sql.foodmind_password
  sensitive   = true
}

output "cloud_sql_kestra_password" {
  description = "Password for the Kestra database user."
  value       = module.cloud_sql.kestra_password
  sensitive   = true
}

output "kestra_basic_auth_username" {
  description = "Username of the Terraform-managed Kestra Basic Auth administrator."
  value       = var.kestra_basic_auth_username
}

output "api_public_ip" {
  description = "Static IP reserved for the GKE API ingress."
  value       = module.gke.api_public_ip
}

output "kestra_public_ip" {
  description = "Static regional IP reserved for the public Kestra service."
  value       = module.gke.kestra_public_ip
}

output "nats_ui_public_ip" {
  description = "Static regional IP reserved for the public NATS UI service."
  value       = module.gke.nats_ui_public_ip
}

output "elasticsearch_endpoint" {
  description = "Managed Elastic Cloud HTTPS endpoint."
  value       = module.elastic_cloud.elasticsearch_endpoint
}

output "elasticsearch_username" {
  description = "Managed Elastic Cloud username."
  value       = module.elastic_cloud.elasticsearch_username
}

output "elasticsearch_password" {
  description = "Managed Elastic Cloud password."
  value       = module.elastic_cloud.elasticsearch_password
  sensitive   = true
}

output "cloud_run_ui_url" {
  description = "Cloud Run UI service URL."
  value       = module.cloud_run_ui.url
}
