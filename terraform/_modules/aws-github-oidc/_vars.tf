variable "project" {
  description = "Project name — used in resource naming"
  type        = string
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "environment must be one of: dev, prod"
  }
}

variable "github_repo" {
  description = "GitHub repository in org/repo format (e.g. myorg/askloud)"
  type        = string
}

variable "ecr_repository_arns" {
  description = "ECR repository ARNs the GitHub Actions role is allowed to push to"
  type        = list(string)
}

variable "create_oidc_provider" {
  description = "Create the GitHub OIDC provider. Set false when dev and prod share one AWS account (provider already exists)."
  type        = bool
  default     = true
}

variable "tags" {
  description = "Additional tags merged onto every resource"
  type        = map(string)
  default     = {}
}
