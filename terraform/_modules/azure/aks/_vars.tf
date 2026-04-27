# TODO: Implement Azure Kubernetes Service module
#
# Expected variables:
#   cluster_name          string   — AKS cluster name
#   resource_group_name   string
#   location              string
#   kubernetes_version    string   — e.g. "1.30"
#   node_subnet_id        string   — private subnet for the system node pool
#   node_vm_size          string   — e.g. "Standard_D2s_v3"
#   node_count            number
#   min_count             number
#   max_count             number
#   enable_workload_identity bool  — OIDC issuer + workload identity (equiv. IRSA)
