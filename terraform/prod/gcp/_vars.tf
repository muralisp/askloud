variable "project_id"    { type = string }
variable "project_number" { type = string }
variable "project_name"  { default = "askloud" }
variable "environment"   { default = "prod" }
variable "owner"         { default = "platform-team" }
variable "region"        { default = "asia-south1" }

# TODO: expand as GCP modules are implemented
# variable "vpc_cidr"             { default = "10.26.0.0/16" }
# variable "node_machine_type"    { default = "n2-standard-4" }
# variable "node_count"           { default = 3 }
# variable "min_node_count"       { default = 2 }
# variable "max_node_count"       { default = 6 }
