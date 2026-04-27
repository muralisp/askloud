# ── GitHub Actions OIDC ───────────────────────────────────────────────────────
# Module version: 1.0.0  (see ../_modules/aws-github-oidc/VERSION)

module "github_oidc" {
  source = "../_modules/aws-github-oidc"

  project     = var.project
  environment = var.environment
  github_repo = "YOUR_ORG/YOUR_REPO"

  ecr_repository_arns = [
    for name in local.ecr_repositories :
    "arn:aws:ecr:${var.region}:${local.account_id}:repository/${name}"
  ]

  # OIDC provider already created by dev workspace — reuse it
  create_oidc_provider = false
}
