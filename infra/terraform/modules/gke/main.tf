resource "google_project_service" "container" {
  project            = var.project_id
  service            = "container.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "artifact_registry" {
  project            = var.project_id
  service            = "artifactregistry.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "compute" {
  project            = var.project_id
  service            = "compute.googleapis.com"
  disable_on_destroy = false
}

resource "google_compute_network" "foodmind" {
  project                 = var.project_id
  name                    = "${var.name}-network"
  auto_create_subnetworks = false

  depends_on = [google_project_service.compute]
}

resource "google_compute_subnetwork" "foodmind" {
  project       = var.project_id
  name          = "${var.name}-subnet"
  region        = var.region
  network       = google_compute_network.foodmind.id
  ip_cidr_range = var.subnet_cidr

  secondary_ip_range {
    range_name    = "pods"
    ip_cidr_range = var.pods_cidr
  }

  secondary_ip_range {
    range_name    = "services"
    ip_cidr_range = var.services_cidr
  }
}

resource "google_service_account" "workload" {
  project      = var.project_id
  account_id   = "${var.name}-workload"
  display_name = "FoodMind GKE workloads"
}

resource "google_container_cluster" "foodmind" {
  project                  = var.project_id
  name                     = var.name
  location                 = var.region
  network                  = google_compute_network.foodmind.id
  subnetwork               = google_compute_subnetwork.foodmind.id
  remove_default_node_pool = true
  initial_node_count       = 1

  release_channel {
    channel = "REGULAR"
  }

  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }

  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  deletion_protection = var.deletion_protection

  depends_on = [google_project_service.container, google_project_service.compute]
}

resource "google_container_node_pool" "foodmind" {
  project        = var.project_id
  name           = "${var.name}-pool"
  location       = var.region
  cluster        = google_container_cluster.foodmind.name
  node_count     = var.node_count
  node_locations = var.node_zones

  node_config {
    machine_type    = var.machine_type
    disk_size_gb    = var.boot_disk_size_gb
    service_account = google_service_account.workload.email
    oauth_scopes    = ["https://www.googleapis.com/auth/cloud-platform"]

    workload_metadata_config {
      mode = "GKE_METADATA"
    }
  }
}

resource "google_artifact_registry_repository" "foodmind" {
  project       = var.project_id
  location      = var.region
  repository_id = var.artifact_repository_id
  description   = "FoodMind container images"
  format        = "DOCKER"

  depends_on = [google_project_service.artifact_registry]
}

resource "google_compute_global_address" "api" {
  project      = var.project_id
  name         = "${var.name}-api-ip"
  address_type = "EXTERNAL"
  ip_version   = "IPV4"

  depends_on = [google_project_service.compute]
}
