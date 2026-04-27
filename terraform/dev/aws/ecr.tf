# ── ECR Repositories ──────────────────────────────────────────────────────────
# Module version: 1.0.0  (see ../../_modules/aws/ecr/VERSION)

module "ecr" {
  source = "../../_modules/aws/ecr"

  project               = var.project
  environment           = var.environment
  repositories          = local.ecr_repositories
  image_retention_count = 10
}
