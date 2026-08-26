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

variable "vpc_cidr" {
  description = "VPC CIDR block"
  type        = string
  default     = "10.11.0.0/16"
}

variable "public_subnet_cidrs" {
  description = "Public subnet CIDRs — one /24 per AZ"
  type        = list(string)
  default     = ["10.11.0.0/24", "10.11.1.0/24", "10.11.2.0/24"]
}

variable "private_subnet_cidrs" {
  description = "Private subnet CIDRs — /20 per AZ to accommodate EKS pod IPs"
  type        = list(string)
  default     = ["10.11.128.0/20", "10.11.144.0/20", "10.11.160.0/20"]
}
