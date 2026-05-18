"""
Central configuration: environment variables, model settings, and all
static lookup tables (aliases, dedup fields, noise filters, colors, CLI maps).
"""

import os

API_KEY  = os.environ.get("ANTHROPIC_API_KEY")
MODEL_ID = "claude-haiku-4-5-20251001"
DATA_DIR = "data"
CONFIG_DIR = "config"

# DynamoDB backend — when set, the engine loads inventory from DynamoDB
# instead of local JSON files.
DYNAMODB_TABLE   = os.environ.get("ASKLOUD_DYNAMODB_TABLE",   "askloud-central-ops-inventory")
DYNAMODB_REGION  = os.environ.get("ASKLOUD_DYNAMODB_REGION",  "ap-south-1")
DYNAMODB_PROFILE = os.environ.get("ASKLOUD_DYNAMODB_PROFILE", "askloud_central_ops")

# Account ID → friendly name used as the Account field in DynamoDB mode.
# Mirrors the directory-name convention used in local file mode.
# Override via env var as JSON: ASKLOUD_ACCOUNT_ALIASES='{"123456789012":"prod"}'
import json as _json
_alias_env = os.environ.get("ASKLOUD_ACCOUNT_ALIASES", "")
ACCOUNT_ALIASES: dict[str, str] = _json.loads(_alias_env) if _alias_env else {
    "099878477985": "dev",
    "803760314511": "central-ops",
}
MAX_HISTORY_TURNS  = 10
CLI_TIMEOUT        = 120  # seconds per subprocess call
MAX_LIVE_RETRIES   = 2    # max error-feedback retries in live mode

TOKEN_PRICES = {
    "claude-haiku-4-5-20251001": {"input": 0.80,  "output": 4.00,  "cache_write": 1.00,  "cache_read": 0.08},
    "claude-sonnet-4-6":         {"input": 3.00,  "output": 15.00, "cache_write": 3.75,  "cache_read": 0.30},
    "claude-opus-4-6":           {"input": 15.00, "output": 75.00, "cache_write": 18.75, "cache_read": 1.50},
}

# Config field name → jmespath path for fields that don't auto-resolve.
# Keys are lowercase for case-insensitive lookup. "*" applies to all resource types.
FIELD_ALIASES = {
    "*": {
        "account":  "Account",
        "region":   "Region",
        "provider": "Provider",
    },
    "ec2": {
        "instanceid":    "InstanceId",
        "instancetype":  "InstanceType",
        "instancestate": "State.Name",
        "privateip":     "PrivateIpAddress",
        "publicip":      "PublicIpAddress",
        "zone":          "Placement.AvailabilityZone",
        "subnetid":      "SubnetId",
        "vpcid":         "VpcId",
        "keyname":       "KeyName",
        "launchtime":    "LaunchTime",
        "imageid":       "ImageId",
    },
    "vpc": {
        "vpcid":     "VpcId",
        "cidrblock": "CidrBlock",
        "ownerid":   "OwnerId",
    },
    "subnet": {
        "subnetid":         "SubnetId",
        "cidrblock":        "CidrBlock",
        "vpcid":            "VpcId",
        "availabilityzone": "AvailabilityZone",
    },
    "vm": {
        "computername": "osProfile.computerName",
        "vmsize":       "hardwareProfile.vmSize",
        "ostype":       "storageProfile.osDisk.osType",
    },
    "security_group": {
        "groupid":   "GroupId",
        "groupname": "GroupName",
        "vpcid":     "VpcId",
    },
    "iam_role": {
        "rolename": "RoleName",
        "roleid":   "RoleId",
    },
    "nat_gateway": {
        "natgatewayid": "NatGatewayId",
        "subnetid":     "SubnetId",
        "publicip":     "PublicIp",
        "privateip":    "PrivateIp",
    },
    "igw": {
        "internetgatewayid": "InternetGatewayId",
        "vpcid":             "VpcId",
    },
    "eip": {
        "allocationid": "AllocationId",
        "publicip":     "PublicIp",
    },
    "route_table": {
        "routetableid": "RouteTableId",
        "vpcid":        "VpcId",
    },
    "lambda_function": {
        "functionname": "FunctionName",
        "runtime":      "Runtime",
    },
    "sqs_queue": {
        "queuename": "QueueName",
        "queueurl":  "QueueUrl",
    },
    "dynamodb_table": {
        "tablename":   "TableName",
        "billingmode": "BillingMode",
    },
    "ecr_repository": {
        "repositoryname": "RepositoryName",
        "repositoryurl":  "RepositoryUrl",
    },
    "event_bus": {
        "busname": "BusName",
    },
    "eventbridge_rule": {
        "rulename":     "RuleName",
        "state":        "State",
        "eventbusname": "EventBusName",
    },
    "log_group": {
        "loggroupname": "LogGroupName",
    },
}

# Unique-ID field per resource type — used for global deduplication and targeted refresh merges.
DEDUP_FIELDS = {
    "ec2":             "InstanceId",
    "vpc":             "VpcId",
    "subnet":          "SubnetId",
    "security_group":  "GroupId",
    "iam_role":        "RoleId",
    "igw":             "InternetGatewayId",
    "nat_gateway":     "NatGatewayId",
    "eip":             "AllocationId",
    "route_table":     "RouteTableId",
    "lambda_function": "FunctionName",
    "sqs_queue":       "QueueName",
    "dynamodb_table":  "TableName",
    "event_bus":       "BusName",
    "eventbridge_rule": "RuleName",
    "log_group":       "LogGroupName",
    "ecr_repository":  "RepositoryName",
    "gce":             "id",
    "vm":              "id",
}

# System/internal tag key prefixes stripped from the LLM schema to reduce input tokens.
# Tag keys referenced in a config file are always kept regardless of this list.
NOISE_TAG_PREFIXES = (
    "aws:",
    "k8s.io/",
    "kubernetes.io/",
    "karpenter.",
    "karpenter.sh/",
    "karpenter.k8s.aws/",
    "elasticbeanstalk:",
    "eks:",
)

# 256-colour ANSI codes approximating each provider's brand colour.
PROVIDER_COLORS = {
    "aws":   "\033[38;5;214m",   # orange  (#FF9900)
    "azure": "\033[38;5;39m",    # blue    (#0078D4)
    "gcp":   "\033[38;5;77m",    # green   (#34A853)
}
ANSI_RESET = "\033[0m"

# Prompt colors — change these to restyle the interactive prompt.
# Use standard ANSI codes or 256-color: \033[38;5;<0-255>m
PROMPT_MODE_COLOR = "\033[38;5;255m"   # lavender — wraps [inventory] / [live]
PROMPT_ASK_COLOR  = "\033[38;5;255m"   # bright white — wraps "Ask >"

# CLI binary name and the flag that forces JSON output, per provider.
PROVIDER_CLI = {"aws": "aws", "azure": "az", "gcp": "gcloud"}
PROVIDER_OUTPUT_FLAG = {
    "aws":   ["--output", "json"],
    "azure": ["--output", "json"],
    "gcp":   ["--format", "json"],
}
