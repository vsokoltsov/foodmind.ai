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

module "gcp_secrets" {
  source = "./modules/gcp-secrets"

  project_id                           = var.project_id
  openai_api_key                       = var.openai_api_key
  github_actions_service_account_email = google_service_account.github_actions.email

  depends_on = [google_project_service.secret_manager]
}

module "github_actions_config" {
  source = "./modules/github-actions-secrets"

  repository                 = var.github_repository
  gcp_project_id             = var.project_id
  workload_identity_provider = google_iam_workload_identity_pool_provider.github_actions.name
  gcp_service_account_email  = google_service_account.github_actions.email
}

resource "google_service_account" "ingestion" {
  account_id   = var.service_account_id
  display_name = "FoodMind ingestion"
  project      = var.project_id
}
