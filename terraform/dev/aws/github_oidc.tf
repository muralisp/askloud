# ── GitHub Actions OIDC ───────────────────────────────────────────────────────
# Module version: 1.0.0  (see ../../_modules/aws/github-oidc/VERSION)
#
# After applying, copy the github_actions_role_arn output value into
# GitHub → Settings → Secrets → AWS_ROLE_ARN

module "github_oidc" {
  source = "../../_modules/aws/github-oidc"

  project     = var.project
  environment = var.environment

  # Replace with your GitHub org/repo (e.g. "muralisp/cloud-inventory-claude")
  github_repo = "muralisp/askloud"

  ecr_repository_arns = [
    for name in local.ecr_repositories :
    "arn:aws:ecr:${var.region}:${local.account_id}:repository/${name}"
  ]

  create_oidc_provider = true  # set false if prod shares this AWS account
}
