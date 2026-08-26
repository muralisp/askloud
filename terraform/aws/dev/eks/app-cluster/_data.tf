# Pull VPC outputs from the networking workspace state.
# Deploy networking/ first, then this workspace.
data "terraform_remote_state" "networking" {
  backend = "s3"
  config = {
    bucket         = "askloud-tfstate"
    key            = "dev/networking/terraform.tfstate"
    region         = "ap-south-1"
    dynamodb_table = "askloud-tfstate-lock"
    encrypt        = true
    profile        = "askloud_dev"
  }
}

locals {
  cluster_name    = "${var.project}-${var.environment}"
  vpc_id          = data.terraform_remote_state.networking.outputs.vpc_id
  private_subnets = data.terraform_remote_state.networking.outputs.private_subnet_ids
}
