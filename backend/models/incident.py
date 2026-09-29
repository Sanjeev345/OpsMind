from typing import Any, Literal

from pydantic import BaseModel, Field


class Metric(BaseModel):
    key: str
    label: str
    value: str
    baseline: str | None = None
    status: Literal["critical", "warning", "ok"] = "ok"


class IncidentSummary(BaseModel):
    id: str
    title: str
    service: str
    severity: str
    status: str
    timestamp: str
    kind: Literal["active", "historical"]


class Incident(BaseModel):
    """An active (demo) incident under investigation."""

    id: str
    title: str
    timestamp: str
    service: str
    severity: str
    status: str = "open"
    summary: str
    alerts: list[str] = Field(default_factory=list)
    metrics: list[Metric] = Field(default_factory=list)
    health: dict[str, Any] = Field(default_factory=dict)
    deployments: list[dict[str, Any]] = Field(default_factory=list)
