# Artifact Registry repository for Docker images
resource "google_artifact_registry_repository" "tldrist" {
  location      = var.region
  repository_id = "tldrist"
  description   = "Docker repository for TLDRist"
  format        = "DOCKER"

  depends_on = [google_project_service.apis]
}

# Allow the tldrist service account to push images
resource "google_artifact_registry_repository_iam_member" "tldrist_writer" {
  project    = var.project_id
  location   = var.region
  repository = google_artifact_registry_repository.tldrist.name
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.tldrist.email}"
}

# Allow Cloud Build to push images
resource "google_artifact_registry_repository_iam_member" "cloudbuild_writer" {
  project    = var.project_id
  location   = var.region
  repository = google_artifact_registry_repository.tldrist.name
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${data.google_project.current.number}@cloudbuild.gserviceaccount.com"
}
