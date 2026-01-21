variable "project_id" {
  description = "The GCP project ID"
  type        = string
}

variable "region" {
  description = "The GCP region for resources"
  type        = string
  default     = "europe-west1"
}

variable "recipient_email" {
  description = "Email address to receive the weekly digest"
  type        = string
}

variable "gmail_address" {
  description = "Gmail address for sending emails"
  type        = string
}

variable "todoist_project_name" {
  description = "Name of the Todoist project to process"
  type        = string
  default     = "Read"
}

variable "scheduler_timezone" {
  description = "Timezone for the Cloud Scheduler job"
  type        = string
  default     = "Europe/Paris"
}

variable "image_tag" {
  description = "Docker image tag to deploy"
  type        = string
  default     = "latest"
}
