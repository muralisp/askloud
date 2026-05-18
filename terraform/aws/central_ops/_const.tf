terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
  }

  backend "s3" {
    bucket       = "askloud-central-ops-tfstate"   # bucket in the central ops account (803760314511)
    key          = "central_ops/terraform.tfstate"
    region       = "ap-south-1"
    use_lockfile = true
    encrypt      = true
    profile      = "askloud_central_ops"
  }
}

# default_tags propagates required-tag policy to every resource in this
# workspace, satisfying the OPA policy in _policies/required_tags.rego.
provider "aws" {
  region  = var.region
  profile = "askloud_central_ops"

  default_tags {
    tags = {
      Project     = var.project
      Environment = var.environment
      ManagedBy   = "terraform"
      Owner       = var.owner
    }
  }
}
