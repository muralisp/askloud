data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}
data "aws_region" "current" {}

locals {
  name_prefix = "${var.project}-${var.environment}"
  account_id  = data.aws_caller_identity.current.account_id
  partition   = data.aws_partition.current.partition

  # SQS visibility timeout must be at least 6× the Lambda timeout so in-flight
  # messages remain hidden for the full processing window, preventing redelivery.
  sqs_visibility_timeout = var.lambda_timeout_seconds * 6
}
