data "aws_caller_identity" "current" {}

data "aws_availability_zones" "available" {
  filter {
    name   = "opt-in-status"
    values = ["opt-in-not-required"]
  }
}

locals {
  cluster_name     = "${var.project}-${var.environment}"
  azs              = slice(data.aws_availability_zones.available.names, 0, 3)
  account_id       = data.aws_caller_identity.current.account_id
  ecr_base_url     = "${local.account_id}.dkr.ecr.${var.region}.amazonaws.com"
  ecr_repositories = ["askloud-gui", "askloud-engine"]
}
