"""Tool registry exposed to the LLM agent (OpenAI-compatible function schemas for Groq)."""
from typing import Any, Awaitable, Callable

from tools import incident_tools, memory_tools, runbook_tools


def _fn(name: str, description: str, props: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": props, "required": required, "additionalProperties": False},
        },
    }


TOOL_SCHEMAS = [
    _fn("get_service_health", "Get the CURRENT simulated telemetry for a service (API, Redis client pool, Redis server, upstream, database).",
        {"service": {"type": "string", "description": "Service name, e.g. payment-api"}}, ["service"]),
    _fn("get_recent_deployments", "Get recent deployments for a service, with version, age and change description.",
        {"service": {"type": "string"}}, ["service"]),
    _fn("search_historical_incidents",
        "Search OpsMind's organizational memory in Hindsight for past incidents, root causes, successful resolutions, "
        "FAILED remediation attempts, engineer decisions and learned patterns. Use a descriptive natural-language query "
        "containing the service name and the key symptoms/metrics.",
        {"query": {"type": "string"}}, ["query"]),
    _fn("get_incident", "Read a full incident record from the local incident archive by ID (e.g. INC-011) to compare details.",
        {"incident_id": {"type": "string"}}, ["incident_id"]),
    _fn("get_runbook", "Get the team runbook for a service and issue type (redis, database, deployment, provider, memory).",
        {"service": {"type": "string"}, "issue_type": {"type": "string"}}, ["service", "issue_type"]),
]

_SYNC_TOOLS: dict[str, Callable[..., dict]] = {
    "get_service_health": incident_tools.get_service_health,
    "get_recent_deployments": incident_tools.get_recent_deployments,
    "get_incident": incident_tools.get_incident,
    "get_runbook": runbook_tools.get_runbook,
}
_ASYNC_TOOLS: dict[str, Callable[..., Awaitable[dict]]] = {
    "search_historical_incidents": memory_tools.search_historical_incidents,
}
_REQUIRED = {t["function"]["name"]: t["function"]["parameters"]["required"] for t in TOOL_SCHEMAS}


class ToolError(Exception):
    pass


async def execute_tool(name: str, args: Any, ctx: dict[str, Any]) -> dict[str, Any]:
    if name not in _REQUIRED:
        raise ToolError(f"Unknown tool '{name}'. Available: {', '.join(_REQUIRED)}")
    if not isinstance(args, dict):
        raise ToolError("Tool arguments must be a JSON object")
    missing = [k for k in _REQUIRED[name] if not isinstance(args.get(k), str) or not args.get(k).strip()]
    if missing:
        raise ToolError(f"Missing/invalid arguments for {name}: {', '.join(missing)}")
    clean = {k: str(args[k])[:500] for k in _REQUIRED[name]}
    if name in _ASYNC_TOOLS:
        return await _ASYNC_TOOLS[name](**clean, ctx=ctx)
    return _SYNC_TOOLS[name](**clean, ctx=ctx)
