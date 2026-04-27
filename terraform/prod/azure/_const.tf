terraform {
  required_version = ">=1.6"

  # TODO: configure Azure backend when ready
  # backend "azurerm" {
  #   resource_group_name  = "askloud-tfstate-rg"
  #   storage_account_name = "askloudaskloudtfstate"
  #   container_name       = "tfstate"
  #   key                  = "prod/terraform.tfstate"
  # }

  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "~>3.0" }
    azuread = { source = "hashicorp/azuread", version = "~>2.0" }
  }
}

provider "azurerm" {
  features {}

  # Shift-left: all resources inherit these tags at the provider level.
  # Per-resource tags are merged on top — provider tags are the safety net.
  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
      Owner       = var.owner
    }
  }
}
