output "role_arn" {
  description = "IAM role ARN — add this as AWS_ROLE_ARN in GitHub repository secrets"
  value       = aws_iam_role.github_actions.arn
}
