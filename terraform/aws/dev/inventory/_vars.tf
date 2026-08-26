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

# ── Cross-account wiring (values from central_ops outputs) ───────────────────

variable "central_account_id" {
  description = "AWS account ID of the Central Operations account"
  type        = string
}

variable "router_lambda_role_arn" {
  description = "IAM role ARN of the Router Lambda in the Central account — the only principal allowed to assume Askloud-Inventory-Reader"
  type        = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:iam::[0-9]{12}:role/.+$", var.router_lambda_role_arn))
    error_message = "router_lambda_role_arn must be a valid IAM role ARN."
  }
}

variable "central_event_bus_arn" {
  description = "ARN of the Askloud central EventBridge bus — .tfstate events are forwarded here"
  type        = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:events:.+:[0-9]{12}:event-bus/.+$", var.central_event_bus_arn))
    error_message = "central_event_bus_arn must be a valid EventBridge event bus ARN."
  }
}

variable "state_bucket_name" {
  description = "Name of the S3 bucket holding Terraform remote state for this account"
  type        = string
  default     = "askloud-tfstate"
}

variable "diff_lambda_role_arn" {
  description = "IAM role ARN of the Diff Lambda in the Central account — granted s3:GetObject on this account's tfstate bucket"
  type        = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:iam::[0-9]{12}:role/.+$", var.diff_lambda_role_arn))
    error_message = "diff_lambda_role_arn must be a valid IAM role ARN."
  }
}
