output "api_service" {
  description = "Google API service enabled for Vertex AI."
  value       = google_project_service.vertex_ai.service
}

output "authorized_service_accounts" {
  description = "Service accounts granted the Vertex AI User role."
  value       = sort(tolist(var.service_account_emails))
}
