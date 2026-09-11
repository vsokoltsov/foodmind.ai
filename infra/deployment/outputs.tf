output "release_name" {
  description = "Helm release managed by this state."
  value       = helm_release.foodmind.name
}

output "release_status" {
  description = "Resulting Helm release status."
  value       = helm_release.foodmind.status
}

