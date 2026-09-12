resource "google_project_service" "sqladmin" {
  project            = var.project_id
  service            = "sqladmin.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "service_networking" {
  project            = var.project_id
  service            = "servicenetworking.googleapis.com"
  disable_on_destroy = false
}

resource "google_compute_global_address" "private_services" {
  project       = var.project_id
  name          = "${var.name}-sql-private-services"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = var.network_id
}

resource "google_service_networking_connection" "private_services" {
  network                 = var.network_id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_services.name]

  depends_on = [google_project_service.service_networking]
}

resource "random_password" "foodmind" {
  length  = 32
  special = false
}

resource "random_password" "kestra" {
  length  = 32
  special = false
}

resource "google_sql_database_instance" "foodmind" {
  project             = var.project_id
  name                = var.name
  region              = var.region
  database_version    = "POSTGRES_17"
  deletion_protection = var.deletion_protection

  settings {
    edition                  = var.edition
    tier                     = var.tier
    availability_type        = var.availability_type
    disk_type                = "PD_SSD"
    disk_size                = 20
    retain_backups_on_delete = false

    # Cloud SQL has two independent safeguards. The resource-level setting
    # protects Terraform deletes; this API-level setting also blocks deletes
    # made through Terraform when enabled. Keep both controlled by the same
    # input so the destroy profile can disable them together.
    deletion_protection_enabled = var.deletion_protection

    backup_configuration {
      enabled = true
    }

    ip_configuration {
      ipv4_enabled    = false
      private_network = var.network_id
    }
  }

  depends_on = [
    google_project_service.sqladmin,
    google_service_networking_connection.private_services,
  ]
}

resource "google_sql_database" "foodmind" {
  project  = var.project_id
  name     = "foodmind"
  instance = google_sql_database_instance.foodmind.name
}

resource "google_sql_database" "kestra" {
  project  = var.project_id
  name     = "kestra"
  instance = google_sql_database_instance.foodmind.name
}

resource "google_sql_user" "foodmind" {
  project  = var.project_id
  name     = "foodmind"
  instance = google_sql_database_instance.foodmind.name
  password = random_password.foodmind.result
}

resource "google_sql_user" "kestra" {
  project  = var.project_id
  name     = "kestra"
  instance = google_sql_database_instance.foodmind.name
  password = random_password.kestra.result
}
