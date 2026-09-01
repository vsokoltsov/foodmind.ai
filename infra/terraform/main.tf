module "ingestion_artifacts" {
  source = "./modules/gcs-artifact-bucket"

  project_id            = var.project_id
  region                = var.region
  bucket_name           = var.bucket_name
  service_account_email = google_service_account.ingestion.email
  force_destroy         = var.force_destroy
}

module "github_actions_secrets" {
  source = "./modules/github-actions-secrets"

  repository     = var.github_repository
  openai_api_key = var.openai_api_key
}

resource "google_service_account" "ingestion" {
  account_id   = var.service_account_id
  display_name = "FoodMind ingestion"
  project      = var.project_id
}
