"""Local demo data: incidents, runbooks, services, and runtime demo state.

Also converts historical incidents into Hindsight seed memories (the four memory
categories: incident experience, failed approaches, engineer decisions, learned patterns).
"""
from __future__ import annotations

import json
import threading
from datetime import datetime
from functools import lru_cache
from typing import Any

from config import DATA_DIR
from models.incident import Incident, IncidentSummary

STATE_FILE = DATA_DIR / "runtime_state.json"
_state_lock = threading.Lock()


class IncidentNotFound(Exception):
    def __init__(self, incident_id: str):
        super().__init__(incident_id)
        self.incident_id = incident_id


def _load(name: str) -> Any:
    with open(DATA_DIR / name, encoding="utf-8") as f:
        return json.load(f)


@lru_cache
def historical_incidents() -> dict[str, dict]:
    return {i["id"]: i for i in _load("incidents.json")}


@lru_cache
def demo_incidents() -> dict[str, dict]:
    return {i["id"]: i for i in _load("demo_incidents.json")}


@lru_cache
def runbooks() -> list[dict]:
    return _load("runbooks.json")


@lru_cache
def services() -> dict[str, dict]:
    return {s["name"]: s for s in _load("services.json")}


# --------------------------------------------------------------------------- state


def _read_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {"statuses": {}, "investigations": {}, "feedback": []}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"statuses": {}, "investigations": {}, "feedback": []}


def _write_state(state: dict[str, Any]) -> None:
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    tmp.replace(STATE_FILE)


def update_state(fn) -> dict[str, Any]:
    with _state_lock:
        state = _read_state()
        fn(state)
        _write_state(state)
        return state


def get_state() -> dict[str, Any]:
    with _state_lock:
        return _read_state()


def reset_state() -> None:
    with _state_lock:
        if STATE_FILE.exists():
            STATE_FILE.unlink()


def set_status(incident_id: str, status: str) -> None:
    update_state(lambda s: s.setdefault("statuses", {}).__setitem__(incident_id, status))


def save_investigation(incident_id: str, summary: dict[str, Any]) -> None:
    update_state(lambda s: s.setdefault("investigations", {}).__setitem__(incident_id, summary))


def last_investigation(incident_id: str) -> dict[str, Any] | None:
    return get_state().get("investigations", {}).get(incident_id)


def record_feedback(entry: dict[str, Any]) -> None:
    update_state(lambda s: s.setdefault("feedback", []).append(entry))


# --------------------------------------------------------------------------- queries


def list_incidents() -> list[IncidentSummary]:
    statuses = get_state().get("statuses", {})
    out = [
        IncidentSummary(
            id=i["id"], title=i["title"], service=i["service"], severity=i["severity"],
            status=statuses.get(i["id"], i.get("status", "open")), timestamp=i["timestamp"], kind="active",
        )
        for i in demo_incidents().values()
    ]
    out += [
        IncidentSummary(
            id=i["id"], title=i["title"], service=i["service"], severity=i["severity"],
            status="resolved", timestamp=i["timestamp"], kind="historical",
        )
        for i in sorted(historical_incidents().values(), key=lambda x: x["timestamp"], reverse=True)
    ]
    return out


def get_active_incident(incident_id: str) -> Incident:
    raw = demo_incidents().get(incident_id.upper())
    if raw is None:
        raise IncidentNotFound(incident_id)
    data = dict(raw)
    data["status"] = get_state().get("statuses", {}).get(raw["id"], raw.get("status", "open"))
    return Incident(**data)


def get_any_incident(incident_id: str) -> dict[str, Any]:
    iid = incident_id.strip().upper()
    if iid in demo_incidents():
        return {"kind": "active", **demo_incidents()[iid]}
    if iid in historical_incidents():
        return {"kind": "historical", **historical_incidents()[iid]}
    raise IncidentNotFound(incident_id)


# --------------------------------------------------------------------------- seed memories


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _incident_experience_text(i: dict) -> str:
    metrics = ", ".join(f"{k}={v}" for k, v in i["metrics"].items())
    dep = i.get("recent_deployment") or {}
    lines = [
        f"Incident {i['id']} ({i['severity']}) affected {i['service']}: {i['title']}.",
        f"Symptoms: {'; '.join(i['symptoms'])}.",
        f"Metrics during the incident: {metrics}.",
    ]
    if dep:
        lines.append(
            f"Recent deployment: {dep['version']} ({dep['deployed_minutes_before']} minutes before) - {dep['change']}."
        )
    lines.append(f"Root cause: {i['root_cause']}.")
    lines.append(f"Successful resolution: {i['resolution']}")
    for fa in i.get("failed_approaches", []):
        lines.append(f"Failed remediation attempt: {fa['action']} - result: {fa['result']}.")
    if i.get("engineer_notes"):
        lines.append(f"Engineer notes: {i['engineer_notes']}")
    return "\n".join(lines)


