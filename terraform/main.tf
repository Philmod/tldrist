terraform {
  required_version = ">= 1.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# Enable required APIs
resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "cloudscheduler.googleapis.com",
    "secretmanager.googleapis.com",
    "aiplatform.googleapis.com",
    "cloudbuild.googleapis.com",
    "artifactregistry.googleapis.com",
  ])

  service            = each.value
  disable_on_destroy = false
}

# Cloud Run service
resource "google_cloud_run_v2_service" "tldrist" {
  name     = "tldrist"
  location = var.region

  template {
    service_account = google_service_account.tldrist.email

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/tldrist/tldrist:${var.image_tag}"

      env {
        name  = "TLDRIST_GCP_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "TLDRIST_GCP_REGION"
        value = var.region
      }
      env {
        name  = "TLDRIST_GMAIL_ADDRESS"
        value = var.gmail_address
      }
      env {
        name  = "TLDRIST_RECIPIENT_EMAIL"
        value = var.recipient_email
      }
      env {
        name  = "TLDRIST_TODOIST_PROJECT_ID"
        value = var.todoist_project_id
      }
      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      startup_probe {
        http_get {
          path = "/api/v1/health"
        }
        initial_delay_seconds = 5
        period_seconds        = 10
        failure_threshold     = 3
      }
    }

    scaling {
      min_instance_count = 0
      max_instance_count = 1
    }

    timeout = "300s"
  }

  depends_on = [google_project_service.apis]
}

# Cloud Scheduler job - runs every Monday at 7am Paris time
resource "google_cloud_scheduler_job" "weekly_digest" {
  name        = "tldrist-weekly-digest"
  description = "Trigger TL;DRist weekly digest every Monday at 7am"
  schedule    = "0 7 * * 1"
  time_zone   = var.scheduler_timezone

  http_target {
    http_method = "POST"
    uri         = "${google_cloud_run_v2_service.tldrist.uri}/api/v1/summarize"

    oidc_token {
      service_account_email = google_service_account.scheduler.email
      audience              = google_cloud_run_v2_service.tldrist.uri
    }
  }

  retry_config {
    retry_count          = 3
    min_backoff_duration = "5s"
    max_backoff_duration = "300s"
  }

  depends_on = [google_project_service.apis]
}
