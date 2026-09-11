variable "project_id" {
  description = "Google Cloud project containing the target GKE cluster."
  type        = string
}

variable "region" {
  description = "Region of the target GKE cluster."
  type        = string
}

variable "cluster_name" {
  description = "Name of the target GKE cluster."
  type        = string
}

variable "namespace" {
  description = "Kubernetes namespace for FoodMind."
  type        = string
  default     = "foodmind"
}

variable "component" {
  description = "Independently managed Helm component."
  type        = string

  validation {
    condition     = contains(["all", "bootstrap", "nats", "observability", "grafana", "kestra", "api", "worker"], var.component)
    error_message = "component must be all, bootstrap, nats, observability, grafana, kestra, api, or worker."
  }
}

variable "image_tag" {
  description = "Immutable API and ingestion image tag."
  type        = string
}

variable "kestra_image_tag" {
  description = "Immutable Kestra runtime image tag."
  type        = string
}

variable "artifact_registry_repository" {
  description = "Artifact Registry repository URL, without an image name."
  type        = string
}

variable "cloud_sql_connection_name" {
  description = "Cloud SQL instance connection name consumed by the Auth Proxy."
  type        = string
}

variable "gcp_workload_service_account" {
  description = "Google service account used through GKE Workload Identity."
  type        = string
}

variable "gcs_bucket" {
  description = "Bucket used for ingestion artifacts."
  type        = string
}

variable "evaluation_artifact_bucket" {
  description = "Bucket used for evaluation artifacts."
  type        = string
  default     = ""
}

variable "elasticsearch_endpoint" {
  description = "Credential-free Elastic Cloud HTTPS endpoint."
  type        = string

  validation {
    condition = can(regex(
      "^https://[^@/?#]+/?$",
      var.elasticsearch_endpoint,
    ))
    error_message = "elasticsearch_endpoint must be a credential-free HTTPS host and optional port."
  }
}

variable "elasticsearch_username" {
  description = "Elastic Cloud username."
  type        = string
}

variable "api_domain_name" {
  description = "Optional public API DNS name."
  type        = string
  default     = ""
}

variable "kestra_basic_auth_username" {
  description = "Kestra Basic Auth administrator username."
  type        = string
  default     = "admin@foodmind.local"
}

variable "kestra_public_ip" {
  description = "Static regional IP reserved for Kestra."
  type        = string
}

variable "nats_ui_public_ip" {
  description = "Static regional IP reserved for NATS NUI."
  type        = string
}

variable "adopt_existing_resources" {
  description = "Import the namespace, runtime Secret, and flow ConfigMap created by the legacy deployment script. Disable only for a greenfield cluster."
  type        = bool
  default     = true
}

variable "runtime_secret_revision" {
  description = "Monotonically increasing revision used to rotate write-only Kubernetes Secret data."
  type        = number
  default     = 1
}

# Ephemeral variables are accepted only during the bootstrap apply and feed a
# write-only Kubernetes provider attribute. Their values are therefore omitted
# from the Terraform plan and state.
variable "openai_api_key" {
  type      = string
  sensitive = true
  ephemeral = true
  default   = ""
}

variable "foodmind_database_password" {
  type      = string
  sensitive = true
  ephemeral = true
  default   = ""
}

variable "kestra_database_password" {
  type      = string
  sensitive = true
  ephemeral = true
  default   = ""
}

variable "kestra_basic_auth_password" {
  type      = string
  sensitive = true
  ephemeral = true
  default   = ""
}

variable "elasticsearch_password" {
  type      = string
  sensitive = true
  ephemeral = true
  default   = ""
}

