module "github_oidc" {
  source = "../../../_modules/aws/github-oidc"

  project     = var.project
  environment = var.environment
  github_repo = var.github_repo

  ecr_repository_arns = local.ecr_repository_arns

  create_oidc_provider = true # set false if prod shares this AWS account
}
