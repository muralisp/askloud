terraform {
  required_providers {
    google = { source = "hashicorp/google", version = "~>5.0" }
  }
}

# TODO: google_artifact_registry_repository (format = "DOCKER"),
#        google_artifact_registry_repository_iam_member (reader bindings),
#        google_artifact_registry_repository cleanup policy (retention)
