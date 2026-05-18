# ─────────────────────────────────────────────────────────────────────────────
# DYNAMODB — Inventory Table
# ─────────────────────────────────────────────────────────────────────────────
resource "aws_dynamodb_table" "inventory" {
  name         = "${local.name_prefix}-inventory"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "PK"
  range_key    = "SK"

  attribute {
    name = "PK"
    type = "S"
  }

  attribute {
    name = "SK"
    type = "S"
  }

  # Native TTL: DynamoDB evaluates ttl_timestamp (Unix epoch) and automatically
  # removes items once the value is in the past. Deletion is eventually consistent
  # and free — no WCUs consumed.
  ttl {
    attribute_name = "ttl_timestamp"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }
}

# ─────────────────────────────────────────────────────────────────────────────
# SQS — Dead Letter Queue + Ingestion Queue
# ─────────────────────────────────────────────────────────────────────────────
resource "aws_sqs_queue" "ingestion_dlq" {
  name = "${local.name_prefix}-ingestion-dlq"

  # 14-day retention gives operators time to inspect and replay failed messages
  message_retention_seconds = 1209600
}

resource "aws_sqs_queue" "ingestion" {
  name = "${local.name_prefix}-ingestion"

  # 6× Lambda timeout keeps messages hidden for the full processing window.
  # If the Lambda does not delete the message within this window, SQS redelivers
  # it — the redrive policy sends it to the DLQ after maxReceiveCount attempts.
  visibility_timeout_seconds = local.sqs_visibility_timeout

  message_retention_seconds = 86400

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.ingestion_dlq.arn
    maxReceiveCount     = var.sqs_dlq_max_receive_count
  })
}

# Allow EventBridge to send messages to the ingestion queue directly
# (used as a fallback route or fan-out target from the central bus rule).
resource "aws_sqs_queue_policy" "ingestion" {
  queue_url = aws_sqs_queue.ingestion.id
  policy    = data.aws_iam_policy_document.sqs_ingestion_resource_policy.json
}

data "aws_iam_policy_document" "sqs_ingestion_resource_policy" {
  statement {
    sid    = "AllowEventBridgeSend"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }

    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.ingestion.arn]

    # Restrict to events originating from the Diff Lambda's EventBridge rule only
    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = [aws_cloudwatch_event_rule.tfstate_created.arn]
    }
  }
}

# ─────────────────────────────────────────────────────────────────────────────
# EVENTBRIDGE — Central Custom Bus
# ─────────────────────────────────────────────────────────────────────────────
resource "aws_cloudwatch_event_bus" "central" {
  name = "askloud-central-bus"
}

# Resource-based bus policy that authorises cross-account PutEvents.
# Without this, workload accounts cannot deliver events even if their IAM
# roles permit events:PutEvents — both ends must explicitly allow it.
# Skipped entirely when neither an org ID nor account IDs are supplied, which
# prevents EventBridge from receiving an empty (invalid) Principal array.
locals {
  has_bus_policy = var.allowed_org_id != "" || length(var.allowed_workload_accounts) > 0
}

resource "aws_cloudwatch_event_bus_policy" "central" {
  count          = local.has_bus_policy ? 1 : 0
  event_bus_name = aws_cloudwatch_event_bus.central.name

  policy = var.allowed_org_id != "" ? (
    data.aws_iam_policy_document.bus_policy_org[0].json
  ) : data.aws_iam_policy_document.bus_policy_accounts[0].json
}

# Option A: trust every account in the AWS Organization via a PrincipalOrgID
# condition. This scales automatically when new accounts are added to the org.
data "aws_iam_policy_document" "bus_policy_org" {
  count = var.allowed_org_id != "" ? 1 : 0

  statement {
    sid    = "AllowOrgPutEvents"
    effect = "Allow"

    principals {
      type        = "AWS"
      identifiers = ["*"]
    }

    actions   = ["events:PutEvents"]
    resources = [aws_cloudwatch_event_bus.central.arn]

    condition {
      test     = "StringEquals"
      variable = "aws:PrincipalOrgID"
      values   = [var.allowed_org_id]
    }
  }
}

# Option B: trust a finite list of explicitly-named workload account IDs.
# Only evaluated when the list is non-empty — an empty identifiers list is
# an invalid IAM policy that EventBridge rejects with ValidationException.
data "aws_iam_policy_document" "bus_policy_accounts" {
  count = length(var.allowed_workload_accounts) > 0 ? 1 : 0

  statement {
    sid    = "AllowWorkloadAccountsPutEvents"
    effect = "Allow"

    principals {
      type = "AWS"
      identifiers = [
        for id in var.allowed_workload_accounts :
        "arn:${local.partition}:iam::${id}:root"
      ]
    }

    actions   = ["events:PutEvents"]
    resources = [aws_cloudwatch_event_bus.central.arn]
  }
}

