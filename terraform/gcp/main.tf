# TODO: Instantiate GCP modules for the dev environment.
#
# Example wiring (uncomment and fill in once modules are implemented):
#
# module "vpc" {
#   source               = "../../_modules/gcp/vpc"
#   project_id           = var.project_id
#   region               = var.region
#   network_name         = "askloud-dev"
#   private_subnet_cidr  = "10.22.0.0/20"
#   pod_cidr             = "10.22.64.0/18"
#   service_cidr         = "10.22.128.0/22"
#   enable_private_nodes = true
# }
#
# module "artifact_registry" {
#   source          = "../../_modules/gcp/artifact-registry"
#   project_id      = var.project_id
#   location        = var.region
#   repository_id   = "askloud"
#   ...
# }
#
# module "gke" {
#   source            = "../../_modules/gcp/gke"
#   network_self_link = module.vpc.network_self_link
#   subnet_self_link   = module.vpc.subnet_self_link
#   ...
# }
#
# module "github_oidc" {
#   source          = "../../_modules/gcp/github-oidc"
#   project_id      = var.project_id
#   project_number  = var.project_number
#   github_repo     = "muralisp/askloud"
#   ...
# }
