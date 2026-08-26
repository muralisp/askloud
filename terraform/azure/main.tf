# TODO: Instantiate Azure modules for the dev environment.
#
# Example wiring (uncomment and fill in once modules are implemented):
#
# module "network" {
#   source              = "../../_modules/azure/network"
#   resource_group_name = azurerm_resource_group.main.name
#   location            = var.location
#   vnet_cidr           = var.vnet_cidr
#   ...
# }
#
# module "acr" {
#   source              = "../../_modules/azure/acr"
#   registry_name       = "asklouddev"
#   resource_group_name = azurerm_resource_group.main.name
#   location            = var.location
#   sku                 = "Basic"
#   ...
# }
#
# module "aks" {
#   source              = "../../_modules/azure/aks"
#   node_subnet_id      = module.network.private_subnet_ids[0]
#   ...
# }
#
# module "github_oidc" {
#   source      = "../../_modules/azure/github-oidc"
#   github_repo = "muralisp/askloud"
#   acr_id      = module.acr.registry_id
#   ...
# }
