terraform {
  required_providers {
    google = { source = "hashicorp/google", version = "~>5.0" }
  }
}

# TODO: google_container_cluster (private cluster, workload identity, shielded nodes),
#        google_container_node_pool (separate node pool with auto-scaling),
#        google_service_account (node SA with minimal permissions),
#        google_project_iam_member (roles/logging.logWriter, monitoring.metricWriter, etc.)
