variable "repository" {
  description = "GitHub repository receiving Actions configuration variables."
  type        = string
}

variable "gcp_project_id" {
  description = "Google Cloud project ID exposed as a non-sensitive Actions variable."
  type        = string
}

variable "workload_identity_provider" {
  description = "Workload Identity provider resource name exposed as an Actions variable."
  type        = string
}

variable "gcp_service_account_email" {
  description = "GitHub Actions service account email exposed as an Actions variable."
  type        = string
}

variable "evaluation_bucket_name" {
  description = "Evaluation artifact bucket exposed as a non-sensitive Actions variable."
  type        = string
}
