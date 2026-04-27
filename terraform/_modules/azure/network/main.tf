terraform {
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "~>3.0" }
  }
}

# TODO: azurerm_virtual_network, azurerm_subnet (private + public),
#        azurerm_network_security_group, azurerm_nat_gateway
