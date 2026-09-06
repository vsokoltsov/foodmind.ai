resource "google_project_service" "run" {
  project            = var.project_id
  service            = "run.googleapis.com"
  disable_on_destroy = false
}

resource "google_service_account" "ui" {
  project      = var.project_id
  account_id   = "${var.name}-ui"
  display_name = "FoodMind UI Cloud Run"
}

resource "google_cloud_run_v2_service" "ui" {
  project  = var.project_id
  name     = "${var.name}-ui"
  location = var.region

  template {
    service_account = google_service_account.ui.email

    containers {
      image = var.image

      ports {
        container_port = 7860
      }

      env {
        name  = "FOODMIND_API_URL"
        value = var.api_url
      }

      env {
        name = "NICEGUI_STORAGE_SECRET"
        value_source {
          secret_key_ref {
            secret  = var.nicegui_secret_id
            version = "latest"
          }
        }
      }
    }
  }

  depends_on = [google_project_service.run]
}

resource "google_cloud_run_v2_service_iam_member" "public" {
  count    = var.public_access ? 1 : 0
  project  = var.project_id
  location = google_cloud_run_v2_service.ui.location
  name     = google_cloud_run_v2_service.ui.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_secret_manager_secret_iam_member" "nicegui_storage" {
  project   = var.project_id
  secret_id = var.nicegui_secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.ui.email}"
}

resource "google_cloud_run_domain_mapping" "ui" {
  count    = var.domain_name == null ? 0 : 1
  project  = var.project_id
  location = var.region
  name     = var.domain_name

  metadata {
    namespace = var.project_id
  }

  spec {
    route_name = google_cloud_run_v2_service.ui.name
  }
}

resource "google_dns_record_set" "ui" {
  count        = var.dns_managed_zone == null || var.domain_name == null ? 0 : 1
  project      = var.project_id
  managed_zone = var.dns_managed_zone
  name         = "${var.domain_name}."
  type         = "CNAME"
  ttl          = 300
  rrdatas      = ["ghs.googlehosted.com."]
}
