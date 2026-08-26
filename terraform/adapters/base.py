"""
Abstract base class enforcing the adapter contract for all cloud resource types.

Every concrete adapter must implement fetch() and normalize(); calculate_fingerprint()
ships with a canonical default implementation (deterministic SHA-256 of sorted JSON)
that concrete adapters may override when resource-specific stability guarantees are
needed (e.g., sorting a list field before hashing to prevent order-change false drift).
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod

import boto3


class BaseAdapter(ABC):
    """
    Contract for all cloud-resource adapters in the Askloud ingestion pipeline.

    The three-stage lifecycle::

        raw_data    = adapter.fetch(resource_id, session, region)
        normalized  = adapter.normalize(raw_data)
        fingerprint = adapter.calculate_fingerprint(normalized)

    A fingerprint change between two ingestion runs signals console/runtime drift —
    the DynamoDB item is overwritten only when the fingerprint differs, making every
    write idempotent by content.
    """

    @abstractmethod
    def fetch(self, resource_id: str, session: boto3.Session, region: str) -> dict:
        """
        Query the live cloud API and return the raw provider response.

        Implementations MUST return an empty dict (not raise) when the resource
        no longer exists (terminated, deleted, or purged), so the caller can
        distinguish "resource gone" from "API error" without catching exceptions.

        Args:
            resource_id: Provider-native identifier (e.g. ``i-0abc123def456789``).
            session:     An already-authenticated ``boto3.Session``; may carry
                         cross-account temporary credentials from STS AssumeRole.
            region:      Target region / zone / location string.

        Returns:
            Raw API response dict, or ``{}`` if the resource does not exist.

        Raises:
            botocore.exceptions.ClientError: On unexpected API errors (throttling,
                permission denied, etc.) — the caller handles retry / dead-letter routing.
        """

    @abstractmethod
    def normalize(self, raw_data: dict) -> dict:
        """
        Flatten and normalise a raw provider response into a common schema.

        The returned dict MUST contain at least the following keys so that
        cross-provider queries and drift detection work uniformly:

        ==================== ========================================
        Key                  Type / semantics
        ==================== ========================================
        ``tags``             ``dict[str, str]`` — all resource tags
        ``instance_type``    ``str | None``
        ``subnet_id``        ``str | None``
        ``security_groups``  ``list[str]`` — IDs only (not names)
        ``iam_instance_profile`` ``str | None`` — ARN
        ==================== ========================================

        Args:
            raw_data: Output of :meth:`fetch`; may be ``{}`` when resource is gone.

        Returns:
            Normalised dict with the common schema keys present.
            Returns ``{}`` when ``raw_data`` is empty.
        """

    def calculate_fingerprint(self, normalized_data: dict) -> str:
        """
        Deterministic SHA-256 hex digest of the normalised payload.

        Keys are sorted alphabetically before serialisation so that dict
        insertion-order differences (e.g. across Python versions or API response
        ordering changes) never generate a spurious drift signal.

        Concrete subclasses may override this method to apply resource-specific
        stabilisation (e.g., sorting a list field) before hashing.

        Args:
            normalized_data: Output of :meth:`normalize`.

        Returns:
            64-character lowercase hexadecimal SHA-256 digest string.
        """
        canonical_json = json.dumps(
            normalized_data, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(canonical_json.encode()).hexdigest()
