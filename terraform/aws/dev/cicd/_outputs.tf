output "github_actions_role_arn" {
  description = "Add this as AWS_ROLE_ARN in GitHub repository secrets"
  value       = module.github_oidc.role_arn
}
