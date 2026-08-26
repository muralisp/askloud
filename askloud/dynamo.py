"""
DynamoDB backend for CloudInventoryEngine.

When ASKLOUD_DYNAMODB_TABLE is set, the engine loads inventory records from
DynamoDB instead of local JSON files.  The records are converted to
the same flat-dict format used by DataLoader so the rest of the engine
(direct_search, execute_plan, LLM prompt) works without any other changes.

DynamoDB item layout (written by askloud_ingest.py / router_lambda.py):
  PK         = aws#ACCOUNT_ID#RESOURCE_TYPE  (e.g. aws#099878477985#aws_instance)
  SK         = REGION#RESOURCE_ID            (e.g. ap-south-1#i-0abc123def456789)
  normalized = tfstate attribute dict (snake_case keys)
  deleted    = bool (soft-delete flag; absent on older items means alive)
"""

from __future__ import annotations

import logging
import os
import time
from decimal import Decimal
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── Query cache ───────────────────────────────────────────────────────────────
# Each entry: cache_key → (monotonic_timestamp, records_list)
# Keyed by (table_name, engine_type) so different tables never collide.
_CACHE_TTL: float = float(os.environ.get("ASKLOUD_QUERY_CACHE_TTL", "60"))
_query_cache: dict[str, tuple[float, list]] = {}

# ── boto3 Table resource cache ────────────────────────────────────────────────
_table_cache: dict[tuple, Any] = {}


def clear_query_cache() -> None:
    """Flush the in-process query cache. Call after /reload or post-apply."""
    _query_cache.clear()


def _get_table(table_name: str, region: str, profile: Optional[str]):
    """Return a cached boto3 DynamoDB Table resource (avoids per-call Session overhead)."""
    import boto3
    key = (table_name, region, profile)
    if key not in _table_cache:
        session = boto3.Session(profile_name=profile) if profile else boto3.Session()
        _table_cache[key] = session.resource("dynamodb", region_name=region).Table(table_name)
    return _table_cache[key]

try:
    from .settings import ACCOUNT_ALIASES as _ACCOUNT_ALIASES
except ImportError:
    _ACCOUNT_ALIASES: dict[str, str] = {}  # fallback when loaded outside package


def _account_name(account_id: str) -> str:
    """Return friendly name for account_id, falling back to the raw ID."""
    return _ACCOUNT_ALIASES.get(account_id, account_id)


