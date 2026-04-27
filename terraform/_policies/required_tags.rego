# OPA / Conftest policy — enforces required tags/labels on every Terraform-managed resource.
#
# Usage (run against a terraform plan JSON):
#   terraform -chdir=terraform/dev/aws  plan -out=tfplan
#   terraform -chdir=terraform/dev/aws  show -json tfplan > plan.json
#   conftest test plan.json --policy terraform/_policies/required_tags.rego
#
# Cloud coverage:
#   AWS   — provider default_tags supplies the four keys via "tags"
#   Azure — provider default_tags supplies them via "tags"
#   GCP   — provider default_labels supplies them via "labels" (lower-cased keys)
#
# This policy is the CI gate that proves no resource slips through without them.

package terraform.required_tags

import future.keywords.in

required_keys_aws_azure := {"Project", "Environment", "ManagedBy", "Owner"}
required_keys_gcp       := {"project", "environment", "managed_by", "owner"}

# AWS / Azure: enforce on resources that carry a "tags" attribute.
deny[msg] {
  resource := input.resource_changes[_]
  resource.change.actions[_] in {"create", "update"}
  tags := resource.change.after.tags
  tags != null

  missing := required_keys_aws_azure - {k | tags[k]}
  count(missing) > 0

  msg := sprintf(
    "POLICY FAIL: '%s' is missing required tags: %v",
    [resource.address, missing]
  )
}

deny[msg] {
  resource := input.resource_changes[_]
  resource.change.actions[_] in {"create", "update"}
  resource.change.after.tags == null
  not resource.change.after.labels   # don't double-fire on GCP resources

  msg := sprintf(
    "POLICY FAIL: '%s' has no tags block — required tags are: %v",
    [resource.address, required_keys_aws_azure]
  )
}

# GCP: enforce on resources that carry a "labels" attribute.
deny[msg] {
  resource := input.resource_changes[_]
  resource.change.actions[_] in {"create", "update"}
  labels := resource.change.after.labels
  labels != null

  missing := required_keys_gcp - {k | labels[k]}
  count(missing) > 0

  msg := sprintf(
    "POLICY FAIL: '%s' is missing required labels: %v",
    [resource.address, missing]
  )
}

deny[msg] {
  resource := input.resource_changes[_]
  resource.change.actions[_] in {"create", "update"}
  resource.change.after.labels == null
  not resource.change.after.tags   # don't double-fire on AWS/Azure resources

  msg := sprintf(
    "POLICY FAIL: '%s' has no labels block — required labels are: %v",
    [resource.address, required_keys_gcp]
  )
}
