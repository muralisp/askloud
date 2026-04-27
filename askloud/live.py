"""
Live mode — real-time cloud data without sending any data to the LLM.

Flow:
  1. Single LLM call: NL query → JSON plan (CLI commands + display spec)
  2. Engine runs the CLI commands locally
  3. Engine extracts records via jmespath and renders the table

The LLM never sees any cloud data — only the user's question.

Public API:
  get_aws_profiles() -> list[str]          — profiles from ~/.aws/credentials
  build_live_system_prompt(profiles) -> str — system prompt for live mode
  execute_live_plan(plan) -> (records, errors)
"""

import os
import json
import subprocess
import configparser
from datetime import date

import jmespath

from .settings import CLI_TIMEOUT


# Keyed by the provider values the LLM uses in the plan
_CLI_BINARY = {
    "aws":    "aws",
    "az":     "az",
    "gcloud": "gcloud",
}

_OUTPUT_FLAGS = {
    "aws":    ["--output", "json"],
    "az":     ["--output", "json"],
    "gcloud": ["--format", "json"],
}


def get_aws_profiles() -> list:
    """Read available AWS profiles from ~/.aws/credentials."""
    creds_path = os.path.expanduser("~/.aws/credentials")
    if not os.path.exists(creds_path):
        return []
    config = configparser.ConfigParser()
    config.read(creds_path)
    return list(config.sections())


def build_live_system_prompt(profiles: list) -> str:
    profile_list = "\n".join(f"  - {p}" for p in profiles) if profiles else "  (none configured)"
    today = date.today()
    today_str = today.strftime("%Y-%m-%d")
    return f"""\
You are a Live Cloud CLI Translator. Given a natural language query, output a JSON plan \
that specifies which CLI commands to run and how to display the results as a table.

Output ONLY a raw JSON object — no markdown, no explanation.

## Available AWS Profiles
{profile_list}

## Output Format
{{
  "title":    "Human-readable table title",
  "provider": "aws" | "az" | "gcloud",
  "commands": [
    {{"provider": "aws|az|gcloud", "args": ["arg1", "arg2", ...]}}
  ],
  "extract": "jmespath expression applied to each command output to get the list of records",
  "columns": [
    {{"header": "Column Name", "path": "jmespath path within each record", "default": "N/A"}}
  ]
}}

## Current Date
Today is {today_str}. Use this to compute relative date ranges (e.g. "last month", "this year").

## Rules
- Do NOT include --output or --format flags in args (appended automatically).
- For AWS, always include --profile <profile> and --region <region> in args.
  Match user-facing names (e.g. "dev", "prod") to the closest profile listed above.
- For queries spanning multiple accounts or regions, list multiple commands — one per account/region.
- "extract" is a jmespath expression applied to each command's JSON output to produce a flat list of records.
  Omit "extract" when the CLI already returns a top-level JSON array.
- "columns" paths are jmespath expressions evaluated on each record individually.
- "provider" controls the table header color (aws / az / gcloud).

## extract values for common commands
- ec2 describe-instances        → "Reservations[].Instances[]"
- ec2 describe-volumes          → "Volumes[]"
- ec2 describe-vpcs             → "Vpcs[]"
- ec2 describe-subnets          → "Subnets[]"
- rds describe-db-instances     → "DBInstances[]"
- eks list-clusters             → "clusters[]"   (columns: [{{"header":"Cluster","path":"@"}}])
- s3api list-buckets            → "Buckets[]"
- ce get-cost-and-usage         → "ResultsByTime[].Groups[]"
- az vm list                    → (omit — root is already a list)
- az resource list              → (omit — root is already a list)
- gcloud compute instances list → (omit — root is already a list)

## Common AWS CLI Patterns
- EC2 instances:    ec2 describe-instances --region <r> --profile <p>
- Running only:     ec2 describe-instances --filters Name=instance-state-name,Values=running --region <r> --profile <p>
- Specific ID:      ec2 describe-instances --instance-ids <id> --region <r> --profile <p>
- VPCs:             ec2 describe-vpcs --region <r> --profile <p>
- RDS instances:    rds describe-db-instances --region <r> --profile <p>
- EKS clusters:     eks list-clusters --region <r> --profile <p>
- S3 buckets:       s3api list-buckets --profile <p>
- Cost (by service):  ce get-cost-and-usage --time-period Start=YYYY-MM-01,End=YYYY-MM-DD --granularity MONTHLY --metrics BlendedCost --group-by Type=DIMENSION,Key=SERVICE --profile <p>
- Cost (by resource): ce get-cost-and-usage --time-period Start=YYYY-MM-01,End=YYYY-MM-DD --granularity MONTHLY --metrics BlendedCost --group-by Type=DIMENSION,Key=RESOURCE_ID --profile <p>

## Common Azure CLI Patterns
- List VMs:             vm list
- List resources:       resource list
- Cost:                 consumption usage list --subscription <sub-id>

## Common GCP CLI Patterns
- List instances:   compute instances list --project <proj>
- List disks:       compute disks list --project <proj>
"""


def execute_live_plan(plan: dict) -> tuple:
    """
    Run the CLI commands in plan["commands"], extract records via plan["extract"],
    and return (records, errors, injected_keys).

    All --key value pairs from each command's args are injected into that command's
    records (e.g. profile="Dev-Data-Science", region="us-east-1").  The engine uses
    injected_keys to auto-prepend columns whose values differ across the result set.

    Cloud data never leaves the local machine — the LLM only produced the plan.
    """
    all_records: list   = []
    errors: list        = []
    injected_keys: set  = set()
    extract_expr        = plan.get("extract", "")

    for cmd_spec in plan.get("commands", []):
        provider  = cmd_spec.get("provider", "aws").lower()
        args      = [str(a) for a in cmd_spec.get("args", [])]
        flag_vals = _flag_values(args)   # e.g. {"profile": "Dev-DS", "region": "us-east-1"}
        injected_keys.update(flag_vals)

        cli = _CLI_BINARY.get(provider)
        if not cli:
            errors.append(f"Unsupported provider: {provider}")
            continue

        cmd = [cli] + args + _OUTPUT_FLAGS.get(provider, [])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=CLI_TIMEOUT)
        except FileNotFoundError:
            errors.append(f"CLI '{cli}' not found. Is it installed?")
            continue
        except subprocess.TimeoutExpired:
            errors.append(f"Command timed out after {CLI_TIMEOUT}s")
            continue

        if result.returncode != 0:
            errors.append(result.stderr.strip()[:300])
            continue

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            errors.append(f"Non-JSON output from: {' '.join(cmd[:4])}")
            continue

        if extract_expr:
            records = jmespath.search(extract_expr, data) or []
        elif isinstance(data, list):
            records = data
        else:
            records = [data]

        if isinstance(records, dict):
            records = [records]

        # Stamp every record from this command with the flag values
        if flag_vals:
            records = [{**r, **flag_vals} for r in records]

        all_records.extend(records)

    return all_records, errors, injected_keys


def _flag_values(args: list) -> dict:
    """
    Extract all --key value pairs from a CLI args list.
    Skips flags whose next token also starts with '--' (boolean flags).

    Example: ["ec2", "describe-volumes", "--region", "us-east-1", "--profile", "Prod"]
             → {"region": "us-east-1", "profile": "Prod"}
    """
    result = {}
    i = 0
    while i < len(args):
        if args[i].startswith("--") and i + 1 < len(args) and not args[i + 1].startswith("--"):
            key = args[i][2:]        # strip leading --
            result[key] = args[i + 1]
            i += 2
        else:
            i += 1
    return result
