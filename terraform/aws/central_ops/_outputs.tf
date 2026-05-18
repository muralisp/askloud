# ── EventBridge ───────────────────────────────────────────────────────────────

output "central_event_bus_arn" {
  description = "ARN of the Askloud central EventBridge bus. Supply this to workload account EventBridge rules as the cross-account target."
  value       = aws_cloudwatch_event_bus.central.arn
}

output "central_event_bus_name" {
  description = "Name of the Askloud central EventBridge bus"
  value       = aws_cloudwatch_event_bus.central.name
}

# ── SQS ───────────────────────────────────────────────────────────────────────

output "sqs_queue_url" {
  description = "URL of the Askloud ingestion SQS queue"
  value       = aws_sqs_queue.ingestion.id
}

output "sqs_queue_arn" {
  description = "ARN of the Askloud ingestion SQS queue"
  value       = aws_sqs_queue.ingestion.arn
}

output "sqs_dlq_arn" {
  description = "ARN of the ingestion Dead Letter Queue"
  value       = aws_sqs_queue.ingestion_dlq.arn
}

# ── DynamoDB ──────────────────────────────────────────────────────────────────

output "dynamodb_table_name" {
  description = "Name of the Askloud DynamoDB inventory table"
  value       = aws_dynamodb_table.inventory.name
}

output "dynamodb_table_arn" {
  description = "ARN of the Askloud DynamoDB inventory table"
  value       = aws_dynamodb_table.inventory.arn
}

# ── Lambda ────────────────────────────────────────────────────────────────────

output "diff_lambda_function_name" {
  description = "Name of the Diff Lambda function"
  value       = aws_lambda_function.diff.function_name
}

output "diff_lambda_function_arn" {
  description = "ARN of the Diff Lambda function"
  value       = aws_lambda_function.diff.arn
}

output "router_lambda_function_name" {
  description = "Name of the Router Lambda function"
  value       = aws_lambda_function.router.function_name
}

output "router_lambda_role_arn" {
  description = "IAM execution role ARN of the Router Lambda. Paste this into the workload account _vars_inventory.tf as router_lambda_role_arn — it becomes the only principal trusted to assume Askloud-Inventory-Reader."
  value       = aws_iam_role.router_lambda.arn
}
