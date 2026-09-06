output "instance_connection_name" { value = google_sql_database_instance.foodmind.connection_name }
output "connection_name" { value = google_sql_database_instance.foodmind.connection_name }
output "foodmind_password" {
  value     = random_password.foodmind.result
  sensitive = true
}
output "kestra_password" {
  value     = random_password.kestra.result
  sensitive = true
}
