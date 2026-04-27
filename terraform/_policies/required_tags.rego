# OPA / Conftest policy — enforces required tags on every Terraform-managed resource.
#
# Usage (run against a terraform plan JSON):
#   terraform -chdir=terraform/dev plan -out=tfplan
#   terraform -chdir=terraform/dev show -json tfplan > plan.json
#   conftest test plan.json --policy terraform/_policies/required_tags.rego
#
# All four tags below are automatically supplied by the aws provider default_tags
# block in _const.tf.  This policy is the CI gate that proves no resource slips
# through without them.

package terraform.required_tags

import future.keywords.in

required_tags := {"Project", "Environment", "ManagedBy", "Owner"}

deny[msg] {
  resource := input.resource_changes[_]
  resource.change.actions[_] in {"create", "update"}
  resource.change.after.tags != null

  resource_tags   := {k | resource.change.after.tags[k]}
  missing_tags    := required_tags - resource_tags
  count(missing_tags) > 0

  msg := sprintf(
    "POLICY FAIL: '%s' is missing required tags: %v",
    [resource.address, missing_tags]
  )
}

deny[msg] {
  resource := input.resource_changes[_]
  resource.change.actions[_] in {"create", "update"}
  resource.change.after.tags == null

  msg := sprintf(
    "POLICY FAIL: '%s' has no tags block — required tags are: %v",
    [resource.address, required_tags]
  )
}
