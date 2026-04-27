terraform {
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "~>3.0" }
  }
}

# TODO: azurerm_kubernetes_cluster (system node pool, RBAC, OIDC issuer),
#        azurerm_kubernetes_cluster_node_pool (user node pools),
#        azurerm_user_assigned_identity (workload identity, equiv. IRSA),
#        azurerm_role_assignment (AcrPull on ACR)
