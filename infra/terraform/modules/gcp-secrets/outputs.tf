output "openai_secret_name" {
  description = "Secret Manager name for the OpenAI API key."
  value       = try(google_secret_manager_secret.openai_api_key[0].secret_id, null)
}

output "gemini_secret_name" {
  description = "Secret Manager name for the Gemini API key."
  value       = try(google_secret_manager_secret.gemini_api_key[0].secret_id, null)
}

output "nicegui_storage_secret_name" {
  description = "Secret Manager secret containing NICEGUI_STORAGE_SECRET."
  value       = try(google_secret_manager_secret.nicegui_storage[0].secret_id, null)
}

output "foodmind_database_password_secret_name" {
  description = "Secret Manager secret containing the FoodMind database password."
  value       = google_secret_manager_secret.foodmind_database_password.secret_id
}

output "kestra_database_password_secret_name" {
  description = "Secret Manager secret containing the Kestra database password."
  value       = google_secret_manager_secret.kestra_database_password.secret_id
}

output "kestra_basic_auth_password_secret_name" {
  description = "Secret Manager secret containing the Kestra Basic Auth password."
  value       = google_secret_manager_secret.kestra_basic_auth_password.secret_id
}

output "elasticsearch_password_secret_name" {
  description = "Secret Manager secret containing the Elasticsearch password."
  value       = google_secret_manager_secret.elasticsearch_password.secret_id
}
