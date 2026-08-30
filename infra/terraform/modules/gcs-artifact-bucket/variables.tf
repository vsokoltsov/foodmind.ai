variable "project_id" {
  description = "Google Cloud project that owns the bucket."
  type        = string
}

variable "region" {
  description = "Bucket location."
  type        = string
}

variable "bucket_name" {
  description = "Globally unique bucket name."
  type        = string
}

variable "service_account_email" {
  description = "Service account allowed to read and write ingestion artifacts."
  type        = string
}

variable "force_destroy" {
  description = "Whether Terraform may delete non-empty bucket contents."
  type        = bool
  default     = false
}
