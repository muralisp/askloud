"""
Askloud Diff Lambda

Triggered by EventBridge when a *.tfstate file is written to a workload S3 bucket.
Reads the new tfstate, then diffs it against the current DynamoDB records for that
workspace, and publishes:
  - UPSERT messages for all resources present in the new state.
  - DELETE messages for resources currently in DynamoDB (tfstate_key matches) that
    are absent from the new state (i.e. destroyed by terraform destroy/apply).

Using DynamoDB as the diff baseline (rather than the previous S3 version) means:
  - No dependency on S3 bucket versioning.
  - Resilient to missed events — each run self-heals against the actual inventory.
  - Scoped per workspace via the tfstate_key attribute stored on every record.

Resource attributes are taken directly from tfstate — no live AWS API calls are made.

Required environment variables:
    SQS_QUEUE_URL    URL of the Askloud ingestion SQS queue
    DYNAMODB_TABLE   Name of the Askloud inventory DynamoDB table
"""

from __future__ import annotations

import json
import logging
import os
from typing import Iterator

import boto3
from boto3.dynamodb.conditions import Attr

logger = logging.getLogger()
logger.setLevel(logging.INFO)

SQS_QUEUE_URL: str  = os.environ["SQS_QUEUE_URL"]
DYNAMODB_TABLE: str = os.environ["DYNAMODB_TABLE"]

_s3    = boto3.client("s3")
_sqs   = boto3.client("sqs")
_table = boto3.resource("dynamodb").Table(DYNAMODB_TABLE)

# ── Resource types to skip (sub-resources / bindings / triggers) ──────────────
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

_DROP_ATTRS = frozenset({
    "timeouts",
    "tags_all",
})


# ── Helpers (mirrors askloud_ingest.py) ───────────────────────────────────────

def _parse_arn(arn: str) -> tuple[str, str]:
    parts = arn.split(":")
    if len(parts) < 6:
        raise ValueError(f"Cannot parse ARN: {arn!r}")
    return parts[4], parts[3]  # account_id, region


def _infer_context(state: dict) -> tuple[str, str]:
    """Return (account_id, region) from the first ARN-bearing resource in the state."""
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


def _normalize_attrs(attrs: dict) -> dict:
    return {k: v for k, v in attrs.items() if k not in _DROP_ATTRS}


def _extract_resources(
    state: dict,
    fallback_account: str = "",
    fallback_region: str  = "",
) -> Iterator[tuple[str, str, str, str, dict]]:
    """Yield (resource_type, resource_id, account_id, region, normalized_attrs)."""
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
                continue

            # Skip terminated EC2 instances — the EC2 Events Lambda handles
            # deletion via state-change events, and re-upserting from stale
            # tfstate would undo that soft-delete.
            if rtype == "aws_instance" and attrs.get("instance_state") == "terminated":
                logger.info(json.dumps({
                    "status":      "skipped",
                    "reason":      "instance_terminated",
                    "resource_id": res_id,
                }))
                continue

            arn = attrs.get("arn", "")
            try:
                account_id, region = _parse_arn(arn)
            except ValueError:
                account_id, region = "", ""

            if account_id and not region:
                region = "global"

            if not account_id:
                account_id = fallback_account
            if not region:
                region = fallback_region

            if not account_id or not region:
                logger.warning(json.dumps({
                    "status": "skipped",
                    "reason": "no_account_or_region",
                    "resource_type": rtype,
                    "resource_id": res_id,
                }))
                continue

            yield rtype, res_id, account_id, region, _normalize_attrs(attrs)


# ── DynamoDB diff baseline ────────────────────────────────────────────────────

