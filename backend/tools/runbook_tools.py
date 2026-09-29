"""Local runbook lookup."""
from typing import Any

from services import incident_service

ISSUE_ALIASES = {
    "redis": ["redis", "cache", "connection pool", "redis_pool", "redis timeout"],
    "database": ["database", "db", "postgres", "sql"],
    "deployment": ["deploy", "config", "configuration", "rollback", "release"],
    "provider": ["provider", "payflow", "upstream", "third-party", "external"],
    "memory": ["memory", "oom", "leak", "heap"],
}


def get_runbook(service: str, issue_type: str, ctx: dict[str, Any]) -> dict[str, Any]:
    issue = issue_type.strip().lower()
    wanted = {k for k, words in ISSUE_ALIASES.items() if any(w in issue for w in words)}
    svc = service.strip().lower()
    matches = [
        rb for rb in incident_service.runbooks()
        if rb["issue_type"] in wanted and rb["service"] in ("*", svc)
    ]
    if not matches:
        return {"error": f"No runbook found for service={service} issue_type={issue_type}",
                "available_issue_types": sorted(ISSUE_ALIASES)}
    return {"runbooks": matches}
