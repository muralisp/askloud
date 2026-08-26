data "aws_caller_identity" "current" {}

locals {
  account_id       = data.aws_caller_identity.current.account_id
  ecr_base_url     = "${local.account_id}.dkr.ecr.${var.region}.amazonaws.com"
  ecr_repositories = ["askloud-gui", "askloud-engine"]
}
