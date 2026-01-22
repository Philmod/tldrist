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

# User-managed service account for Cloud Build (required for 2nd-gen repos)
resource "google_service_account" "cloudbuild" {
  account_id   = "tldrist-cloudbuild"
  display_name = "TLDRist Cloud Build Service Account"
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

# Allow tldrist service account to write images to GCS bucket
resource "google_storage_bucket_iam_member" "tldrist_storage_writer" {
  bucket = google_storage_bucket.images.name
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:${google_service_account.tldrist.email}"
}

# Cloud Build service account permissions for CI/CD
data "google_project" "current" {}

# Allow user-managed Cloud Build SA to write logs
resource "google_project_iam_member" "cloudbuild_logs_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.cloudbuild.email}"
}

# Allow user-managed Cloud Build SA to push/pull from Artifact Registry
resource "google_project_iam_member" "cloudbuild_artifact_registry" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.cloudbuild.email}"
}

# Allow user-managed Cloud Build SA to deploy to Cloud Run
resource "google_project_iam_member" "cloudbuild_run_developer" {
  project = var.project_id
  role    = "roles/run.developer"
  member  = "serviceAccount:${google_service_account.cloudbuild.email}"
}

# Allow user-managed Cloud Build SA to act as the Cloud Run service account
resource "google_service_account_iam_member" "cloudbuild_act_as_tldrist" {
  service_account_id = google_service_account.tldrist.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.cloudbuild.email}"
}

# Custom role for Cloud Build P4SA - only permissions needed for GitHub connection
resource "google_project_iam_custom_role" "cloudbuild_connection_secrets" {
  role_id     = "cloudbuildConnectionSecrets"
  title       = "Cloud Build Connection Secrets"
  description = "Minimal permissions for Cloud Build to create GitHub connection secrets"
  permissions = [
    "secretmanager.secrets.create",
    "secretmanager.secrets.delete",
    "secretmanager.secrets.get",
    "secretmanager.secrets.update",
    "secretmanager.versions.add",
    "secretmanager.versions.access",
    "secretmanager.secrets.setIamPolicy",
    "secretmanager.secrets.getIamPolicy",
  ]
}

# Allow Cloud Build P4SA to manage connection secrets only
resource "google_project_iam_member" "cloudbuild_connection_secrets" {
  project = var.project_id
  role    = google_project_iam_custom_role.cloudbuild_connection_secrets.id
  member  = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-cloudbuild.iam.gserviceaccount.com"
}
