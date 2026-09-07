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

variable "gemini_api_key" {
  description = "Gemini API key stored in Google Cloud Secret Manager."
  type        = string
  sensitive   = true
  default     = null
}

variable "nicegui_storage_secret" {
  description = "Secret used to sign NiceGUI browser storage."
  type        = string
  sensitive   = true
  default     = null
}

variable "kestra_basic_auth_username" {
  description = "Email address used for the Terraform-managed Kestra Basic Auth administrator."
  type        = string
  default     = "admin@foodmind.local"
}

variable "kestra_basic_auth_password" {
  description = "Optional Kestra Basic Auth password. Terraform generates one when omitted."
  type        = string
  sensitive   = true
  default     = null
  nullable    = true
}

variable "gke_cluster_name" {
  description = "Name of the regional GKE cluster."
  type        = string
  default     = "foodmind"
}

variable "gke_namespace" {
  description = "Kubernetes namespace used by the FoodMind Helm release."
  type        = string
  default     = "foodmind"
}

variable "artifact_repository_id" {
  description = "Artifact Registry Docker repository for FoodMind images."
  type        = string
  default     = "foodmind"
}

variable "gke_node_count" {
  description = "Initial number of GKE worker nodes. One is sufficient for the temporary MVP deployment."
  type        = number
  default     = 1
}

variable "gke_machine_type" {
  description = "GKE worker-node machine type."
  type        = string
  default     = "e2-standard-2"
}

variable "gke_boot_disk_size_gb" {
  description = "Boot-disk size for each GKE worker."
  type        = number
  default     = 30
}

variable "gke_node_zones" {
  description = "Zones used by the GKE node pool. A single zone keeps the temporary MVP deployment inexpensive."
  type        = list(string)
  default     = ["europe-west3-a"]
}

variable "gke_deletion_protection" {
  description = "Prevent accidental deletion of the GKE cluster."
  type        = bool
  default     = false
}

variable "gke_subnet_cidr" {
  description = "Primary CIDR range for the FoodMind GKE subnet."
  type        = string
  default     = "10.10.0.0/20"
}

variable "gke_pods_cidr" {
  description = "Secondary CIDR range for GKE pods."
  type        = string
  default     = "10.20.0.0/16"
}

variable "gke_services_cidr" {
  description = "Secondary CIDR range for GKE services."
  type        = string
  default     = "10.30.0.0/20"
}

variable "cloud_sql_instance_name" {
  description = "Cloud SQL instance name."
  type        = string
  default     = "foodmind-postgres"
}

variable "cloud_sql_tier" {
  description = "Cloud SQL machine tier. db-f1-micro is the lowest-cost development tier."
  type        = string
  default     = "db-f1-micro"
}

variable "cloud_sql_edition" {
  description = "Cloud SQL edition. Enterprise permits the shared-core development tier."
  type        = string
  default     = "ENTERPRISE"
}

variable "cloud_sql_availability_type" {
  description = "Cloud SQL availability type, ZONAL or REGIONAL."
  type        = string
  default     = "ZONAL"
}

variable "cloud_sql_deletion_protection" {
  description = "Prevent accidental deletion of Cloud SQL."
  type        = bool
  default     = false
}

variable "elastic_cloud_api_key" {
  description = "Elastic Cloud control-plane API key used by the managed Elasticsearch provider."
  type        = string
  sensitive   = true
}

variable "elastic_cloud_region" {
  description = "Elastic Cloud GCP region, for example gcp-europe-west3."
  type        = string
  default     = "gcp-europe-west3"
}

variable "elastic_cloud_version" {
  description = "Elastic Stack version for the managed deployment."
  type        = string
  default     = "9.4.3"
}

variable "elastic_cloud_deployment_template_id" {
  description = "Non-deprecated Elastic Cloud deployment template ID for the selected region. Obtain it with infra/terraform/list-elastic-templates.sh."
  type        = string
}

variable "ui_image" {
  description = "Immutable UI image URI deployed to Cloud Run."
  type        = string
  default     = null
}

variable "api_public_url" {
  description = "Public HTTPS base URL of the GKE API used by the Cloud Run UI."
  type        = string
  default     = ""
}

variable "api_domain_name" {
  description = "Optional API DNS name, without a trailing dot."
  type        = string
  default     = null
}

variable "ui_domain_name" {
  description = "Optional verified Cloud Run UI DNS name, without a trailing dot."
  type        = string
  default     = null
}

variable "dns_managed_zone" {
  description = "Optional Cloud DNS managed-zone name for API and UI records."
  type        = string
  default     = null
}

variable "ui_public_access" {
  description = "Allow unauthenticated invocations of the Cloud Run UI."
  type        = bool
  default     = true
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
