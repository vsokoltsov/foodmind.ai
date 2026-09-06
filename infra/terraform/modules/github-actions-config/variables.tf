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

variable "region" {
  description = "GCP region used by the deployment workflow."
  type        = string
}

variable "gke_cluster_name" {
  description = "GKE cluster targeted by the deployment workflow."
  type        = string
}

variable "gke_namespace" {
  description = "Kubernetes namespace used by the FoodMind Helm release."
  type        = string
}

variable "artifact_registry_repository" {
  description = "Artifact Registry repository URL for container image pushes."
  type        = string
}

variable "cloud_sql_connection_name" {
  description = "Cloud SQL instance connection name consumed by the Auth Proxy."
  type        = string
}

variable "gcp_workload_service_account" {
  description = "GCP workload service account bound to the Helm chart service account."
  type        = string
}

variable "gcs_bucket_name" {
  description = "GCS bucket used for ingestion artifacts."
  type        = string
}

variable "elasticsearch_endpoint" {
  description = "Managed Elasticsearch HTTPS endpoint."
  type        = string
}

variable "elasticsearch_username" {
  description = "Managed Elasticsearch username."
  type        = string
}

variable "api_domain_name" {
  description = "Optional public API domain used by the Helm ingress."
  type        = string
  default     = null
  nullable    = true
}
