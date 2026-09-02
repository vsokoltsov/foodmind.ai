output "managed_variables" {
  description = "Names of repository variables managed for GCP federation."
  value = [
    github_actions_variable.gcp_project_id.variable_name,
    github_actions_variable.workload_identity_provider.variable_name,
    github_actions_variable.service_account.variable_name,
  ]
}
