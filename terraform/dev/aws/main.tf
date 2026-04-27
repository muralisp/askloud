# ── VPC ───────────────────────────────────────────────────────────────────────
# Module version: 1.0.0  (see ../../_modules/aws/vpc/VERSION)

module "vpc" {
  source = "../../_modules/aws/vpc"

  project              = var.project
  environment          = var.environment
  vpc_cidr             = var.vpc_cidr
  availability_zones   = local.azs
  public_subnet_cidrs  = var.public_subnet_cidrs
  private_subnet_cidrs = var.private_subnet_cidrs
  single_nat_gateway   = true  # single NAT to keep dev costs low
  cluster_name         = local.cluster_name
}