def _dedecimal(obj):
    """Recursively convert DynamoDB Decimal values to int or float."""
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    if isinstance(obj, dict):
        return {k: _dedecimal(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_dedecimal(i) for i in obj]
    return obj


# Terraform resource type → engine short key used in loader.data
_RESOURCE_TYPE_MAP: dict[str, str] = {
    # Compute
    "aws_instance":              "ec2",
    # Networking
    "aws_vpc":                   "vpc",
    "aws_subnet":                "subnet",
    "aws_internet_gateway":      "igw",
    "aws_nat_gateway":           "nat_gateway",
    "aws_eip":                   "eip",
    "aws_route_table":           "route_table",
    # Security
    "aws_security_group":        "security_group",
    # IAM
    "aws_iam_role":              "iam_role",
    # Container registry
    "aws_ecr_repository":        "ecr_repository",
    # Serverless / messaging
    "aws_lambda_function":       "lambda_function",
    "aws_sqs_queue":             "sqs_queue",
    "aws_dynamodb_table":        "dynamodb_table",
    # EventBridge / CloudWatch
    "aws_cloudwatch_event_bus":  "event_bus",
    "aws_cloudwatch_event_rule": "eventbridge_rule",
    "aws_cloudwatch_log_group":  "log_group",
}

# Reverse map: engine short key → Terraform resource type (for per-query DynamoDB)
_ENGINE_TO_TF: dict[str, str] = {v: k for k, v in _RESOURCE_TYPE_MAP.items()}


def _tags(normalized: dict) -> list:
    """Return tags as [{Key, Value}] list — same format as the AWS SDK and local JSON files."""
    t = normalized.get("tags")
    if isinstance(t, dict):
        return [{"Key": k, "Value": v} for k, v in t.items()]
    return []


def _to_engine_record(item: dict) -> dict:
    """
    Convert one DynamoDB item to the flat-dict format the engine expects in
    loader.data.

    normalized contains raw tfstate attributes (snake_case keys).  Each
    resource-type branch maps them to the PascalCase names that conf files,
    FIELD_ALIASES, and the LLM system prompt reference.
    """
    normalized    = item.get("normalized") or {}
    resource_type = item.get("resource_type", "")

    account_id = item.get("account_id", "")
    base = {
        "Account":     _account_name(account_id) if account_id else "N/A",
        "AccountId":   account_id or "N/A",
        "Region":      item.get("region",   "N/A"),
        "Provider":    item.get("provider", "aws"),
        "ingested_at": item.get("ingested_at", ""),
    }

    # ── EC2 instance ──────────────────────────────────────────────────────────
    if resource_type == "aws_instance":
        # vpc_security_group_ids = new tfstate format; security_groups = legacy adapter format
        sgs = (normalized.get("vpc_security_group_ids")
               or normalized.get("security_groups")
               or [])
        return {
            **base,
            "InstanceId":         item.get("resource_id", ""),
            "InstanceType":       normalized.get("instance_type", ""),
            "SubnetId":           normalized.get("subnet_id", ""),
            "SecurityGroupId":    sgs[0] if sgs else "",
            "KeyName":            normalized.get("key_name", ""),
            "ImageId":            normalized.get("ami", ""),
            "PrivateIpAddress":   normalized.get("private_ip", ""),
            "State":              {"Name": normalized.get("instance_state", "")},
            "IamInstanceProfile": normalized.get("iam_instance_profile") or None,
            "Tags":               _tags(normalized),
        }

    # ── VPC ───────────────────────────────────────────────────────────────────
    if resource_type == "aws_vpc":
        return {
            **base,
            "VpcId":     item.get("resource_id", ""),
            "CidrBlock": normalized.get("cidr_block", ""),
            "OwnerId":   normalized.get("owner_id", ""),
            "Tags":               _tags(normalized),
        }

    # ── Subnet ────────────────────────────────────────────────────────────────
    if resource_type == "aws_subnet":
        return {
            **base,
            "SubnetId":         item.get("resource_id", ""),
            "VpcId":            normalized.get("vpc_id", ""),
            "CidrBlock":        normalized.get("cidr_block", ""),
            "AvailabilityZone": normalized.get("availability_zone", ""),
            "Tags":               _tags(normalized),
        }

    # ── Internet gateway ──────────────────────────────────────────────────────
    if resource_type == "aws_internet_gateway":
        return {
            **base,
            "InternetGatewayId": item.get("resource_id", ""),
            "VpcId":             normalized.get("vpc_id", ""),
            "OwnerId":           normalized.get("owner_id", ""),
            "Tags":               _tags(normalized),
        }

    # ── NAT gateway ───────────────────────────────────────────────────────────
    if resource_type == "aws_nat_gateway":
        return {
            **base,
            "NatGatewayId":   item.get("resource_id", ""),
            "SubnetId":       normalized.get("subnet_id", ""),
            "PublicIp":       normalized.get("public_ip", ""),
            "PrivateIp":      normalized.get("private_ip", ""),
            "ConnectivityType": normalized.get("connectivity_type", ""),
            "Tags":               _tags(normalized),
        }

    # ── Elastic IP ────────────────────────────────────────────────────────────
    if resource_type == "aws_eip":
        return {
            **base,
            "AllocationId": item.get("resource_id", ""),
            "PublicIp":     normalized.get("public_ip", ""),
            "PrivateIp":    normalized.get("private_ip", ""),
            "InstanceId":   normalized.get("instance", ""),
            "Domain":       normalized.get("domain", ""),
            "Tags":               _tags(normalized),
        }

    # ── Route table ───────────────────────────────────────────────────────────
    if resource_type == "aws_route_table":
        return {
            **base,
            "RouteTableId": item.get("resource_id", ""),
            "VpcId":        normalized.get("vpc_id", ""),
            "OwnerId":      normalized.get("owner_id", ""),
            "Tags":               _tags(normalized),
        }

    # ── Security group ────────────────────────────────────────────────────────
    if resource_type == "aws_security_group":
        return {
            **base,
            "GroupId":     item.get("resource_id", ""),
            "GroupName":   normalized.get("name", ""),
            "Description": normalized.get("description", ""),
            "VpcId":       normalized.get("vpc_id", ""),
            "Tags":               _tags(normalized),
        }

    # ── ECR repository ───────────────────────────────────────────────────────
    if resource_type == "aws_ecr_repository":
        return {
            **base,
            "RepositoryName": item.get("resource_id", ""),
            "RepositoryUrl":  normalized.get("repository_url", ""),
            "ImageTagMutability": normalized.get("image_tag_mutability", ""),
            "Tags":               _tags(normalized),
        }

    # ── IAM role ─────────────────────────────────────────────────────────────
    if resource_type == "aws_iam_role":
        return {
            **base,
            "RoleName":    normalized.get("name", item.get("resource_id", "")),
            "RoleId":      item.get("resource_id", ""),
            "Arn":         normalized.get("arn", ""),
            "Description": normalized.get("description", ""),
            "CreateDate":  normalized.get("create_date", ""),
            "Tags":               _tags(normalized),
        }

    # ── Lambda function ───────────────────────────────────────────────────────
    if resource_type == "aws_lambda_function":
        return {
            **base,
            "FunctionName": item.get("resource_id", ""),
            "Runtime":      normalized.get("runtime", ""),
            "Handler":      normalized.get("handler", ""),
            "MemorySize":   normalized.get("memory_size", ""),
            "Timeout":      normalized.get("timeout", ""),
            "Arn":          normalized.get("arn", ""),
            "Tags":               _tags(normalized),
        }

    # ── SQS queue ─────────────────────────────────────────────────────────────
    if resource_type == "aws_sqs_queue":
        # resource_id is the queue URL; extract queue name from the ARN
        arn  = normalized.get("arn", "")
        name = arn.split(":")[-1] if arn else item.get("resource_id", "")
        return {
            **base,
            "QueueName":             name,
            "QueueUrl":              item.get("resource_id", ""),
            "Arn":                   arn,
            "DelaySeconds":          normalized.get("delay_seconds", 0),
            "VisibilityTimeoutSeconds": normalized.get("visibility_timeout_seconds", 30),
            "Tags":               _tags(normalized),
        }

    # ── DynamoDB table ────────────────────────────────────────────────────────
    if resource_type == "aws_dynamodb_table":
        return {
            **base,
            "TableName":  item.get("resource_id", ""),
            "BillingMode": normalized.get("billing_mode", ""),
            "HashKey":    normalized.get("hash_key", ""),
            "RangeKey":   normalized.get("range_key", ""),
            "Arn":        normalized.get("arn", ""),
            "Tags":               _tags(normalized),
        }

    # ── EventBridge custom bus ────────────────────────────────────────────────
    if resource_type == "aws_cloudwatch_event_bus":
        return {
            **base,
            "BusName": item.get("resource_id", ""),
            "Arn":     normalized.get("arn", ""),
            "Tags":               _tags(normalized),
        }

    # ── EventBridge rule ──────────────────────────────────────────────────────
    if resource_type == "aws_cloudwatch_event_rule":
        return {
            **base,
            "RuleName":     normalized.get("name", item.get("resource_id", "")),
            "Arn":          normalized.get("arn", ""),
            "State":        normalized.get("state", ""),
            "EventBusName": normalized.get("event_bus_name", ""),
            "Tags":               _tags(normalized),
        }

    # ── CloudWatch log group ──────────────────────────────────────────────────
    if resource_type == "aws_cloudwatch_log_group":
        return {
            **base,
            "LogGroupName":    item.get("resource_id", ""),
            "Arn":             normalized.get("arn", ""),
            "RetentionInDays": normalized.get("retention_in_days", 0),
            "Tags":               _tags(normalized),
        }

    # ── Generic fallback: surface resource_id + all normalized fields ─────────
    return {**base, "resource_id": item.get("resource_id", ""), **normalized}


def load_from_dynamodb(
    table_name: str,
    region: str,
    profile: Optional[str] = None,
) -> dict[str, list[dict]]:
    """
    Scan the Askloud DynamoDB inventory table and return records grouped by
    engine resource-type key (e.g. ``{"ec2": [...], "vpc": [...], ...}``).

    Only live items (``deleted`` absent or False) are returned.
    Pagination is handled automatically.

    Args:
        table_name: DynamoDB table name from ``ASKLOUD_DYNAMODB_TABLE``.
        region:     AWS region where the table lives.
        profile:    Optional AWS CLI profile name.  Omit to use the default
                    credential chain (env vars, instance role, etc.).

    Returns:
        Dict mapping engine resource key → list of engine-format record dicts.

    Raises:
        Any boto3/botocore exception so the caller can handle or surface it.
    """
    from boto3.dynamodb.conditions import Attr

    table  = _get_table(table_name, region, profile)
    result: dict[str, list[dict]] = {}
    scan_kwargs: dict = {
        "FilterExpression": Attr("deleted").eq(False) | Attr("deleted").not_exists(),
    }

    while True:
        response = table.scan(**scan_kwargs)
        for item in response.get("Items", []):
            item        = _dedecimal(item)
            raw_type    = item.get("resource_type", "unknown")
            engine_type = _RESOURCE_TYPE_MAP.get(raw_type, raw_type)
            result.setdefault(engine_type, []).append(_to_engine_record(item))

        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        scan_kwargs["ExclusiveStartKey"] = last_key

    total = sum(len(v) for v in result.values())
    logger.info("Loaded %d record(s) from DynamoDB table %s", total, table_name)
    return result


def load_schema_samples(
    table_name: str,
    region: str,
    profile: Optional[str] = None,
) -> dict[str, list[dict]]:
    """
    Fast startup scan: fetch one sample record per resource type for schema and
    field-map building.  Scans at most one DynamoDB page (Limit=300) so startup
    is near-instant regardless of table size.  Actual records are fetched
    per-query by query_resource().
    """
    from boto3.dynamodb.conditions import Attr

    table   = _get_table(table_name, region, profile)
    samples: dict[str, list[dict]] = {}
    response = table.scan(
        FilterExpression=Attr("deleted").eq(False) | Attr("deleted").not_exists(),
        Limit=300,
    )
    for item in response.get("Items", []):
        item        = _dedecimal(item)
        raw_type    = item.get("resource_type", "unknown")
        engine_type = _RESOURCE_TYPE_MAP.get(raw_type, raw_type)
        if engine_type not in samples:
            samples[engine_type] = [_to_engine_record(item)]

    logger.info("Schema samples: %d type(s) from table %s", len(samples), table_name)
    return samples


def query_resource(
    table_name: str,
    region: str,
    engine_type: str,
    profile: Optional[str] = None,
) -> list[dict]:
    """
    Fetch all live records of one resource type from DynamoDB.

    Fast path: Query by PK (``aws#ACCOUNT_ID#RESOURCE_TYPE``) for each account
    in ACCOUNT_ALIASES — reads only the relevant partition(s) instead of the
    whole table.  Falls back to a full Scan when no account IDs are configured.

    Results are cached in-process for _CACHE_TTL seconds so that multi-step
    plans and repeated queries within a session don't hit DynamoDB twice.
    """
    from boto3.dynamodb.conditions import Attr, Key

    cache_key = f"{table_name}:{engine_type}"
    cached = _query_cache.get(cache_key)
    if cached:
        ts, records = cached
        if time.monotonic() - ts < _CACHE_TTL:
            logger.debug("Cache hit for %s (%s)", engine_type, table_name)
            return records

    tf_type = _ENGINE_TO_TF.get(engine_type, engine_type)
    table   = _get_table(table_name, region, profile)
    records: list[dict] = []

    account_ids = list(_ACCOUNT_ALIASES.keys())
    if account_ids:
        # Query by partition key — O(result set) instead of O(table size)
        not_deleted = Attr("deleted").eq(False) | Attr("deleted").not_exists()
        for account_id in account_ids:
            pk = f"aws#{account_id}#{tf_type}"
            kwargs: dict = {
                "KeyConditionExpression": Key("PK").eq(pk),
                "FilterExpression":       not_deleted,
            }
            while True:
                response = table.query(**kwargs)
                for item in response.get("Items", []):
                    records.append(_to_engine_record(_dedecimal(item)))
                last_key = response.get("LastEvaluatedKey")
                if not last_key:
                    break
                kwargs["ExclusiveStartKey"] = last_key
    else:
        # No account aliases configured — fall back to full Scan
        kwargs = {
            "FilterExpression": (
                Attr("resource_type").eq(tf_type)
                & (Attr("deleted").eq(False) | Attr("deleted").not_exists())
            ),
        }
        while True:
            response = table.scan(**kwargs)
            for item in response.get("Items", []):
                records.append(_to_engine_record(_dedecimal(item)))
            last_key = response.get("LastEvaluatedKey")
            if not last_key:
                break
            kwargs["ExclusiveStartKey"] = last_key

    _query_cache[cache_key] = (time.monotonic(), records)
    logger.info("Fetched %d %s record(s) from %s (cached for %gs)", len(records), engine_type, table_name, _CACHE_TTL)
    return records
