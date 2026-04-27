# TODO: Implement GCP Artifact Registry module (Docker format)
#
# Expected variables:
#   project_id             string   — GCP project ID
#   location               string   — e.g. "asia-south1"
#   repository_id          string   — e.g. "askloud"
#   image_retention_count  number   — max tagged images to retain per package
#   reader_service_accounts list    — SAs granted roles/artifactregistry.reader (GKE nodes)
