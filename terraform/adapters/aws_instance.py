"""
Concrete BaseAdapter implementation for Amazon EC2 instances (resource type: aws_instance).

Handles the full describe_instances lifecycle including cross-account sessions,
404/malformed-ID graceful degradation, and a fingerprint that is stable against
security-group ordering differences (a common source of false drift in EC2).
"""

from __future__ import annotations

import hashlib
import json
import logging

import boto3
import botocore.exceptions

from .base import BaseAdapter

logger = logging.getLogger(__name__)

# EC2 error codes that mean "resource is gone" rather than "unexpected failure"
_NOT_FOUND_CODES = frozenset({
    "InvalidInstanceID.NotFound",
    "InvalidInstanceID.Malformed",
})


class AwsInstanceAdapter(BaseAdapter):
    """Adapter for ``aws_instance`` (Amazon EC2) resources."""

    def fetch(self, resource_id: str, session: boto3.Session, region: str) -> dict:
        """
        Call ``ec2.describe_instances`` for the given instance ID via the
        provided cross-account session.

        Returns the raw Instance dict (first instance of the first reservation),
        or ``{}`` when the instance is terminated, purged, or the ID is invalid.

        Args:
            resource_id: EC2 instance ID, e.g. ``i-0abc123def456789``.
            session:     Cross-account boto3.Session from STS AssumeRole.
            region:      AWS region, e.g. ``us-east-1``.

        Returns:
            Raw EC2 Instance dict from the AWS API, or ``{}`` if not found.

        Raises:
            botocore.exceptions.ClientError: For unexpected API failures
                (throttling, insufficient permissions, etc.).
        """
        ec2 = session.client("ec2", region_name=region)
        try:
            response = ec2.describe_instances(InstanceIds=[resource_id])
            reservations = response.get("Reservations", [])
            if not reservations:
                logger.warning(
                    "describe_instances returned empty Reservations for %s in %s",
                    resource_id,
                    region,
                )
                return {}
            instances = reservations[0].get("Instances", [])
            if not instances:
                return {}
            return instances[0]

        except botocore.exceptions.ClientError as exc:
            code = exc.response["Error"]["Code"]
            if code in _NOT_FOUND_CODES:
                logger.warning(
                    "Instance %s not found in %s (code: %s); treating as deleted",
                    resource_id,
                    region,
                    code,
                )
                return {}
            raise

    def normalize(self, raw_data: dict) -> dict:
        """
        Extract the common-denominator fields from the EC2 ``describe_instances`` payload.

        Tag keys and values are extracted from the AWS array format
        ``[{"Key": "...", "Value": "..."}, ...]`` into a flat ``dict[str, str]``.
        Security groups are reduced to a list of Group IDs (not names) so the
        fingerprint is stable against group-name renames.

        Args:
            raw_data: Raw EC2 Instance dict from :meth:`fetch`, or ``{}``.

        Returns:
            Normalised dict, or ``{}`` when ``raw_data`` is empty.
        """
        if not raw_data:
            return {}

        tags: dict[str, str] = {
            t["Key"]: t["Value"]
            for t in raw_data.get("Tags", [])
            if "Key" in t and "Value" in t
        }

        security_groups: list[str] = [
            sg["GroupId"]
            for sg in raw_data.get("SecurityGroups", [])
            if "GroupId" in sg
        ]

        iam_profile_arn: str | None = None
        iam_block = raw_data.get("IamInstanceProfile")
        if isinstance(iam_block, dict):
            iam_profile_arn = iam_block.get("Arn")

        return {
            "iam_instance_profile": iam_profile_arn,
            "instance_type": raw_data.get("InstanceType"),
            "security_groups": security_groups,
            "subnet_id": raw_data.get("SubnetId"),
            "tags": tags,
        }

    def calculate_fingerprint(self, normalized_data: dict) -> str:
        """
        SHA-256 of the alphabetically-sorted, minified JSON of the normalised payload.

        Security groups are sorted before hashing so that AWS returning the same
        groups in a different order (which happens) does not produce phantom drift.

        Args:
            normalized_data: Output of :meth:`normalize`.

        Returns:
            64-character lowercase hex SHA-256 digest.
        """
        stable = dict(normalized_data)
        stable["security_groups"] = sorted(stable.get("security_groups") or [])
        canonical_json = json.dumps(stable, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical_json.encode()).hexdigest()
