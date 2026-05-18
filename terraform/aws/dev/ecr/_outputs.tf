output "ecr_gui_url" {
  description = "ECR repository URL for askloud-gui"
  value       = module.ecr.repository_urls["askloud-gui"]
}

output "ecr_engine_url" {
  description = "ECR repository URL for askloud-engine"
  value       = module.ecr.repository_urls["askloud-engine"]
}

output "ecr_base_url" {
  description = "ECR registry base URL (account.dkr.ecr.region.amazonaws.com)"
  value       = local.ecr_base_url
}

output "repository_urls" {
  description = "Map of all ECR repository name → URL"
  value       = module.ecr.repository_urls
}
