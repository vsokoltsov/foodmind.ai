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

variable "gemini_api_key" {
  description = "Gemini key stored as a Secret Manager version."
  type        = string
  sensitive   = true
  default     = null
}

variable "github_actions_service_account_email" {
  description = "Service account allowed to read CI secrets."
  type        = string
}

variable "nicegui_storage_secret" {
  description = "Secret used by NiceGUI to protect its signed browser storage."
  type        = string
  sensitive   = true
  default     = null
}

variable "foodmind_database_password" {
  description = "Password for the FoodMind application database user."
  type        = string
  sensitive   = true
}

variable "kestra_database_password" {
  description = "Password for the Kestra database user."
  type        = string
  sensitive   = true
}

variable "elasticsearch_password" {
  description = "Password for the managed Elasticsearch deployment."
  type        = string
  sensitive   = true
}
