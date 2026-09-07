module "ingestion_artifacts" {
  source = "./modules/gcs-artifact-bucket"

  project_id            = var.project_id
  region                = var.region
  bucket_name           = var.bucket_name
  service_account_email = google_service_account.ingestion.email
  force_destroy         = var.force_destroy
}

module "evaluation_artifacts" {
  count  = var.evaluation_bucket_name == null ? 0 : 1
  source = "./modules/gcs-artifact-bucket"

  project_id            = var.project_id
  region                = var.region
  bucket_name           = coalesce(var.evaluation_bucket_name, "${var.bucket_name}-evaluation")
  service_account_email = google_service_account.ingestion.email
  force_destroy         = var.force_destroy
}

resource "google_storage_bucket_iam_member" "github_evaluation_writer" {
  count  = var.evaluation_bucket_name == null ? 0 : 1
  bucket = module.evaluation_artifacts[0].bucket_name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.github_actions.email}"
}

resource "google_project_service" "secret_manager" {
  project = var.project_id
  service = "secretmanager.googleapis.com"
}

resource "google_project_service" "iam" {
  project = var.project_id
  service = "iam.googleapis.com"
}

resource "google_project_service" "iam_credentials" {
  project = var.project_id
  service = "iamcredentials.googleapis.com"
}

resource "google_project_service" "sts" {
  project = var.project_id
  service = "sts.googleapis.com"
}

resource "google_iam_workload_identity_pool" "github_actions" {
  project                   = var.project_id
  workload_identity_pool_id = var.github_wif_pool_id
  display_name              = "GitHub Actions"
  description               = "OIDC identities for FoodMind GitHub Actions"
}

resource "google_iam_workload_identity_pool_provider" "github_actions" {
  project                            = var.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github_actions.workload_identity_pool_id
  workload_identity_pool_provider_id = var.github_wif_provider_id
  display_name                       = "GitHub Actions OIDC"
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }
  attribute_condition = "assertion.repository == '${var.github_owner}/${var.github_repository}'"
  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com/"
  }
}

resource "google_service_account" "github_actions" {
  account_id   = var.github_actions_service_account_id
  display_name = "FoodMind GitHub Actions"
  project      = var.project_id
}

resource "google_service_account_iam_member" "github_actions_wif" {
  service_account_id = google_service_account.github_actions.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github_actions.name}/attribute.repository/${var.github_owner}/${var.github_repository}"
}

resource "random_password" "nicegui_storage" {
  length  = 64
  special = true
}

resource "random_password" "kestra_basic_auth" {
  length  = 40
  special = false
}

locals {
  nicegui_storage_secret = coalesce(var.nicegui_storage_secret, random_password.nicegui_storage.result)
  kestra_basic_auth_password = coalesce(
    var.kestra_basic_auth_password,
    random_password.kestra_basic_auth.result,
  )
  ui_image       = coalesce(var.ui_image, "${module.gke.artifact_repository_url}/ui:latest")
  api_public_url = var.api_public_url == "" ? "http://${module.gke.api_public_ip}" : var.api_public_url
}

module "gcp_secrets" {
  source = "./modules/gcp-secrets"

  project_id                           = var.project_id
  openai_api_key                       = var.openai_api_key
  gemini_api_key                       = var.gemini_api_key
  nicegui_storage_secret               = local.nicegui_storage_secret
  kestra_basic_auth_password           = local.kestra_basic_auth_password
  foodmind_database_password           = module.cloud_sql.foodmind_password
  kestra_database_password             = module.cloud_sql.kestra_password
  elasticsearch_password               = module.elastic_cloud.elasticsearch_password
  github_actions_service_account_email = google_service_account.github_actions.email

  depends_on = [google_project_service.secret_manager]
}

module "github_actions_config" {
  source = "./modules/github-actions-config"

