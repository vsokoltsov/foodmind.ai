output "openai_secret_name" {
  description = "Secret Manager name for the OpenAI API key."
  value       = try(google_secret_manager_secret.openai_api_key[0].secret_id, null)
}
