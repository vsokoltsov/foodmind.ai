resource "google_project_service" "vertex_ai" {
  project = var.project_id
  service = "aiplatform.googleapis.com"

  disable_on_destroy = false
}

resource "google_project_iam_member" "vertex_ai_user" {
  for_each = toset(var.service_account_emails)

  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${each.value}"

  depends_on = [google_project_service.vertex_ai]
}