def _get_existing_resources(tfstate_key: str) -> dict[tuple[str, str], dict]:
    """
    Scan DynamoDB for live records belonging to this workspace (by tfstate_key).

    Returns {(resource_type, resource_id): {"account_id": ..., "region": ...}}
    so the caller can detect which resources were removed from the new tfstate.
    """
    existing: dict[tuple[str, str], dict] = {}
    scan_kwargs: dict = {
        "FilterExpression": (
            Attr("tfstate_key").eq(tfstate_key)
            & (Attr("deleted").eq(False) | Attr("deleted").not_exists())
        ),
        "ProjectionExpression": "resource_type, resource_id, account_id, #rgn",
        "ExpressionAttributeNames": {"#rgn": "region"},
    }

    while True:
        response = _table.scan(**scan_kwargs)
        for item in response.get("Items", []):
            key = (item.get("resource_type", ""), item.get("resource_id", ""))
            existing[key] = {
                "account_id": item.get("account_id", ""),
                "region":     item.get("region", ""),
            }
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        scan_kwargs["ExclusiveStartKey"] = last_key

    logger.info(json.dumps({
        "status":      "existing_resources_loaded",
        "tfstate_key": tfstate_key,
        "count":       len(existing),
    }))
    return existing


# ── Lambda handler ────────────────────────────────────────────────────────────

def lambda_handler(event: dict, context) -> None:
    detail = event.get("detail", {})
    bucket = detail.get("bucket", {}).get("name", "")
    key    = detail.get("object", {}).get("key", "")

    if not bucket or not key or not key.endswith(".tfstate"):
        logger.info(json.dumps({"status": "skipped", "reason": "not_a_tfstate", "key": key}))
        return

    logger.info(json.dumps({"status": "processing", "bucket": bucket, "key": key}))

    # ── New state: all current resources → UPSERT ─────────────────────────────
    new_state                     = json.loads(_s3.get_object(Bucket=bucket, Key=key)["Body"].read())
    fallback_account, fallback_region = _infer_context(new_state)

    new_resource_keys: set[tuple[str, str]] = set()
    messages: list[dict] = []

    for rtype, res_id, account_id, region, normalized in _extract_resources(
        new_state, fallback_account, fallback_region
    ):
        new_resource_keys.add((rtype, res_id))
        messages.append({
            "action":        "UPSERT",
            "provider":      "aws",
            "account_id":    account_id,
            "region":        region,
            "resource_type": rtype,
            "resource_id":   res_id,
            "tfstate_key":   key,
            "normalized":    normalized,
        })

    # ── DynamoDB diff: resources absent from new state → DELETE ───────────────
    existing = _get_existing_resources(key)
    for (rtype, res_id), meta in existing.items():
        if (rtype, res_id) not in new_resource_keys:
            messages.append({
                "action":        "DELETE",
                "provider":      "aws",
                "account_id":    meta["account_id"],
                "region":        meta["region"],
                "resource_type": rtype,
                "resource_id":   res_id,
            })
            logger.info(json.dumps({
                "status":        "delete_detected",
                "resource_type": rtype,
                "resource_id":   res_id,
            }))

    if not messages:
        logger.info(json.dumps({"status": "no_resources", "bucket": bucket, "key": key}))
        return

    # ── SQS send_message_batch: max 10 entries per call ───────────────────────
    sent = failed = 0
    for batch_start in range(0, len(messages), 10):
        batch = messages[batch_start:batch_start + 10]
        entries = [
            {"Id": str(i), "MessageBody": json.dumps(msg, default=str)}
            for i, msg in enumerate(batch)
        ]
        resp = _sqs.send_message_batch(QueueUrl=SQS_QUEUE_URL, Entries=entries)
        sent += len(resp.get("Successful", []))
        for failure in resp.get("Failed", []):
            logger.error(json.dumps({"status": "sqs_send_failed", "detail": failure}))
            failed += 1

    logger.info(json.dumps({
        "status":  "done",
        "bucket":  bucket,
        "key":     key,
        "upserts": sum(1 for m in messages if m["action"] == "UPSERT"),
        "deletes": sum(1 for m in messages if m["action"] == "DELETE"),
        "sent":    sent,
        "failed":  failed,
    }))
