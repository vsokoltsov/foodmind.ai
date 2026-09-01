resource "github_actions_secret" "openai_api_key" {
  count       = var.openai_api_key == null ? 0 : 1
  repository  = var.repository
  secret_name = "OPENAI_API_KEY"
  value       = var.openai_api_key
}
