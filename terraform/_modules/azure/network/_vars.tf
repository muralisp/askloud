# TODO: Implement Azure VNet + Subnet module
#
# Expected variables:
#   resource_group_name   string   — Azure resource group to deploy into
#   location              string   — Azure region (e.g. eastus)
#   vnet_cidr             string   — Address space, e.g. "10.20.0.0/16"
#   private_subnet_cidrs  list     — Subnets for AKS node pools
#   public_subnet_cidrs   list     — Subnets for public-facing resources
#   availability_zones    list     — Zones to span (e.g. ["1","2","3"])