# ─────────────────────────────────────────────────────────────────────────────
# EVENTBRIDGE — Rule: .tfstate ObjectCreated → Diff Lambda
# ─────────────────────────────────────────────────────────────────────────────
resource "aws_cloudwatch_event_rule" "tfstate_created" {
  name           = "${local.name_prefix}-tfstate-created"
  description    = "Fires when a *.tfstate object is created in any workload account S3 bucket and forwarded here"
  event_bus_name = aws_cloudwatch_event_bus.central.name

  event_pattern = jsonencode({
    source      = ["aws.s3"]
    detail-type = ["Object Created"]
    detail = {
      object = {
        key = [{ suffix = ".tfstate" }]
      }
    }
  })
}

resource "aws_cloudwatch_event_target" "tfstate_to_diff_lambda" {
  rule           = aws_cloudwatch_event_rule.tfstate_created.name
  event_bus_name = aws_cloudwatch_event_bus.central.name
  target_id      = "DiffLambdaTarget"
  arn            = aws_lambda_function.diff.arn
}

# ─────────────────────────────────────────────────────────────────────────────
# CLOUDWATCH LOG GROUPS
# Pre-created so retention is enforced before the first Lambda invocation.
# ─────────────────────────────────────────────────────────────────────────────
resource "aws_cloudwatch_log_group" "diff_lambda" {
  name              = "/aws/lambda/${local.name_prefix}-diff"
  retention_in_days = var.retention_days
}

resource "aws_cloudwatch_log_group" "router_lambda" {
  name              = "/aws/lambda/${local.name_prefix}-router"
  retention_in_days = var.retention_days
}

# ─────────────────────────────────────────────────────────────────────────────
# IAM — Shared Lambda trust policy
# ─────────────────────────────────────────────────────────────────────────────
data "aws_iam_policy_document" "lambda_trust" {
  statement {
    sid    = "AllowLambdaService"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]
  }
}

# ─────────────────────────────────────────────────────────────────────────────
# IAM — Diff Lambda execution role
# ─────────────────────────────────────────────────────────────────────────────
resource "aws_iam_role" "diff_lambda" {
  name               = "${local.name_prefix}-diff-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
}

data "aws_iam_policy_document" "diff_lambda_permissions" {
  statement {
    sid    = "WriteLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    # Scoped to this function's log group only
    resources = ["${aws_cloudwatch_log_group.diff_lambda.arn}:*"]
  }

  # Scan live records scoped to the current workspace (by tfstate_key) to detect
  # resources that were destroyed and are absent from the new tfstate.
  statement {
    sid    = "DynamoDBDiff"
    effect = "Allow"
    actions = [
      "dynamodb:Scan",
    ]
    resources = [aws_dynamodb_table.inventory.arn]
  }

  # Fetch raw tfstate files from workload account S3 buckets.
  # Scoped to the ARNs in var.workload_state_bucket_arns (tighten in production).
  statement {
    sid     = "S3GetTFState"
    effect  = "Allow"
    actions = ["s3:GetObject"]
    resources = [
      for bucket_arn in var.workload_state_bucket_arns :
      "${bucket_arn}/*.tfstate"
    ]
  }

  # Publish diff events to the ingestion queue for downstream Router processing
  statement {
    sid       = "SQSSendDiffEvents"
    effect    = "Allow"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.ingestion.arn]
  }
}

resource "aws_iam_role_policy" "diff_lambda" {
  name   = "${local.name_prefix}-diff-lambda-policy"
  role   = aws_iam_role.diff_lambda.id
  policy = data.aws_iam_policy_document.diff_lambda_permissions.json
}

