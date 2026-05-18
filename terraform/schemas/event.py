"""
Structural contract for messages traversing the Askloud SQS ingestion pipeline.

All fields are required; the schema version sentinel ensures forward-compatibility
as the contract evolves without breaking existing consumers.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Action(str, Enum):
    """Operations the ingestion engine can perform on a resource."""

    UPSERT = "UPSERT"
    DELETE = "DELETE"


class Provider(str, Enum):
    """Supported cloud providers."""

    AWS = "aws"
    GCP = "gcp"
    AZURE = "azure"


class EventContext(BaseModel):
    """Identifies the cloud account, region, and provider targeted by this event."""

    account_id: str = Field(..., description="Cloud account or project identifier")
    region: str = Field(..., description="Cloud region, zone, or location")
    provider: Provider = Field(..., description="Cloud provider")


class ResourceRef(BaseModel):
    """Canonical pointer to a single cloud resource."""

    type: str = Field(..., description="Resource type key, e.g. 'aws_instance'")
    id: str = Field(..., description="Provider-native resource identifier")


class AskloudEvent(BaseModel):
    """
    Canonical message schema for all events traversing the Askloud SQS pipeline.

    Schema version: 1.1
    Validation is strict — unknown fields are silently ignored; missing required
    fields raise a ValidationError at parse time so bad messages never reach
    business logic.

    Example payload::

        {
          "schema_version": "1.1",
          "event_id": "a3f1c2d4-...",
          "timestamp": "2024-01-15T12:00:00+00:00",
          "action": "UPSERT",
          "context": {
            "account_id": "123456789012",
            "region": "us-east-1",
            "provider": "aws"
          },
          "resource": {
            "type": "aws_instance",
            "id": "i-0abc123def456789"
          }
        }
    """

    schema_version: Literal["1.1"] = Field(
        default="1.1",
        description="Schema version sentinel — consumers reject anything != '1.1'",
    )
    event_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique event UUID; used for idempotency and STS session naming",
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO-8601 UTC timestamp of when this event was produced",
    )
    action: Action = Field(..., description="Lifecycle operation to apply to the resource")
    context: EventContext = Field(..., description="Account, region, and provider context")
    resource: ResourceRef = Field(..., description="Resource type and canonical identifier")

    @field_validator("timestamp")
    @classmethod
    def _validate_iso8601(cls, v: str) -> str:
        """Reject timestamps that cannot be parsed as ISO-8601."""
        try:
            datetime.fromisoformat(v)
        except ValueError as exc:
            raise ValueError(f"timestamp must be ISO-8601; got {v!r}") from exc
        return v

    model_config = {
        "use_enum_values": True,
        "extra": "ignore",
    }
