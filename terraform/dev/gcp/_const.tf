terraform {
  required_version = ">=1.6"

  # TODO: configure GCS backend when ready
  # backend "gcs" {
  #   bucket = "askloud-tfstate"
  #   prefix = "dev/gcp"
  # }

  required_providers {
    google = { source = "hashicorp/google", version = "~>5.0" }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region

  # GCP has no provider-level default_labels in google ~>5; use a local
  # and merge into each resource.  Enforced at CI by the OPA policy.
  default_labels = {
    project     = var.project_name
    environment = var.environment
    managed_by  = "terraform"
    owner       = var.owner
  }
}
