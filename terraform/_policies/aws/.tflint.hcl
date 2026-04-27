# tflint config — copy or symlink into each environment directory before running tflint.
# Run: tflint --chdir=dev

plugin "aws" {
  enabled = true
  version = "0.32.0"
  source  = "github.com/terraform-linters/tflint-ruleset-aws"
}

# Enforce required tags on every taggable AWS resource
rule "aws_resource_missing_tags" {
  enabled = true
  tags    = ["Project", "Environment", "ManagedBy", "Owner"]
}

# Ensure required_version and required_providers are declared
rule "terraform_required_version" {
  enabled = true
}

rule "terraform_required_providers" {
  enabled = true
}

# Catch deprecated resource attributes before they cause plan failures
rule "terraform_deprecated_interpolation" {
  enabled = true
}

# Enforce snake_case naming for all identifiers
rule "terraform_naming_convention" {
  enabled = true
  format  = "snake_case"
}
