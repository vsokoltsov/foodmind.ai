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

resource "google_secret_manager_secret" "gemini_api_key" {
  count     = var.gemini_api_key == null ? 0 : 1
  project   = var.project_id
  secret_id = "GEMINI_API_KEY"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "gemini_api_key" {
  count       = var.gemini_api_key == null ? 0 : 1
  secret      = google_secret_manager_secret.gemini_api_key[0].id
  secret_data = var.gemini_api_key
}

resource "google_secret_manager_secret_iam_member" "github_actions_gemini" {
  count     = var.gemini_api_key == null ? 0 : 1
  project   = var.project_id
  secret_id = google_secret_manager_secret.gemini_api_key[0].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.github_actions_service_account_email}"
}

resource "google_secret_manager_secret" "nicegui_storage" {
  count     = var.nicegui_storage_secret == null ? 0 : 1
  project   = var.project_id
  secret_id = "NICEGUI_STORAGE_SECRET"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "nicegui_storage" {
  count       = var.nicegui_storage_secret == null ? 0 : 1
  secret      = google_secret_manager_secret.nicegui_storage[0].id
  secret_data = var.nicegui_storage_secret
}

resource "google_secret_manager_secret" "foodmind_database_password" {
  project   = var.project_id
  secret_id = "FOODMIND_DATABASE_PASSWORD"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "foodmind_database_password" {
  secret      = google_secret_manager_secret.foodmind_database_password.id
  secret_data = var.foodmind_database_password
}

resource "google_secret_manager_secret" "kestra_database_password" {
  project   = var.project_id
  secret_id = "KESTRA_DATABASE_PASSWORD"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "kestra_database_password" {
  secret      = google_secret_manager_secret.kestra_database_password.id
  secret_data = var.kestra_database_password
}

resource "google_secret_manager_secret" "kestra_basic_auth_password" {
  project   = var.project_id
  secret_id = "KESTRA_BASIC_AUTH_PASSWORD"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "kestra_basic_auth_password" {
  secret      = google_secret_manager_secret.kestra_basic_auth_password.id
  secret_data = var.kestra_basic_auth_password
}

resource "google_secret_manager_secret" "elasticsearch_password" {
  project   = var.project_id
  secret_id = "ELASTICSEARCH_PASSWORD"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "elasticsearch_password" {
  secret      = google_secret_manager_secret.elasticsearch_password.id
  secret_data = var.elasticsearch_password
}

resource "google_secret_manager_secret_iam_member" "github_actions_runtime" {
  for_each = {
    FOODMIND_DATABASE_PASSWORD = google_secret_manager_secret.foodmind_database_password.secret_id
    KESTRA_DATABASE_PASSWORD   = google_secret_manager_secret.kestra_database_password.secret_id
    KESTRA_BASIC_AUTH_PASSWORD = google_secret_manager_secret.kestra_basic_auth_password.secret_id
    ELASTICSEARCH_PASSWORD     = google_secret_manager_secret.elasticsearch_password.secret_id
  }

  project   = var.project_id
  secret_id = each.value
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.github_actions_service_account_email}"
}
