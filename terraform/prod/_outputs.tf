output "cluster_name" {
  description = "EKS cluster name"
  value       = module.eks.cluster_name
}

output "configure_kubectl" {
  description = "Run this command to point kubectl at the prod cluster"
  value       = "aws eks update-kubeconfig --region ${var.region} --name ${module.eks.cluster_name}"
}

output "ecr_gui_url" {
  description = "ECR repository URL for askloud-gui"
  value       = module.ecr.repository_urls["askloud-gui"]
}

output "ecr_engine_url" {
  description = "ECR repository URL for askloud-engine"
  value       = module.ecr.repository_urls["askloud-engine"]
}

output "vpc_id" {
  description = "VPC ID"
  value       = module.vpc.vpc_id
}

output "ebs_csi_role_arn" {
  description = "IAM role ARN for the EBS CSI driver"
  value       = module.ebs_csi.iam_role_arn
}

output "github_actions_role_arn" {
  description = "Add this as AWS_ROLE_ARN in GitHub repository secrets"
  value       = module.github_oidc.role_arn
}
