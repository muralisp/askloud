output "cluster_name" {
  description = "EKS cluster name"
  value       = module.eks.cluster_name
}

output "cluster_endpoint" {
  description = "EKS API server endpoint"
  value       = module.eks.cluster_endpoint
}

output "configure_kubectl" {
  description = "Run this command to point kubectl at the app cluster"
  value       = "aws eks update-kubeconfig --region ${var.region} --name ${module.eks.cluster_name}"
}

output "oidc_provider_arn" {
  description = "OIDC provider ARN — consumed by IRSA-enabled workspaces via terraform_remote_state"
  value       = module.eks.oidc_provider_arn
}

output "oidc_provider" {
  description = "OIDC issuer URL without https://"
  value       = module.eks.oidc_provider
}

output "ebs_csi_role_arn" {
  description = "IAM role ARN for the EBS CSI driver"
  value       = module.ebs_csi.iam_role_arn
}
