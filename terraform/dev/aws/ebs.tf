# ── EBS CSI Driver ────────────────────────────────────────────────────────────
# Module version: 1.0.0  (see ../../_modules/aws/ebs-csi/VERSION)
#
# EBS volumes are ReadWriteOnce — the GUI pod and the collector CronJob must
# land on the same node.  The collector CronJob in k8s/collector-cronjob.yaml
# uses podAffinity to enforce this.

module "ebs_csi" {
  source = "../../_modules/aws/ebs-csi"

  project           = var.project
  environment       = var.environment
  cluster_name      = module.eks.cluster_name
  oidc_provider_arn = module.eks.oidc_provider_arn
  oidc_provider     = module.eks.oidc_provider
}
