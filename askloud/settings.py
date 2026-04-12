"""
Central configuration: environment variables, model settings, and all
static lookup tables (aliases, dedup fields, noise filters, colors, CLI maps).
"""

import os

API_KEY  = os.environ.get("ANTHROPIC_API_KEY")
MODEL_ID = "claude-haiku-4-5-20251001"
DATA_DIR = "data"
CONFIG_DIR = "config"
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
}

# Unique-ID field per resource type — used for global deduplication and targeted refresh merges.
DEDUP_FIELDS = {
    "ec2":    "InstanceId",
    "vpc":    "VpcId",
    "subnet": "SubnetId",
    "gce":    "id",
    "vm":     "id",
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
PROMPT_MODE_COLOR = "\033[38;5;255m"   # lavender — wraps [snapshot: Xmin old] / [live]
PROMPT_ASK_COLOR  = "\033[38;5;255m"   # bright white — wraps "Ask >"

# CLI binary name and the flag that forces JSON output, per provider.
PROVIDER_CLI = {"aws": "aws", "azure": "az", "gcp": "gcloud"}
PROVIDER_OUTPUT_FLAG = {
    "aws":   ["--output", "json"],
    "azure": ["--output", "json"],
    "gcp":   ["--format", "json"],
}
