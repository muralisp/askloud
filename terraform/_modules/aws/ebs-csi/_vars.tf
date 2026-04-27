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

variable "cluster_name" {
  description = "Name of the EKS cluster to install the addon into"
  type        = string
}

variable "oidc_provider_arn" {
  description = "OIDC provider ARN from the EKS module (used for IRSA trust policy)"
  type        = string
}

variable "oidc_provider" {
  description = "OIDC provider URL without https:// prefix (used in trust policy conditions)"
  type        = string
}

variable "tags" {
  description = "Additional tags merged onto every resource in this module"
  type        = map(string)
  default     = {}
}
