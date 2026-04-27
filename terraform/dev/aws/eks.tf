# ── EKS Cluster ───────────────────────────────────────────────────────────────
# Module version: 1.0.0  (see ../../_modules/aws/eks/VERSION)

module "eks" {
  source = "../../_modules/aws/eks"

  project             = var.project
  environment         = var.environment
  cluster_name        = local.cluster_name
  kubernetes_version  = var.kubernetes_version
  vpc_id              = module.vpc.vpc_id
  subnet_ids          = module.vpc.private_subnet_ids
  node_instance_types = var.node_instance_types
  node_desired_size   = var.node_desired_size
  node_min_size       = var.node_min_size
  node_max_size       = var.node_max_size
  node_disk_size      = 20
}
