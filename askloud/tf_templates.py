"""
HCL template definitions for agentic resource creation.

Each entry in TEMPLATES defines:
  label        — human-readable resource type name
  render       — function(params: dict) -> HCL string
  params       — ordered list of parameter specs

Parameter spec keys:
  name                — key used in the params dict
  prompt              — text shown to the user
  required            — if True, must be provided; no default
  default             — value used when user presses Enter (optional params only)
  inventory_resource  — engine resource type to offer as a pick-list (e.g. "subnet")
  inventory_field     — field to extract as the value (e.g. "SubnetId")
  inventory_label     — callable(record) -> display string for the pick-list entry
"""

from __future__ import annotations
import re


def _to_resource_name(name: str) -> str:
    """Convert a human name to a valid Terraform resource label (snake_case)."""
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = s.strip("_")
    if s and s[0].isdigit():
        s = "r_" + s
    return s or "resource"


def _tag_name(record: dict) -> str:
    """Extract the Name tag from an inventory record (supports both dict and list tags)."""
    tags = record.get("tags") or record.get("Tags")
    if isinstance(tags, dict):
        return tags.get("Name", "")
    if isinstance(tags, list):
        for t in tags:
            if t.get("Key") == "Name":
                return t.get("Value", "")
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# EC2 instance
# ─────────────────────────────────────────────────────────────────────────────

def _hcl_value(v: str) -> str:
    """Return the correct HCL representation for a value.
    AMI IDs (ami-*) and plain strings get quoted; Terraform expressions do not."""
    v = v.strip()
    # Treat as a raw Terraform expression if it looks like one (contains dots, brackets,
    # or starts with a known reference prefix), otherwise quote it as a string literal.
    if v.startswith("ami-") or (not any(c in v for c in ".[(") and v != "null"):
        return f'"{v}"'
    return v


def _render_ec2(params: dict) -> str:
    resource_name = _to_resource_name(params["name"])
    key_line      = (f'  key_name = "{params["key_name"]}"'
                     if params.get("key_name")
                     else "  key_name = null")
    volume_size   = int(params.get("volume_size") or 8)
    ami_val       = _hcl_value(params.get("ami") or "data.aws_ami.al2023.id")

    return (
        f"\n# ── {params['name']} "
        + "─" * max(0, 60 - len(params["name"]))
        + "\n"
        f'resource "aws_instance" "{resource_name}" {{\n'
        f'  ami                         = {ami_val}\n'
        f'  instance_type               = "{params["instance_type"]}"\n'
        f'  subnet_id                   = "{params["subnet_id"]}"\n'
        f'  vpc_security_group_ids      = ["{params["sg_id"]}"]\n'
        f'  associate_public_ip_address = false\n'
        f'\n'
        f'{key_line}\n'
        f'\n'
        f'  root_block_device {{\n'
        f'    volume_type           = "gp3"\n'
        f'    volume_size           = {volume_size}\n'
        f'    delete_on_termination = true\n'
        f'    encrypted             = true\n'
        f'  }}\n'
        f'\n'
        f'  metadata_options {{\n'
        f'    http_tokens = "required"\n'
        f'  }}\n'
        f'\n'
        f'  tags = {{\n'
        f'    Name = "{params["name"]}"\n'
        f'  }}\n'
        f'}}\n'
    )


# ─────────────────────────────────────────────────────────────────────────────
# Security group
# ─────────────────────────────────────────────────────────────────────────────

def _render_security_group(params: dict) -> str:
    resource_name = _to_resource_name(params["name"])
    ingress_block = ""
    if params.get("ssh_cidr"):
        ingress_block = (
            f'\n  ingress {{\n'
            f'    description = "SSH"\n'
            f'    from_port   = 22\n'
            f'    to_port     = 22\n'
            f'    protocol    = "tcp"\n'
            f'    cidr_blocks = ["{params["ssh_cidr"]}"]\n'
            f'  }}\n'
        )

    return (
        f"\n# ── {params['name']} "
        + "─" * max(0, 60 - len(params["name"]))
        + "\n"
        f'resource "aws_security_group" "{resource_name}" {{\n'
        f'  name        = "{params["name"]}"\n'
        f'  description = "{params["description"]}"\n'
        f'  vpc_id      = "{params["vpc_id"]}"\n'
        f'{ingress_block}'
        f'\n  egress {{\n'
        f'    description = "Allow all outbound"\n'
        f'    from_port   = 0\n'
        f'    to_port     = 0\n'
        f'    protocol    = "-1"\n'
        f'    cidr_blocks = ["0.0.0.0/0"]\n'
        f'  }}\n'
        f'\n  tags = {{\n'
        f'    Name = "{params["name"]}"\n'
        f'  }}\n'
        f'}}\n'
    )


# ─────────────────────────────────────────────────────────────────────────────
# Template registry
# ─────────────────────────────────────────────────────────────────────────────

TEMPLATES: dict[str, dict] = {
    "ec2": {
        "label":  "EC2 Instance",
        "render": _render_ec2,
        "params": [
            {
                "name":     "name",
                "prompt":   "Instance name (used as Name tag and Terraform label)",
                "required": True,
            },
            {
                "name":     "instance_type",
                "prompt":   "Instance type",
                "required": False,
                "default":  "t3.micro",
            },
            {
                "name":     "ami",
                "prompt":   "AMI (data source ref or AMI ID)",
                "required": False,
                "default":  "data.aws_ami.al2023.id",
            },
            {
                "name":               "subnet_id",
                "prompt":             "Subnet ID",
                "required":           True,
                "inventory_resource": "subnet",
                "inventory_field":    "SubnetId",
                "inventory_label":    lambda r: (
                    f"{r.get('SubnetId', '?')}  "
                    f"cidr={r.get('CidrBlock', '?')}  "
                    f"az={r.get('AvailabilityZone', '?')}  "
                    f"name={_tag_name(r) or '—'}"
                ),
            },
            {
                "name":               "sg_id",
                "prompt":             "Security group ID",
                "required":           True,
                "inventory_resource": "security_group",
                "inventory_field":    "GroupId",
                "inventory_label":    lambda r: (
                    f"{r.get('GroupId', '?')}  "
                    f"({r.get('GroupName', '?')})  "
                    f"{r.get('Description', '')}"
                ),
            },
            {
                "name":     "key_name",
                "prompt":   "Key pair name (leave blank to skip)",
                "required": False,
                "default":  "",
            },
            {
                "name":     "volume_size",
                "prompt":   "Root volume size in GB",
                "required": False,
                "default":  "8",
            },
        ],
    },

    "security_group": {
        "label":  "Security Group",
        "render": _render_security_group,
        "params": [
            {
                "name":     "name",
                "prompt":   "Security group name",
                "required": True,
            },
            {
                "name":     "description",
                "prompt":   "Description",
                "required": False,
                "default":  "Managed by Terraform",
            },
            {
                "name":               "vpc_id",
                "prompt":             "VPC ID",
                "required":           True,
                "inventory_resource": "vpc",
                "inventory_field":    "VpcId",
                "inventory_label":    lambda r: (
                    f"{r.get('VpcId', '?')}  "
                    f"cidr={r.get('CidrBlock', '?')}  "
                    f"name={_tag_name(r) or '—'}"
                ),
            },
            {
                "name":     "ssh_cidr",
                "prompt":   "Allow SSH from CIDR (leave blank to skip ingress rule)",
                "required": False,
                "default":  "",
            },
        ],
    },
}
