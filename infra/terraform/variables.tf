variable "project_id" {
  description = "Google Cloud project that owns the ingestion bucket."
  type        = string
}

variable "region" {
  description = "Regional location for the ingestion bucket."
  type        = string
  default     = "europe-west3"
}

variable "bucket_name" {
  description = "Globally unique GCS bucket name."
  type        = string
}

variable "evaluation_bucket_name" {
  description = "Optional globally unique bucket for versioned LLM evaluation artifacts."
  type        = string
  default     = null
  nullable    = true
}

variable "service_account_id" {
  description = "Account ID for the Kestra ingestion service account."
  type        = string
  default     = "foodmind-ingestion"
}

variable "force_destroy" {
  description = "Allow Terraform to delete non-empty buckets. Keep false outside local development."
  type        = bool
  default     = false
}

variable "github_owner" {
  description = "GitHub organization or user that owns the repository."
  type        = string
  default     = "vsokoltsov"
}

variable "github_repository" {
  description = "GitHub repository name that receives the Actions secret."
  type        = string
  default     = "foodmind.ai"
}

variable "github_token" {
  description = "GitHub token with repository Actions-secret administration permission."
  type        = string
  sensitive   = true
  default     = null
}

variable "openai_api_key" {
  description = "OpenAI API key stored in Google Cloud Secret Manager."
  type        = string
  sensitive   = true
  default     = null
}

variable "github_wif_pool_id" {
  description = "Workload Identity Federation pool ID for GitHub Actions."
  type        = string
  default     = "github-actions"
}

variable "github_wif_provider_id" {
  description = "Workload Identity Federation OIDC provider ID."
  type        = string
  default     = "github"
}

variable "github_actions_service_account_id" {
  description = "Service account ID used by GitHub Actions through WIF."
  type        = string
  default     = "foodmind-github-actions"
}
