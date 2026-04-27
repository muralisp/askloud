output "iam_role_arn" {
  description = "IAM role ARN for the EBS CSI controller (used by the addon ServiceAccount)"
  value       = aws_iam_role.ebs_csi.arn
}
