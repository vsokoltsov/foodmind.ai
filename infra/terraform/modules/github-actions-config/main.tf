resource "github_actions_variable" "gcp_project_id" {
  repository    = var.repository
  variable_name = "GCP_PROJECT_ID"
  value         = var.gcp_project_id
}

resource "github_actions_variable" "workload_identity_provider" {
  repository    = var.repository
  variable_name = "GCP_WORKLOAD_IDENTITY_PROVIDER"
  value         = var.workload_identity_provider
}

resource "github_actions_variable" "service_account" {
  repository    = var.repository
  variable_name = "GCP_SERVICE_ACCOUNT"
  value         = var.gcp_service_account_email
}

resource "github_actions_variable" "evaluation_bucket" {
  repository    = var.repository
  variable_name = "EVALUATION_ARTIFACT_BUCKET"
  value         = var.evaluation_bucket_name
}

resource "github_actions_variable" "region" {
  repository    = var.repository
  variable_name = "GCP_REGION"
  value         = var.region
}

resource "github_actions_variable" "gke_cluster_name" {
  repository    = var.repository
  variable_name = "GKE_CLUSTER_NAME"
  value         = var.gke_cluster_name
}

resource "github_actions_variable" "gke_namespace" {
  repository    = var.repository
  variable_name = "GKE_NAMESPACE"
  value         = var.gke_namespace
}

resource "github_actions_variable" "artifact_registry_repository" {
  repository    = var.repository
  variable_name = "ARTIFACT_REGISTRY_REPOSITORY"
  value         = var.artifact_registry_repository
}

resource "github_actions_variable" "cloud_sql_connection_name" {
  repository    = var.repository
  variable_name = "CLOUD_SQL_CONNECTION_NAME"
  value         = var.cloud_sql_connection_name
}

resource "github_actions_variable" "gcp_workload_service_account" {
  repository    = var.repository
  variable_name = "GCP_WORKLOAD_SERVICE_ACCOUNT"
  value         = var.gcp_workload_service_account
}

resource "github_actions_variable" "gcs_bucket_name" {
  repository    = var.repository
  variable_name = "GCS_BUCKET"
  value         = var.gcs_bucket_name
}

resource "github_actions_variable" "elasticsearch_endpoint" {
  repository    = var.repository
  variable_name = "ELASTICSEARCH_ENDPOINT"
  value         = var.elasticsearch_endpoint
}

resource "github_actions_variable" "elasticsearch_username" {
  repository    = var.repository
  variable_name = "ELASTICSEARCH_USERNAME"
  value         = var.elasticsearch_username
}

resource "github_actions_variable" "api_domain_name" {
  count = var.api_domain_name == null ? 0 : trimspace(var.api_domain_name) == "" ? 0 : 1

  repository    = var.repository
  variable_name = "API_DOMAIN_NAME"
  value         = var.api_domain_name
}

resource "github_actions_variable" "kestra_basic_auth_username" {
  repository    = var.repository
  variable_name = "KESTRA_BASIC_AUTH_USERNAME"
  value         = var.kestra_basic_auth_username
}

resource "github_actions_variable" "kestra_public_ip" {
  repository    = var.repository
  variable_name = "KESTRA_PUBLIC_IP"
  value         = var.kestra_public_ip
}

resource "github_actions_variable" "nats_ui_public_ip" {
  repository    = var.repository
  variable_name = "NATS_UI_PUBLIC_IP"
  value         = var.nats_ui_public_ip
}

resource "github_actions_variable" "terraform_state_bucket" {
  repository    = var.repository
  variable_name = "TERRAFORM_STATE_BUCKET"
  value         = var.terraform_state_bucket
}
