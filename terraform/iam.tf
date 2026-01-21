# Service account for Cloud Run
resource "google_service_account" "tldrist" {
  account_id   = "tldrist"
  display_name = "TLDRist Cloud Run Service Account"
}

# Service account for Cloud Scheduler
resource "google_service_account" "scheduler" {
  account_id   = "tldrist-scheduler"
  display_name = "TL;DRist Cloud Scheduler Service Account"
}

# Allow tldrist service account to access secrets
resource "google_secret_manager_secret_iam_member" "todoist_token" {
  secret_id = google_secret_manager_secret.todoist_token.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.tldrist.email}"
}

resource "google_secret_manager_secret_iam_member" "gmail_app_password" {
  secret_id = google_secret_manager_secret.gmail_app_password.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.tldrist.email}"
}

# Allow tldrist service account to use Vertex AI
resource "google_project_iam_member" "tldrist_aiplatform" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.tldrist.email}"
}

# Allow scheduler to invoke Cloud Run
resource "google_cloud_run_v2_service_iam_member" "scheduler_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.tldrist.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.scheduler.email}"
}
