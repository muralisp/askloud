#!/usr/bin/env python3
"""
askloud_ingest.py — Manual pipeline trigger.

Reads Terraform state files from S3 and writes all managed resources to the
Askloud DynamoDB inventory table, bypassing the Lambda pipeline for bootstrap
or manual refresh.

Resource attributes are taken directly from tfstate (no live API calls).
Sub-resources (policy attachments, route-table associations, event targets,
bucket notifications) are skipped automatically.

Usage:
    # Ingest all tfstate files under a prefix
    python3 askloud_ingest.py --bucket askloud-tfstate --prefix dev/

    # Ingest a single tfstate file
    python3 askloud_ingest.py --bucket askloud-tfstate \\
        --key dev/ec2/test-inventory/terraform.tfstate

    # Dry-run: print what would be written without touching DynamoDB
    python3 askloud_ingest.py --bucket askloud-tfstate --prefix dev/ --dry-run

    # Ingest central ops state (different bucket and profile)
    python3 askloud_ingest.py \\
        --bucket askloud-central-ops-tfstate \\
        --prefix central_ops/ \\
        --state-profile askloud_central_ops

Environment variables (override CLI defaults):
    ASKLOUD_DYNAMODB_TABLE    DynamoDB table name
    ASKLOUD_DYNAMODB_REGION   DynamoDB table region   (default: ap-south-1)
    ASKLOUD_DYNAMODB_PROFILE  AWS profile for DynamoDB writes
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from typing import Iterator

import boto3
import botocore.exceptions

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ── Resource types to skip (sub-resources / bindings / triggers) ──────────────
# These are relational/policy resources with no standalone inventory value.
_SKIP_TYPES = frozenset({
    "aws_iam_role_policy",
    "aws_iam_role_policy_attachment",
    "aws_iam_instance_profile",
    "aws_route_table_association",
    "aws_main_route_table_association",
    "aws_cloudwatch_event_target",
    "aws_cloudwatch_event_bus_policy",
    "aws_s3_bucket_notification",
    "aws_lambda_event_source_mapping",
    "aws_lambda_permission",
    "aws_sqs_queue_policy",
    "aws_security_group_rule",
    "aws_vpc_security_group_ingress_rule",
    "aws_vpc_security_group_egress_rule",
})

# Terraform-internal attribute keys to strip before storing as normalized data
_DROP_ATTRS = frozenset({
    "timeouts",
    "tags_all",   # merged tags including provider default_tags — redundant with tags
})

_SOFT_DELETE_TTL_SECONDS = 604_800  # 7 days


# ── DynamoDB key helpers (must match router_lambda.py) ────────────────────────

def _pk(provider: str, account_id: str, resource_type: str) -> str:
    return f"{provider}#{account_id}#{resource_type}"


def _sk(region: str, resource_id: str) -> str:
    return f"{region}#{resource_id}"


# ── ARN parser ────────────────────────────────────────────────────────────────

def _parse_arn(arn: str) -> tuple[str, str]:
    """
    Extract (account_id, region) from an AWS ARN.
    ARN format: arn:partition:service:region:account-id:resource
    IAM ARNs have an empty region field.
    """
    parts = arn.split(":")
    if len(parts) < 6:
        raise ValueError(f"Cannot parse ARN: {arn!r}")
    return parts[4], parts[3]   # account_id, region


# ── S3 tfstate reader ─────────────────────────────────────────────────────────

def _iter_tfstate_keys(
    s3_client,
    bucket: str,
    prefix: str = "",
    specific_key: str = "",
) -> Iterator[str]:
    """Yield S3 keys for every *.tfstate file under the given prefix."""
    if specific_key:
        yield specific_key
        return
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith(".tfstate"):
                yield key


def _read_tfstate(s3_client, bucket: str, key: str) -> dict:
    resp = s3_client.get_object(Bucket=bucket, Key=key)
    return json.loads(resp["Body"].read())


# ── Context inference ─────────────────────────────────────────────────────────

def _infer_context(state: dict) -> tuple[str, str]:
    """
    Scan the state for the first ARN-bearing managed resource to determine the
    default (account_id, region) for resources that don't expose an ARN attribute
    (e.g. aws_nat_gateway).
    """
    for res in state.get("resources", []):
        if res.get("mode") != "managed":
            continue
        for inst in res.get("instances", []):
            arn = inst.get("attributes", {}).get("arn", "")
            if not arn:
                continue
            try:
                account_id, region = _parse_arn(arn)
                if account_id and region:
                    return account_id, region
            except ValueError:
                continue
    return "", ""


# ── Attribute normalisation ───────────────────────────────────────────────────

def _normalize_attrs(attrs: dict) -> dict:
    """Strip Terraform-internal noise; preserve all meaningful resource attributes."""
    return {k: v for k, v in attrs.items() if k not in _DROP_ATTRS}


# ── Resource extraction ────────────────────────────────────────────────────────

def _extract_resources(
    state: dict,
    fallback_account: str = "",
    fallback_region: str  = "",
) -> Iterator[tuple[str, str, str, str, dict]]:
    """
    Yield (resource_type, resource_id, account_id, region, normalized_attrs)
    for every managed non-skipped resource in the state.

    account_id and region come from the resource ARN where available; resources
    without an ARN (e.g. aws_nat_gateway) fall back to the context inferred from
    other resources in the same state file.

    IAM and other global-service resources have an empty region in their ARN;
    these are stored with region="global".
    """
    for res in state.get("resources", []):
        if res.get("mode") != "managed":
            continue
        rtype = res.get("type", "")
        if rtype in _SKIP_TYPES:
            continue

        for inst in res.get("instances", []):
            attrs  = inst.get("attributes", {})
            res_id = attrs.get("id", "")
            if not res_id:
                logger.warning("Skipping %s instance with no id", rtype)
                continue

            arn = attrs.get("arn", "")
            try:
                account_id, region = _parse_arn(arn)
            except ValueError:
                account_id, region = "", ""

            # IAM / global services: ARN has empty region field
            if account_id and not region:
                region = "global"

            # Resources that expose no ARN (e.g. aws_nat_gateway) fall back
            if not account_id:
                account_id = fallback_account
            if not region:
                region = fallback_region

            if not account_id or not region:
                logger.warning(
                    "Could not determine account/region for %s %s — skipping",
                    rtype, res_id,
                )
                continue

            yield rtype, res_id, account_id, region, _normalize_attrs(attrs)


# ── DynamoDB write ────────────────────────────────────────────────────────────

def _upsert(
    table,
    resource_type: str,
    resource_id: str,
    account_id: str,
    region: str,
    normalized: dict,
    dry_run: bool,
) -> str:
    """Write one resource to DynamoDB. Returns 'upserted', 'no_change', or 'dry_run'."""
    fingerprint = hashlib.sha256(
        json.dumps(normalized, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()

    pk = _pk("aws", account_id, resource_type)
    sk = _sk(region, resource_id)

    if dry_run:
        print(f"  [dry-run] would upsert  PK={pk}  SK={sk}")
        return "dry_run"

    try:
        table.put_item(
            Item={
                "PK":            pk,
                "SK":            sk,
                "account_id":    account_id,
                "region":        region,
                "provider":      "aws",
                "resource_type": resource_type,
                "resource_id":   resource_id,
                "fingerprint":   fingerprint,
                "normalized":    normalized,
                "ingested_at":   datetime.now(timezone.utc).isoformat(),
                "deleted":       False,
            },
            ConditionExpression="attribute_not_exists(PK) OR fingerprint <> :f",
            ExpressionAttributeValues={":f": fingerprint},
        )
        return "upserted"
    except botocore.exceptions.ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return "no_change"
        raise


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # S3 source
    parser.add_argument("--bucket",  required=True, help="S3 bucket containing tfstate files")
    parser.add_argument("--prefix",  default="",    help="S3 key prefix to scan (e.g. dev/)")
    parser.add_argument("--key",     default="",    help="Single S3 key to process")

    # AWS profile for reading state files
    parser.add_argument(
        "--state-profile",
        default=os.environ.get("ASKLOUD_STATE_PROFILE", "askloud_dev"),
        help="AWS profile for reading S3 tfstate files (default: askloud_dev)",
    )

    # DynamoDB target
    parser.add_argument(
        "--dynamo-table",
        default=os.environ.get("ASKLOUD_DYNAMODB_TABLE", ""),
        help="DynamoDB table name",
    )
    parser.add_argument(
        "--dynamo-region",
        default=os.environ.get("ASKLOUD_DYNAMODB_REGION", "ap-south-1"),
        help="DynamoDB table region (default: ap-south-1)",
    )
    parser.add_argument(
        "--dynamo-profile",
        default=os.environ.get("ASKLOUD_DYNAMODB_PROFILE", "askloud_central_ops"),
        help="AWS profile for DynamoDB writes (default: askloud_central_ops)",
    )

    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be written without touching DynamoDB",
    )

    args = parser.parse_args()

    if not args.dynamo_table and not args.dry_run:
        parser.error("--dynamo-table is required (or set ASKLOUD_DYNAMODB_TABLE)")

    # ── Sessions ──────────────────────────────────────────────────────────────
    state_session = boto3.Session(profile_name=args.state_profile)
    s3            = state_session.client("s3")

    dynamo_table = None
    if not args.dry_run:
        dynamo_session = boto3.Session(profile_name=args.dynamo_profile)
        dynamo_table   = dynamo_session.resource(
            "dynamodb", region_name=args.dynamo_region,
        ).Table(args.dynamo_table)

    # ── Process each tfstate file ─────────────────────────────────────────────
    counts = {"upserted": 0, "no_change": 0, "dry_run": 0, "error": 0}

    for key in _iter_tfstate_keys(s3, args.bucket, args.prefix, args.key):
        print(f"\n📄 {key}")
        try:
            state = _read_tfstate(s3, args.bucket, key)
        except Exception as exc:
            print(f"  ✗ Could not read tfstate: {exc}")
            counts["error"] += 1
            continue

        fallback_account, fallback_region = _infer_context(state)

        for rtype, res_id, account_id, region, normalized in _extract_resources(
            state, fallback_account, fallback_region
        ):
            print(f"  → {rtype}  {res_id}  ({account_id} / {region})")
            try:
                result = _upsert(
                    dynamo_table, rtype, res_id, account_id, region,
                    normalized, args.dry_run,
                )
                symbol = {"upserted": "✓", "no_change": "≡", "dry_run": "~"}.get(result, "?")
                print(f"    {symbol} {result}")
                counts[result] += 1
            except Exception as exc:
                print(f"    ✗ {exc}")
                counts["error"] += 1

    print(f"\n── Summary ─────────────────────────────────────────────────────")
    for k, v in counts.items():
        if v:
            print(f"  {k:12s} {v}")


if __name__ == "__main__":
    main()
