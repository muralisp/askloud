terraform {
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "~>3.0" }
  }
}

# TODO: azurerm_container_registry,
#        azurerm_container_registry_scope_map,
#        lifecycle policy via azurerm_container_registry_task (no native retention API yet)
