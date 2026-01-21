output "cloud_run_url" {
  description = "URL of the Cloud Run service"
  value       = google_cloud_run_v2_service.tldrist.uri
}

output "scheduler_job_name" {
  description = "Name of the Cloud Scheduler job"
  value       = google_cloud_scheduler_job.weekly_digest.name
}

output "service_account_email" {
  description = "Email of the TLDRist service account"
  value       = google_service_account.tldrist.email
}
