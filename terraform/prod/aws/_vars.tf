variable "project" {
  description = "Project name"
  type        = string
  default     = "askloud"
}

variable "environment" {
  description = "Deployment environment — locked to prod in this workspace"
  type        = string
  default     = "prod"
  validation {
    condition     = var.environment == "prod"
    error_message = "This configuration deploys the prod environment only."
  }
}

variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "owner" {
  description = "Team or individual responsible for this environment (used as a required tag)"
  type        = string
  default     = "platform-team"
}

# ── Networking ────────────────────────────────────────────────────────────────

variable "vpc_cidr" {
  description = "VPC CIDR block"
  type        = string
  default     = "10.15.0.0/16"
}

variable "public_subnet_cidrs" {
  description = "Public subnet CIDRs — one /24 per AZ"
  type        = list(string)
  default     = ["10.15.0.0/24", "10.15.1.0/24", "10.15.2.0/24"]
}

variable "private_subnet_cidrs" {
  description = "Private subnet CIDRs — /20 per AZ to accommodate EKS pod IPs"
  type        = list(string)
  default     = ["10.15.128.0/20", "10.15.144.0/20", "10.15.160.0/20"]
}

# ── EKS ───────────────────────────────────────────────────────────────────────

variable "kubernetes_version" {
  description = "Kubernetes version"
  type        = string
  default     = "1.31"
}

variable "node_instance_types" {
  description = "EC2 instance types for worker nodes"
  type        = list(string)
  default     = ["t3.large"]
}

variable "node_desired_size" {
  type    = number
  default = 3
}

variable "node_min_size" {
  type    = number
  default = 2
}

variable "node_max_size" {
  type    = number
  default = 5
}
