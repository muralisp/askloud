module "ecr" {
  source = "../../../_modules/aws/ecr"

  project               = var.project
  environment           = var.environment
  repositories          = local.ecr_repositories
  image_retention_count = var.image_retention_count
}
