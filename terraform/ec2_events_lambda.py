"""
Askloud EC2 Events Lambda

Triggered by EventBridge when an EC2 instance reaches a terminal state
(shutting-down or terminated).  Publishes a DELETE message to the Askloud
ingestion SQS queue so the Router Lambda soft-deletes the DynamoDB record.

Required environment variables:
    SQS_QUEUE_URL    URL of the Askloud ingestion SQS queue
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

SQS_QUEUE_URL: str = os.environ["SQS_QUEUE_URL"]

_sqs = boto3.client("sqs")

_TERMINAL_STATES = frozenset({"shutting-down", "terminated"})
_RESOURCE_TYPE   = "aws_instance"


def lambda_handler(event: dict[str, Any], context: Any) -> None:
    detail      = event.get("detail", {})
    state       = detail.get("state", "")
    instance_id = detail.get("instance-id", "")
    account_id  = event.get("account", "")
    region      = event.get("region", "")

    if state not in _TERMINAL_STATES:
        logger.info(json.dumps({"status": "skipped", "state": state, "instance_id": instance_id}))
        return

    if not instance_id or not account_id or not region:
        logger.warning(json.dumps({"status": "missing_fields", "event": event}))
        return

    message = {
        "action":        "DELETE",
        "provider":      "aws",
        "account_id":    account_id,
        "region":        region,
        "resource_type": _RESOURCE_TYPE,
        "resource_id":   instance_id,
    }

    _sqs.send_message(
        QueueUrl=SQS_QUEUE_URL,
        MessageBody=json.dumps(message),
    )

    logger.info(json.dumps({
        "status":      "delete_queued",
        "instance_id": instance_id,
        "state":       state,
        "account_id":  account_id,
        "region":      region,
    }))
