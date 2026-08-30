output "artifact_bucket_name" {
  description = "Bucket name to set as GCS_BUCKET."
  value       = module.ingestion_artifacts.bucket_name
}

output "ingestion_service_account_email" {
  description = "Service account email to use for Kestra workload identity or a local key."
  value       = google_service_account.ingestion.email
}
