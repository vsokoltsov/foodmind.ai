resource "google_secret_manager_secret" "openai_api_key" {
  count     = var.openai_api_key == null ? 0 : 1
  project   = var.project_id
  secret_id = "OPENAI_API_KEY"

  replication {
    auto {}
  }

}

resource "google_secret_manager_secret_version" "openai_api_key" {
  count       = var.openai_api_key == null ? 0 : 1
  secret      = google_secret_manager_secret.openai_api_key[0].id
  secret_data = var.openai_api_key
}

resource "google_secret_manager_secret_iam_member" "github_actions" {
  count     = var.openai_api_key == null ? 0 : 1
  project   = var.project_id
  secret_id = google_secret_manager_secret.openai_api_key[0].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.github_actions_service_account_email}"
}
