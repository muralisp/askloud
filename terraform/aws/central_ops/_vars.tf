variable "project" {
  description = "Project name — used in resource names and tags"
  type        = string
  default     = "askloud"
}

variable "environment" {
  description = "Deployment environment — locked to central_ops in this workspace"
  type        = string
  default     = "central-ops"
}

variable "region" {
  description = "AWS region for central operations resources"
  type        = string
  default     = "ap-south-1"
}

variable "owner" {
  description = "Team or individual responsible for this environment (required tag)"
  type        = string
  default     = "platform-team"
}

# ── Cross-account trust ───────────────────────────────────────────────────────

variable "allowed_workload_accounts" {
  description = "List of workload AWS account IDs permitted to PutEvents on the central bus. Set either this or allowed_org_id — not both."
  type        = list(string)
  default     = []
}

variable "allowed_org_id" {
  description = "AWS Organizations ID (e.g. o-abc123). When set, the bus policy trusts the entire org instead of individual account IDs."
  type        = string
  default     = ""

  validation {
    condition     = var.allowed_org_id == "" || can(regex("^o-[a-z0-9]{10,32}$", var.allowed_org_id))
    error_message = "allowed_org_id must be empty or a valid Organizations ID in the format o-xxxxxxxxxx."
  }
}

variable "workload_state_bucket_arns" {
  description = <<-EOT
    List of S3 bucket ARNs that hold Terraform remote state in workload accounts.
    The Diff Lambda needs s3:GetObject on these buckets to read tfstate files.
    Defaults to ["arn:aws:s3:::*"] (all buckets) — tighten in production by
    supplying explicit ARNs such as ["arn:aws:s3:::acme-dev-tfstate", ...].
  EOT
  type        = list(string)
  default     = ["arn:aws:s3:::*"]
}

# ── Operational knobs ─────────────────────────────────────────────────────────

variable "retention_days" {
  description = "CloudWatch Logs retention period in days for Lambda log groups"
  type        = number
  default     = 30

  validation {
    condition     = contains([1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1096, 1827, 3653], var.retention_days)
    error_message = "retention_days must be a value accepted by the CloudWatch Logs API."
  }
}

variable "lambda_timeout_seconds" {
  description = "Lambda function timeout in seconds. SQS visibility_timeout_seconds is set to 6× this value."
  type        = number
  default     = 30
}

variable "sqs_dlq_max_receive_count" {
  description = "Number of delivery attempts before a message is moved to the DLQ"
  type        = number
  default     = 3
}

variable "diff_lambda_memory_mb" {
  description = "Memory allocation in MB for the Diff Lambda"
  type        = number
  default     = 256
}

variable "router_lambda_memory_mb" {
  description = "Memory allocation in MB for the Router Lambda"
  type        = number
  default     = 512
}
