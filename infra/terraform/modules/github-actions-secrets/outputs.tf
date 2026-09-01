output "openai_api_key_secret_name" {
  description = "Name of the managed OpenAI Actions secret, when configured."
  value       = var.openai_api_key == null ? null : github_actions_secret.openai_api_key[0].secret_name
}
