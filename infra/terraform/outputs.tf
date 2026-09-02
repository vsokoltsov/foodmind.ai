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