resource "aws_iam_role_policy_attachment" "diff_lambda_basic_execution" {
  role       = aws_iam_role.diff_lambda.name
  policy_arn = "arn:${local.partition}:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# ─────────────────────────────────────────────────────────────────────────────
# IAM — Router Lambda execution role
# ─────────────────────────────────────────────────────────────────────────────
resource "aws_iam_role" "router_lambda" {
  name               = "${local.name_prefix}-router-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
}

data "aws_iam_policy_document" "router_lambda_permissions" {
  statement {
    sid    = "WriteLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["${aws_cloudwatch_log_group.router_lambda.arn}:*"]
  }

  # Consume messages from the SQS trigger source
  statement {
    sid    = "SQSConsume"
    effect = "Allow"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
      "sqs:ChangeMessageVisibility",
    ]
    resources = [aws_sqs_queue.ingestion.arn]
  }

  # Persist discovered resources and update existing items with new TTLs
  statement {
    sid    = "DynamoDBWrite"
    effect = "Allow"
    actions = [
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:BatchWriteItem",
      "dynamodb:DeleteItem",
    ]
    resources = [aws_dynamodb_table.inventory.arn]
  }

  # Cross-account token exchange: assume the read-only inventory role in any
  # workload account. The Router calls sts:AssumeRole → receives a temporary
  # credential set (max 1 hour) → scans the workload account → credentials expire.
  # No long-lived secrets are stored or forwarded to the LLM.
  statement {
    sid     = "AssumeInventoryReaderRole"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    resources = [
      "arn:${local.partition}:iam::*:role/Askloud-Inventory-Reader"
    ]
  }
}

resource "aws_iam_role_policy" "router_lambda" {
  name   = "${local.name_prefix}-router-lambda-policy"
  role   = aws_iam_role.router_lambda.id
  policy = data.aws_iam_policy_document.router_lambda_permissions.json
}

