terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }

  backend "s3" {
    bucket         = "askloud-tfstate"
    key            = "dev/terraform.tfstate"
    region         = "ap-south-1"
    dynamodb_table = "askloud-tfstate-lock"
    encrypt        = true
  }
}

# aws provider default_tags enforces the required-tag policy at the provider
# level — every resource in this workspace inherits these four tags, satisfying
# the OPA policy in _policies/required_tags.rego without any per-resource boilerplate.
provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project     = var.project
      Environment = var.environment
      ManagedBy   = "terraform"
      Owner       = var.owner
    }
  }
}
