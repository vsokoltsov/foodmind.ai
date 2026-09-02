variable "project_id" {
  description = "Google Cloud project containing the secrets."
  type        = string
}

variable "openai_api_key" {
  description = "OpenAI key stored as a Secret Manager version."
  type        = string
  sensitive   = true
  default     = null
}

variable "github_actions_service_account_email" {
  description = "Service account allowed to read CI secrets."
  type        = string
}