  repository                   = var.github_repository
  gcp_project_id               = var.project_id
  workload_identity_provider   = google_iam_workload_identity_pool_provider.github_actions.name
  gcp_service_account_email    = google_service_account.github_actions.email
  evaluation_bucket_name       = coalesce(var.evaluation_bucket_name, "${var.bucket_name}-evaluation")
  region                       = var.region
  gke_cluster_name             = module.gke.cluster_name
  gke_namespace                = var.gke_namespace
  artifact_registry_repository = module.gke.artifact_repository_url
  cloud_sql_connection_name    = module.cloud_sql.connection_name
  gcp_workload_service_account = module.gke.workload_service_account_email
  gcs_bucket_name              = module.ingestion_artifacts.bucket_name
  elasticsearch_endpoint       = module.elastic_cloud.elasticsearch_endpoint
  elasticsearch_username       = module.elastic_cloud.elasticsearch_username
  api_domain_name              = var.api_domain_name
}

resource "google_service_account" "ingestion" {
  account_id   = var.service_account_id
  display_name = "FoodMind ingestion"
  project      = var.project_id
}

module "gke" {
  source = "./modules/gke"

  project_id             = var.project_id
  region                 = var.region
  name                   = var.gke_cluster_name
  artifact_repository_id = var.artifact_repository_id
  node_count             = var.gke_node_count
  machine_type           = var.gke_machine_type
  boot_disk_size_gb      = var.gke_boot_disk_size_gb
  node_zones             = var.gke_node_zones
  deletion_protection    = var.gke_deletion_protection
  subnet_cidr            = var.gke_subnet_cidr
  pods_cidr              = var.gke_pods_cidr
  services_cidr          = var.gke_services_cidr
}

module "cloud_sql" {
  source = "./modules/cloud-sql"

  project_id          = var.project_id
  region              = var.region
  name                = var.cloud_sql_instance_name
  network_id          = module.gke.network_id
  edition             = var.cloud_sql_edition
  tier                = var.cloud_sql_tier
  availability_type   = var.cloud_sql_availability_type
  deletion_protection = var.cloud_sql_deletion_protection
}

module "elastic_cloud" {
  source = "./modules/elastic-cloud"

  name                   = "${var.gke_cluster_name}-elasticsearch"
  region                 = var.elastic_cloud_region
  elastic_stack_version  = var.elastic_cloud_version
  deployment_template_id = var.elastic_cloud_deployment_template_id
}

module "cloud_run_ui" {
  source = "./modules/cloud-run-ui"

  project_id        = var.project_id
  region            = var.region
  name              = var.gke_cluster_name
  image             = local.ui_image
  api_url           = local.api_public_url
  nicegui_secret_id = module.gcp_secrets.nicegui_storage_secret_name
  public_access     = var.ui_public_access
  dns_managed_zone  = var.dns_managed_zone
  domain_name       = var.ui_domain_name
}

resource "google_project_iam_member" "gke_workload_vertex_ai" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${module.gke.workload_service_account_email}"
}

resource "google_service_account_iam_member" "gke_workload_identity" {
  service_account_id = module.gke.workload_service_account_name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[${var.gke_namespace}/foodmind]"

  # The identity pool exists only after GKE enables Workload Identity on the cluster.
  depends_on = [module.gke]
}

resource "google_storage_bucket_iam_member" "gke_ingestion_artifact_writer" {
  bucket = module.ingestion_artifacts.bucket_name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${module.gke.workload_service_account_email}"
}

resource "google_project_iam_member" "gke_workload_cloud_sql" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${module.gke.workload_service_account_email}"
}

resource "google_project_iam_member" "github_actions_artifact_registry" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.github_actions.email}"
}

resource "google_project_iam_member" "github_actions_gke" {
  project = var.project_id
  role    = "roles/container.developer"
  member  = "serviceAccount:${google_service_account.github_actions.email}"
}

resource "google_service_account_iam_member" "github_actions_gke_workload" {
  service_account_id = module.gke.workload_service_account_name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.github_actions.email}"
}

resource "google_dns_record_set" "api" {
  count        = var.dns_managed_zone == null || var.api_domain_name == null ? 0 : 1
  project      = var.project_id
  managed_zone = var.dns_managed_zone
  name         = "${var.api_domain_name}."
  type         = "A"
  ttl          = 300
  rrdatas      = [module.gke.api_public_ip]
}

module "vertex_ai" {
  source = "./modules/vertex-ai"

  project_id = var.project_id
  service_account_emails = [
    google_service_account.ingestion.email,
    google_service_account.github_actions.email,
    module.gke.workload_service_account_email,
  ]
}
