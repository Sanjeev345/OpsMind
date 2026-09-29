from typing import Any, Literal

from pydantic import BaseModel, Field

from models.incident import Incident


class InvestigateRequest(BaseModel):
    incident_id: str = Field(min_length=1, max_length=32)


class TraceEvent(BaseModel):
    id: str
    step: str
    status: Literal["running", "completed", "failed", "warning"]
    detail: str | None = None
    tool: str | None = None
    started_at: str
    duration_ms: int | None = None


class MemoryItem(BaseModel):
    """One memory returned by Hindsight recall. `score` is Hindsight's own final ranking score."""

    id: str
    text: str
    fact_type: str | None = None
    document_id: str | None = None
    memory_type: str | None = None
    incident_id: str | None = None
    mentioned_incidents: list[str] = Field(default_factory=list)
    source: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    score: float | None = None
    occurred_at: str | None = None
    query: str | None = None


class HistoricalMatch(BaseModel):
    incident_id: str
    reason: str
    outcome: str


class FailedApproach(BaseModel):
    incident_id: str
    action: str
    result: str


class LearnedPattern(BaseModel):
    pattern: str
    source: str
    from_engineer_feedback: bool


class RecommendedAction(BaseModel):
    action: str
    rationale: str


class Diagnosis(BaseModel):
    summary: str
    root_cause: str
    confidence: float = Field(ge=0.0, le=1.0)
    current_evidence: list[str]
    historical_matches: list[HistoricalMatch]
    failed_approaches: list[FailedApproach]
    learned_patterns: list[LearnedPattern]
    recommended_actions: list[RecommendedAction]
    warnings: list[str]


class InvestigationResponse(BaseModel):
    investigation_id: str
    incident: Incident
    diagnosis: Diagnosis | None
    diagnosis_error: str | None = None
    memories: list[MemoryItem]
    memory_status: Literal["ok", "unavailable", "not_used"]
    memory_error: str | None = None
    memory_queries: list[str]
    trace: list[TraceEvent]
    tool_calls: int
    model: str
    started_at: str
    completed_at: str
    duration_ms: int
    extra: dict[str, Any] = Field(default_factory=dict)