resource "aws_iam_role_policy_attachment" "router_lambda_basic_execution" {
  role       = aws_iam_role.router_lambda.name
  policy_arn = "arn:${local.partition}:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# ─────────────────────────────────────────────────────────────────────────────
# LAMBDA — Diff Function
# Triggered by EventBridge when a *.tfstate file is created in a workload bucket.
# Reads tfstate attributes directly from S3 and publishes UPSERT events to SQS.
# ─────────────────────────────────────────────────────────────────────────────
data "archive_file" "diff" {
  type        = "zip"
  source_file = "${path.module}/../../diff_lambda.py"
  output_path = "/tmp/${local.name_prefix}-diff.zip"
}

resource "aws_lambda_function" "diff" {
  function_name = "${local.name_prefix}-diff"
  description   = "Reads tfstate on S3 upload and publishes resource events to the ingestion queue"
  role          = aws_iam_role.diff_lambda.arn
  runtime       = "python3.12"
  handler       = "diff_lambda.lambda_handler"
  timeout       = var.lambda_timeout_seconds
  memory_size   = var.diff_lambda_memory_mb

  filename         = data.archive_file.diff.output_path
  source_code_hash = data.archive_file.diff.output_base64sha256

  environment {
    variables = {
      DYNAMODB_TABLE = aws_dynamodb_table.inventory.name
      SQS_QUEUE_URL  = aws_sqs_queue.ingestion.id
    }
  }

  # Log group must exist before Lambda creates its first log stream
  depends_on = [
    aws_cloudwatch_log_group.diff_lambda,
    aws_iam_role_policy.diff_lambda,
  ]
}

# Grant EventBridge permission to invoke the Diff Lambda from the central bus rule
resource "aws_lambda_permission" "eventbridge_invoke_diff" {
  statement_id  = "AllowCentralBusInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.diff.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.tfstate_created.arn
}

# ─────────────────────────────────────────────────────────────────────────────
# LAMBDA — Router Function
# Triggered by SQS; writes resource events to DynamoDB with fingerprint-based
# idempotency.  No live AWS API calls — normalized data arrives in the message.
# ─────────────────────────────────────────────────────────────────────────────
data "archive_file" "router" {
  type        = "zip"
  source_file = "${path.module}/../../router_lambda.py"
  output_path = "/tmp/${local.name_prefix}-router.zip"
}

resource "aws_lambda_function" "router" {
  function_name = "${local.name_prefix}-router"
  description   = "Consumes SQS inventory events and persists resources to DynamoDB"
  role          = aws_iam_role.router_lambda.arn
  runtime       = "python3.12"
  handler       = "router_lambda.lambda_handler"
  timeout       = var.lambda_timeout_seconds
  memory_size   = var.router_lambda_memory_mb

  filename         = data.archive_file.router.output_path
  source_code_hash = data.archive_file.router.output_base64sha256

  environment {
    variables = {
      DYNAMODB_TABLE = aws_dynamodb_table.inventory.name
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.router_lambda,
    aws_iam_role_policy.router_lambda,
  ]
}

# SQS → Router Lambda event source mapping.
# ReportBatchItemFailures lets the Lambda return a list of failed message IDs;
# only those messages are re-enqueued instead of the whole batch.
resource "aws_lambda_event_source_mapping" "sqs_to_router" {
  event_source_arn                   = aws_sqs_queue.ingestion.arn
  function_name                      = aws_lambda_function.router.arn
  batch_size                         = 10
  maximum_batching_window_in_seconds = 30
  enabled                            = true

  function_response_types = ["ReportBatchItemFailures"]
}

# ─────────────────────────────────────────────────────────────────────────────
# EVENTBRIDGE — Rule: EC2 terminal state-change → EC2 Events Lambda
# Catches instances terminated via any mechanism (console, CLI, autoscaling,
# or terraform destroy) forwarded from workload account default buses.
# ─────────────────────────────────────────────────────────────────────────────
resource "aws_cloudwatch_event_rule" "ec2_terminated" {
  name           = "${local.name_prefix}-ec2-terminated"
  description    = "Fires when an EC2 instance reaches shutting-down or terminated state on the central bus"
  event_bus_name = aws_cloudwatch_event_bus.central.name

  event_pattern = jsonencode({
    source      = ["aws.ec2"]
    detail-type = ["EC2 Instance State-change Notification"]
    detail = {
      state = ["shutting-down", "terminated"]
    }
  })
}

resource "aws_cloudwatch_event_target" "ec2_terminated_to_lambda" {
  rule           = aws_cloudwatch_event_rule.ec2_terminated.name
  event_bus_name = aws_cloudwatch_event_bus.central.name
  target_id      = "EC2EventsLambdaTarget"
  arn            = aws_lambda_function.ec2_events.arn
}

# ─────────────────────────────────────────────────────────────────────────────
# CLOUDWATCH LOG GROUP — EC2 Events Lambda
# ─────────────────────────────────────────────────────────────────────────────
resource "aws_cloudwatch_log_group" "ec2_events_lambda" {
  name              = "/aws/lambda/${local.name_prefix}-ec2-events"
  retention_in_days = var.retention_days
}

# ─────────────────────────────────────────────────────────────────────────────
# IAM — EC2 Events Lambda execution role
# ─────────────────────────────────────────────────────────────────────────────
resource "aws_iam_role" "ec2_events_lambda" {
  name               = "${local.name_prefix}-ec2-events-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
}

data "aws_iam_policy_document" "ec2_events_lambda_permissions" {
  statement {
    sid    = "WriteLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["${aws_cloudwatch_log_group.ec2_events_lambda.arn}:*"]
  }

  statement {
    sid       = "SQSSendDeleteEvents"
    effect    = "Allow"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.ingestion.arn]
  }
}

resource "aws_iam_role_policy" "ec2_events_lambda" {
  name   = "${local.name_prefix}-ec2-events-lambda-policy"
  role   = aws_iam_role.ec2_events_lambda.id
  policy = data.aws_iam_policy_document.ec2_events_lambda_permissions.json
}

resource "aws_iam_role_policy_attachment" "ec2_events_lambda_basic_execution" {
  role       = aws_iam_role.ec2_events_lambda.name
  policy_arn = "arn:${local.partition}:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# ─────────────────────────────────────────────────────────────────────────────
# LAMBDA — EC2 Events Function
# Triggered by EventBridge when an EC2 instance reaches a terminal state.
# Publishes a DELETE message to the ingestion queue; the Router Lambda then
# soft-deletes the DynamoDB record.
# ─────────────────────────────────────────────────────────────────────────────
data "archive_file" "ec2_events" {
  type        = "zip"
  source_file = "${path.module}/../../ec2_events_lambda.py"
  output_path = "/tmp/${local.name_prefix}-ec2-events.zip"
}

resource "aws_lambda_function" "ec2_events" {
  function_name = "${local.name_prefix}-ec2-events"
  description   = "Soft-deletes DynamoDB inventory records when EC2 instances are terminated"
  role          = aws_iam_role.ec2_events_lambda.arn
  runtime       = "python3.12"
  handler       = "ec2_events_lambda.lambda_handler"
  timeout       = var.lambda_timeout_seconds
  memory_size   = var.diff_lambda_memory_mb

  filename         = data.archive_file.ec2_events.output_path
  source_code_hash = data.archive_file.ec2_events.output_base64sha256

  environment {
    variables = {
      SQS_QUEUE_URL = aws_sqs_queue.ingestion.id
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.ec2_events_lambda,
    aws_iam_role_policy.ec2_events_lambda,
  ]
}

resource "aws_lambda_permission" "eventbridge_invoke_ec2_events" {
  statement_id  = "AllowCentralBusInvokeEC2Events"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ec2_events.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.ec2_terminated.arn
}
