data "aws_caller_identity" "current" {}

# Latest Amazon Linux 2023 (x86_64) — owned by Amazon, not community
data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# Pull VPC outputs from the networking workspace state
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
  name      = "${var.project}-${var.environment}-test-inventory"
  vpc_id    = data.terraform_remote_state.networking.outputs.vpc_id
  subnet_id = data.terraform_remote_state.networking.outputs.public_subnet_ids[0]
}
