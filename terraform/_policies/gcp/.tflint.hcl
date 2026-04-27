plugin "google" {
  enabled = true
  version = "0.28.0"
  source  = "github.com/terraform-linters/tflint-ruleset-google"
}

# TODO: GCP uses resource labels instead of tags.  The shared OPA policy
# (_policies/required_tags.rego) checks both "tags" and "labels" keys so it
# covers GCP plan JSON without a separate rule.

rule "terraform_required_version" {
  enabled = true
}

rule "terraform_required_providers" {
  enabled = true
}

rule "terraform_naming_convention" {
  enabled = true
}
