output "inventory_reader_role_arn" {
  description = "ARN of the Askloud-Inventory-Reader role — for reference and auditing"
  value       = aws_iam_role.inventory_reader.arn
}

output "eventbridge_forwarding_rule_arn" {
  description = "ARN of the EventBridge rule that forwards .tfstate events to the central bus"
  value       = aws_cloudwatch_event_rule.forward_tfstate_events.arn
}
