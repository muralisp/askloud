variable "project_id"    { type = string }           # GCP project ID (required)
variable "project_number" { type = string }          # numeric, for Workload Identity pool name
variable "project_name"  { default = "askloud" }
variable "environment"   { default = "dev" }
variable "owner"         { default = "platform-team" }
variable "region"        { default = "asia-south1" }

# TODO: expand as GCP modules are implemented
# variable "vpc_cidr"             { default = "10.22.0.0/16" }
# variable "node_machine_type"    { default = "e2-standard-2" }
# variable "node_count"           { default = 2 }
# variable "min_node_count"       { default = 1 }
# variable "max_node_count"       { default = 3 }
