"""Pydantic models for the Smart Home Multi-Agent System.

Defines the serialisation contracts used for communication between the
orchestrator and the agent fleet over NATS.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


# ── Task models ──────────────────────────────────────────────────────────────


class LightingPayload(BaseModel):
    """Type-specific parameters for a lighting ``set_state`` command."""

    device_id: str = Field(..., description="Target device identifier")
    state: str = Field(..., pattern=r"^(on|off)$", description="Desired state")
    brightness: int = Field(..., ge=0, le=100, description="Brightness 0-100")
    ambient_light: int = Field(
        ...,
        ge=0,
        description="Current ambient light level in lux",
    )


class TaskModel(BaseModel):
    """A unit of work published to an agent subject (e.g. ``tasks.lighting``).

    Maps directly to the Go agent's ``Task`` struct.
    """

    id: str = Field(default_factory=lambda: uuid4().hex, description="Unique task identifier")
    type: str = Field(..., description="Operation type (e.g. 'set_state')")
    payload: dict[str, Any] = Field(..., description="Type-specific parameters as a raw JSON object")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        description="ISO-8601 timestamp of task creation",
    )

    @field_validator("payload")
    @classmethod
    def payload_must_be_object(cls, v: Any) -> dict[str, Any]:
        """Ensure payload is a dict (``json.RawMessage`` requirement of Go agent)."""
        if not isinstance(v, dict):
            msg = "payload must be a JSON object (dict), not a raw string"
            raise ValueError(msg)
        return v


# ── Result models ────────────────────────────────────────────────────────────


class ResultModel(BaseModel):
    """A result published by an agent to ``tasks.completed``.

    Maps directly to the Go agent's ``Result`` struct.
    """

    task_id: str = Field(..., description="Original task identifier")
    success: bool = Field(..., description="Whether the task completed successfully")
    data: Any = Field(None, description="Operation result payload (success)")
    error: str = Field("", description="Error message (failure)")
    timestamp: str = Field(
        ...,
        description="ISO-8601 timestamp of result generation",
    )


# ── Internal correlation model ───────────────────────────────────────────────


class CorrelationEntry(BaseModel):
    """Internal bookkeeping entry that pairs a pending task with its Future.

    Not serialised over the wire — used solely inside the orchestrator to
    correlate asynchronous NATS responses with the original request Futures.
    """

    subject: str
    future: Any  # asyncio.Future — quoted to avoid runtime import cycle
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )
