output "vpc_id" {
  description = "VPC ID — consumed by eks/*/  via terraform_remote_state"
  value       = module.vpc.vpc_id
}

output "vpc_cidr" {
  description = "VPC CIDR block"
  value       = module.vpc.vpc_cidr
}

output "public_subnet_ids" {
  description = "Public subnet IDs (one per AZ)"
  value       = module.vpc.public_subnet_ids
}

output "private_subnet_ids" {
  description = "Private subnet IDs (one per AZ) — used by EKS node groups"
  value       = module.vpc.private_subnet_ids
}

output "availability_zones" {
  description = "Availability zones in use"
  value       = local.azs
}
