variable "project" {
  description = "Project name"
  type        = string
  default     = "askloud"
}

variable "environment" {
  description = "Deployment environment — locked to dev in this workspace"
  type        = string
  default     = "dev"
  validation {
    condition     = var.environment == "dev"
    error_message = "This configuration deploys the dev environment only."
  }
}

variable "region" {
  description = "AWS region"
  type        = string
  default     = "ap-south-1"
}

variable "owner" {
  description = "Team or individual responsible for this environment (required tag)"
  type        = string
  default     = "platform-team"
}

variable "github_repo" {
  description = "GitHub repository in org/repo format — scopes OIDC trust to this repo only"
  type        = string
  default     = "muralisp/askloud"
}
