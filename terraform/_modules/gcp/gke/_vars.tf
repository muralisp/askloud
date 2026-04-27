# TODO: Implement GKE Autopilot / Standard cluster module
#
# Expected variables:
#   cluster_name           string   — GKE cluster name
#   project_id             string
#   region                 string
#   network_self_link      string   — from vpc module output
#   subnet_self_link        string
#   pod_range_name         string
#   service_range_name     string
#   kubernetes_version     string   — e.g. "1.30"
#   node_machine_type      string   — e.g. "e2-standard-2"
#   node_count             number
#   min_node_count         number
#   max_node_count         number
#   enable_workload_identity bool   — GKE Workload Identity (equiv. IRSA)
