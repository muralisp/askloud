# ── EKS Cluster ───────────────────────────────────────────────────────────────
module "eks" {
  source = "../../../../_modules/aws/eks"

  project             = var.project
  environment         = var.environment
  cluster_name        = local.cluster_name
  kubernetes_version  = var.kubernetes_version
  vpc_id              = local.vpc_id
  subnet_ids          = local.private_subnets
  node_instance_types = var.node_instance_types
  node_desired_size   = var.node_desired_size
  node_min_size       = var.node_min_size
  node_max_size       = var.node_max_size
  node_disk_size      = 20
}

# ── EBS CSI Driver ────────────────────────────────────────────────────────────
# EBS volumes are ReadWriteOnce — the GUI pod and the collector CronJob must
# land on the same node. The collector CronJob in k8s/collector-cronjob.yaml
# uses podAffinity to enforce this.
module "ebs_csi" {
  source = "../../../../_modules/aws/ebs-csi"

  project           = var.project
  environment       = var.environment
  cluster_name      = module.eks.cluster_name
  oidc_provider_arn = module.eks.oidc_provider_arn
  oidc_provider     = module.eks.oidc_provider
}
