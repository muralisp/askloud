variable "project_name"  { default = "askloud" }
variable "environment"   { default = "dev" }
variable "owner"         { default = "platform-team" }
variable "location"      { default = "eastus" }

# TODO: expand variables as Azure modules are implemented
# variable "subscription_id"   { type = string }
# variable "tenant_id"         { type = string }
# variable "vnet_cidr"         { default = "10.21.0.0/16" }
# variable "node_vm_size"      { default = "Standard_D2s_v3" }
# variable "node_count"        { default = 2 }
# variable "min_count"         { default = 1 }
# variable "max_count"         { default = 3 }
