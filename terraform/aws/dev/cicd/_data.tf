data "aws_caller_identity" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id

  # ECR ARNs are constructed from known constants — no remote_state dependency
  # needed on the ecr/ workspace. Update this list if repositories change.
  ecr_repositories = ["askloud-gui", "askloud-engine"]
  ecr_repository_arns = [
    for name in local.ecr_repositories :
    "arn:aws:ecr:${var.region}:${local.account_id}:repository/${name}"
  ]
}
