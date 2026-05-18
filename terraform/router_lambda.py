"""
Askloud Router Lambda

Consumes resource events from the ingestion SQS queue and persists them to
DynamoDB. Each message contains the full normalized resource data produced by
the Diff Lambda — no live AWS API calls are required.

Batch processing contract:
- Processes all SQS Records in the batch independently.
- Returns batchItemFailures so Lambda replays only failed messages on retry.
- A failure in one record never aborts the rest of the batch.

Idempotency:
- Every put_item carries a conditional expression: write only when the item is
  new OR the fingerprint has changed.  Unchanged resources are a cheap no-op.

Required environment variables:
    DYNAMODB_TABLE   Name of the Askloud inventory DynamoDB table
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

import boto3
import botocore.exceptions

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DYNAMODB_TABLE: str   = os.environ["DYNAMODB_TABLE"]
_SOFT_DELETE_TTL_SECS = 604_800  # 7 days

# Reuse the client across warm invocations
_table = boto3.resource("dynamodb").Table(DYNAMODB_TABLE)


# ── Public handler ────────────────────────────────────────────────────────────

def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, list]:
    batch_item_failures: list[dict[str, str]] = []

    for record in event.get("Records", []):
        message_id = record.get("messageId", "<unknown>")
        try:
            _process_record(record)
            logger.info(json.dumps({"status": "ok", "messageId": message_id}))
        except Exception as exc:
            logger.error(json.dumps({
                "status":    "error",
                "messageId": message_id,
                "error":     type(exc).__name__,
                "detail":    str(exc),
            }))
            batch_item_failures.append({"itemIdentifier": message_id})

    return {"batchItemFailures": batch_item_failures}


# ── Record dispatch ───────────────────────────────────────────────────────────

def _process_record(record: dict[str, Any]) -> None:
    body   = json.loads(record["body"])
    action = body.get("action", "UPSERT")

    if action == "DELETE":
        _soft_delete(body)
    else:
        _upsert(body)


# ── UPSERT ────────────────────────────────────────────────────────────────────

def _upsert(body: dict[str, Any]) -> None:
    normalized  = body["normalized"]
    fingerprint = hashlib.sha256(
        json.dumps(normalized, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()

    pk = f"aws#{body['account_id']}#{body['resource_type']}"
    sk = f"{body['region']}#{body['resource_id']}"

    try:
        _table.put_item(
            Item={
                "PK":            pk,
                "SK":            sk,
                "account_id":    body["account_id"],
                "region":        body["region"],
                "provider":      body.get("provider", "aws"),
                "resource_type": body["resource_type"],
                "resource_id":   body["resource_id"],
                "tfstate_key":   body.get("tfstate_key", ""),
                "fingerprint":   fingerprint,
                "normalized":    normalized,
                "ingested_at":   datetime.now(timezone.utc).isoformat(),
                "deleted":       False,
            },
            ConditionExpression="attribute_not_exists(PK) OR fingerprint <> :f",
            ExpressionAttributeValues={":f": fingerprint},
        )
        logger.info(json.dumps({"status": "upserted", "pk": pk, "fingerprint": fingerprint}))
    except botocore.exceptions.ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            logger.info(json.dumps({"status": "no_change", "pk": pk}))
        else:
            raise


# ── SOFT DELETE ───────────────────────────────────────────────────────────────

def _soft_delete(body: dict[str, Any]) -> None:
    pk  = f"aws#{body['account_id']}#{body['resource_type']}"
    sk  = f"{body['region']}#{body['resource_id']}"
    ttl = int(time.time()) + _SOFT_DELETE_TTL_SECS

    _table.update_item(
        Key={"PK": pk, "SK": sk},
        UpdateExpression="SET deleted = :t, deleted_at = :da, ttl_timestamp = :ttl",
        ExpressionAttributeValues={
            ":t":   True,
            ":da":  datetime.now(timezone.utc).isoformat(),
            ":ttl": ttl,
        },
    )
    logger.info(json.dumps({"status": "soft_deleted", "pk": pk, "ttl_epoch": ttl}))
