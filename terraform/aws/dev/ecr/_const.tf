terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    bucket         = "askloud-tfstate"
    key            = "dev/ecr/terraform.tfstate"
    region         = "ap-south-1"
    dynamodb_table = "askloud-tfstate-lock"
    encrypt        = true
    profile        = "askloud_dev"
  }
}

provider "aws" {
  region  = var.region
  profile = "askloud_dev"

  default_tags {
    tags = {
      Project     = var.project
      Environment = var.environment
      ManagedBy   = "terraform"
      Owner       = var.owner
    }
  }
}
