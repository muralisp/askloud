plugin "azurerm" {
  enabled = true
  version = "0.26.0"
  source  = "github.com/terraform-linters/tflint-ruleset-azurerm"
}

# TODO: add azurerm_resource_missing_tags rule once tflint-ruleset-azurerm supports it.
# In the meantime the OPA policy (_policies/required_tags.rego) enforces tag presence
# on the terraform plan JSON in CI.

rule "terraform_required_version" {
  enabled = true
}

rule "terraform_required_providers" {
  enabled = true
}

rule "terraform_naming_convention" {
  enabled = true
}