# Postmortem-review knowledge (category D) and past engineer decisions (category B).
# These are what a team would have written in postmortems; they are stored in Hindsight
# and are only ever surfaced to the agent through recall.
_PATTERNS = [
    {
        "id": "pattern-redis-pool-exhaustion",
        "pattern": "redis_connection_pool_exhaustion",
        "service": "payment-api",
        "incidents": "INC-003,INC-011,INC-019,INC-024",
        "text": (
            "Postmortem review of INC-003, INC-011, INC-019 and INC-024 (payment-api): when payment-api shows Redis "
            "timeout errors together with the application Redis client pool at capacity (e.g. 20/20, 40/40, 60/60, "
            "100/100) while the Redis server itself is healthy (low CPU, no evictions), the root cause has been "
            "application-side Redis connection pool exhaustion, usually after a deploy that added Redis calls per "
            "request or a traffic spike. The fix every time was increasing the payment-api Redis connection pool and "
            "restarting API workers."
        ),
    },
    {
        "id": "pattern-redis-server-unhealthy",
        "pattern": "redis_server_unhealthy",
        "service": "session-service",
        "incidents": "INC-007",
        "text": (
            "Postmortem review of INC-007 (session-service): Redis timeouts can also come from the Redis server itself "
            "being unhealthy - Redis CPU near 100%, memory at maxmemory and high eviction rate - while the client pool "
            "is NOT saturated. In that case failing over / restarting Redis was the correct fix."
        ),
    },
    {
        "id": "pattern-db-pool-exhaustion",
        "pattern": "db_connection_pool_exhaustion",
        "service": "orders-api",
        "incidents": "INC-001,INC-006,INC-012,INC-016,INC-020,INC-025",
        "text": (
            "Postmortem review of database pool incidents (INC-001, INC-006, INC-012, INC-016, INC-020, INC-025): "
            "application DB pool at capacity with a healthy Postgres usually means a recent deploy holds connections "
            "longer (N+1 queries, long transactions, leaks). Roll back the correlated deploy, then restart pods to "
            "release connections."
        ),
    },
    {
        "id": "pattern-bad-config-deploy",
        "pattern": "bad_deployment_config",
        "service": "*",
        "incidents": "INC-002,INC-008,INC-013,INC-017,INC-022",
        "text": (
            "Postmortem review of configuration incidents (INC-002, INC-008, INC-013, INC-017, INC-022): errors that "
            "start within minutes of a config-only deploy, often with suspiciously exact timeouts or provider 401/404s, "
            "are fixed fastest by rolling back first and investigating the config diff afterwards."
        ),
    },
    {
        "id": "pattern-provider-latency",
        "pattern": "external_provider_latency",
        "service": "payment-api",
        "incidents": "INC-004,INC-009,INC-014,INC-021,INC-026",
        "text": (
            "Postmortem review of provider latency incidents (INC-004, INC-009, INC-014, INC-021, INC-026): high upstream "
            "provider latency with normal internal pools (Redis pool well below capacity) is a provider problem. Open "
            "the circuit breaker and fail over to the secondary provider; scaling or restarting our own services does "
            "not help."
        ),
    },
    {
        "id": "pattern-memory-leak",
        "pattern": "memory_leak",
        "service": "*",
        "incidents": "INC-005,INC-010,INC-015,INC-018,INC-023",
        "text": (
            "Postmortem review of memory leak incidents (INC-005, INC-010, INC-015, INC-018, INC-023): linear heap growth "
            "and OOMKilled pods after adding caches, listeners or metric labels. Rolling restarts give relief; the fix "
            "is bounding the cache or cleaning up references. Raising memory limits only delays the OOM."
        ),
    },
]

_DECISIONS = [
    {
        "id": "decision-INC-012-no-db-failover",
        "incident_id": "INC-012",
        "service": "orders-api",
        "text": (
            "Engineer decision after INC-012: do not fail over the Postgres primary when the database is healthy and "
            "only the orders-api application connection pool is exhausted. The failover added 6 minutes of write "
            "downtime and did not help."
        ),
    },
]


def historical_memory_items(build_item) -> list[dict[str, Any]]:
    """Build Hindsight retain items from local historical data.

    `build_item` is hindsight_service.build_item (passed in so this module stays Hindsight-free).
    """
    items = []
    for i in historical_incidents().values():
        items.append(
            build_item(
                content=_incident_experience_text(i),
                document_id=f"incident-{i['id']}",
                metadata={
                    "type": "incident_experience",
                    "incident_id": i["id"],
                    "service": i["service"],
                    "severity": i["severity"],
                    "root_cause": i["pattern"],
                    "source": "historical_incident",
                },
                tags=["incident", i["service"], i["pattern"]],
                context=f"Resolved production incident record / postmortem for {i['id']}",
                timestamp=_ts(i["timestamp"]),
            )
        )
        for n, fa in enumerate(i.get("failed_approaches", []), start=1):
            items.append(
                build_item(
                    content=(
                        f"During {i['id']} on {i['service']} ({i['title']}), the remediation attempt "
                        f"'{fa['action']}' FAILED: {fa['result']}. The effective remediation was: {i['resolution']}"
                    ),
                    document_id=f"failed-{i['id']}-{n}",
                    metadata={
                        "type": "failed_approach",
                        "incident_id": i["id"],
                        "service": i["service"],
                        "root_cause": i["pattern"],
                        "source": "postmortem",
                    },
                    tags=["failed_approach", i["service"], i["pattern"]],
                    context=f"Failed remediation attempt recorded in the {i['id']} postmortem",
                    timestamp=_ts(i["timestamp"]),
                )
            )
    for p in _PATTERNS:
        items.append(
            build_item(
                content=p["text"],
                document_id=p["id"],
                metadata={
                    "type": "learned_pattern",
                    "service": p["service"],
                    "root_cause": p["pattern"],
                    "incident_ids": p["incidents"],
                    "source": "postmortem_review",
                },
                tags=["learned_pattern", p["pattern"]],
                context="Cross-incident postmortem review",
            )
        )
    for d in _DECISIONS:
        items.append(
            build_item(
                content=d["text"],
                document_id=d["id"],
                metadata={
                    "type": "engineer_decision",
                    "incident_id": d["incident_id"],
                    "service": d["service"],
                    "source": "postmortem",
                },
                tags=["engineer_decision", d["service"]],
                context="Engineer decision recorded after an incident",
            )
        )
    return items
