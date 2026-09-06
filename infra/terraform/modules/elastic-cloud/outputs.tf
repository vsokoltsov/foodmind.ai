output "elasticsearch_endpoint" {
  value = ec_deployment.foodmind.elasticsearch.https_endpoint
}

output "elasticsearch_username" {
  value = ec_deployment.foodmind.elasticsearch_username
}

output "elasticsearch_password" {
  value     = ec_deployment.foodmind.elasticsearch_password
  sensitive = true
}

output "kibana_endpoint" {
  value = ec_deployment.foodmind.kibana.https_endpoint
}
