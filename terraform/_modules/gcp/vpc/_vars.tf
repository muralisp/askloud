# TODO: Implement GCP VPC + Subnet module
#
# Expected variables:
#   project_id             string   — GCP project ID
#   region                 string   — e.g. "asia-south1"
#   network_name           string
#   private_subnet_cidr    string   — primary range for GKE nodes
#   pod_cidr               string   — secondary range for GKE pods
#   service_cidr           string   — secondary range for GKE services
#   enable_private_nodes   bool     — all GKE nodes use RFC-1918 addresses
