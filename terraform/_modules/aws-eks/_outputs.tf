output "cluster_name" {
  description = "EKS cluster name"
  value       = aws_eks_cluster.this.name
}

output "cluster_endpoint" {
  description = "EKS API server endpoint"
  value       = aws_eks_cluster.this.endpoint
}

output "cluster_certificate_authority_data" {
  description = "Base64-encoded CA certificate for the cluster"
  value       = aws_eks_cluster.this.certificate_authority[0].data
  sensitive   = true
}

output "cluster_version" {
  description = "Kubernetes version running on the cluster"
  value       = aws_eks_cluster.this.version
}

output "oidc_provider_arn" {
  description = "OIDC provider ARN — pass to any IRSA-enabled module"
  value       = aws_iam_openid_connect_provider.this.arn
}

output "oidc_provider" {
  description = "OIDC issuer URL without https:// — used in IAM trust policy conditions"
  value       = replace(aws_iam_openid_connect_provider.this.url, "https://", "")
}

output "cluster_security_group_id" {
  description = "Security group auto-created by EKS for the cluster"
  value       = aws_eks_cluster.this.vpc_config[0].cluster_security_group_id
}
