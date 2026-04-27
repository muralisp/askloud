# TODO: Implement Azure Container Registry module
#
# Expected variables:
#   registry_name         string   — globally unique ACR name (alphanumeric)
#   resource_group_name   string
#   location              string
#   sku                   string   — "Basic" | "Standard" | "Premium"
#   geo_replications      list     — list of secondary regions (Premium only)
#   image_retention_days  number   — days to keep untagged images
