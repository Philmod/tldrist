# Todoist API token secret
resource "google_secret_manager_secret" "todoist_token" {
  secret_id = "todoist-token"

  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

# Gmail App Password secret
resource "google_secret_manager_secret" "gmail_app_password" {
  secret_id = "gmail-app-password"

  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

# Note: Secret versions must be created manually or via gcloud:
# gcloud secrets versions add todoist-token --data-file=- <<< "your-todoist-token"
# gcloud secrets versions add gmail-app-password --data-file=- <<< "your-gmail-app-password"
