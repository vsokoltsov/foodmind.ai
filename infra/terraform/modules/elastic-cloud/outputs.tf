output "elasticsearch_endpoint" {
  description = "Credential-free HTTPS endpoint consumed by Helm deployments."
  value       = ec_deployment.foodmind.elasticsearch.https_endpoint

  precondition {
    condition = can(regex(
      "^https://[^/@?#]+(?::[0-9]+)?/?$",
      ec_deployment.foodmind.elasticsearch.https_endpoint,
    ))
    error_message = "Elastic Cloud must return a credential-free HTTPS endpoint with only a host and optional port."
  }
}

output "elasticsearch_username" {
  value = ec_deployment.foodmind.elasticsearch_username
}

output "elasticsearch_password" {
  value     = ec_deployment.foodmind.elasticsearch_password
  sensitive = true
}

output "available_deployment_templates" {
  description = "Non-deprecated deployment templates compatible with the configured region and stack version."
  value       = local.available_deployment_templates
}

output "kibana_endpoint" {
  value = ec_deployment.foodmind.kibana.https_endpoint
}
