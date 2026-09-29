"""Local (simulated) incident tools: incident records, service health, deployments."""
from typing import Any

from services import incident_service


def get_incident(incident_id: str, ctx: dict[str, Any]) -> dict[str, Any]:
    try:
        inc = incident_service.get_any_incident(incident_id)
    except incident_service.IncidentNotFound:
        return {"error": f"Incident {incident_id} not found"}
    if inc["kind"] == "active":
        return {k: inc[k] for k in ("id", "title", "service", "severity", "summary", "alerts", "metrics", "timestamp")}
    # historical incident record (from the local incident archive)
    return {k: inc.get(k) for k in (
        "id", "title", "timestamp", "service", "severity", "symptoms", "metrics", "recent_deployment",
        "root_cause", "resolution", "failed_approaches", "engineer_notes",
    )}


def get_service_health(service: str, ctx: dict[str, Any]) -> dict[str, Any]:
    active = ctx["incident"]
    if service.strip().lower() == active.service.lower():
        return active.health
    known = incident_service.services().get(service.strip().lower())
    if known:
        return {"service": known["name"], "note": "No active alerts for this service. No detailed telemetry snapshot in the demo environment."}
    return {"error": f"Unknown service '{service}'", "known_services": sorted(incident_service.services())}


def get_recent_deployments(service: str, ctx: dict[str, Any]) -> dict[str, Any]:
    active = ctx["incident"]
    if service.strip().lower() == active.service.lower():
        return {"service": active.service, "deployments": active.deployments}
    if service.strip().lower() in incident_service.services():
        return {"service": service, "deployments": [], "note": "No deployments in the last 48 hours."}
    return {"error": f"Unknown service '{service}'"}
