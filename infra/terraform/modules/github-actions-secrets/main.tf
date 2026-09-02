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
