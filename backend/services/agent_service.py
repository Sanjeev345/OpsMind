"""OpsMind investigation agent: Groq tool-calling loop + Hindsight recall + structured diagnosis.

Every trace event is emitted at the moment the corresponding work actually happens
(the streaming endpoint forwards them to the UI live).
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from pydantic import ValidationError

from config import get_settings
from models.investigation import Diagnosis, InvestigationResponse, MemoryItem, TraceEvent
from services import hindsight_service, incident_service, llm_service
from services.llm_service import LLMError
from tools import TOOL_SCHEMAS, ToolError, execute_tool
from tools.memory_tools import mentions_failure

log = logging.getLogger("opsmind.agent")

SYSTEM_PROMPT = """You are OpsMind, an AI Site Reliability Engineering incident-response agent.

Your job is to investigate production incidents using CURRENT EVIDENCE and ORGANIZATIONAL MEMORY.

You have access to tools for:
- current incident information and simulated service health
- recent deployments
- team runbooks
- historical organizational memory stored in Hindsight (past incidents, root causes, successful
  resolutions, failed remediation attempts, engineer decisions and learned patterns)

IMPORTANT RULES:
1. Always investigate current evidence (service health, deployments) before making a recommendation.
2. Always search historical Hindsight memory for relevant incidents. Write a descriptive query with the
   service name and key symptoms/metrics (the tool also recalls failed attempts and engineer lessons).
3. Clearly distinguish current evidence, historical evidence, inference and recommendation.
4. Never invent metrics, incidents, resolutions, or historical facts. Only cite incident IDs that appear
   in tool results.
5. Historical memory is evidence, not proof.
6. If historical memory conflicts with current evidence (or with a runbook), explicitly say so.
7. Prefer previously successful remediation strategies when current evidence matches.
8. Pay close attention to failed remediation attempts and to engineer feedback stored in memory.
9. Never claim an action was performed unless the system actually performed it. You cannot perform actions.
10. Recommendations must be safe and reversible where possible.
11. Do not directly modify real infrastructure.
12. Explain WHY each recommendation follows from the evidence.

Work efficiently: you have a small tool budget. Call one tool at a time. Typical plan: service health,
recent deployments, Hindsight memory search, runbook. When you have enough evidence, reply with just
the word DONE (the diagnosis is written in a separate step)."""

FINAL_INSTRUCTION = """Using ONLY the investigation log above, produce the final incident diagnosis as JSON.

Field guidance:
- summary: 2-3 sentences for the incident channel.
- root_cause: short, specific root cause statement (inference from evidence).
- confidence: 0.0-1.0. High (>=0.8) only if current evidence strongly matches historical incidents.
- current_evidence: facts observed NOW from tool results (metrics, health, deployments). Include numbers.
- historical_matches: past incidents from Hindsight memory that match; incident_id must appear in the log;
  reason = why it matches; outcome = what resolved it (and what failed, if anything), stated ONLY as
  written in the memories — never add remediation steps that the memories do not mention.
- failed_approaches: remediation attempts that previously FAILED according to memory (empty if none found).
- learned_patterns: reusable lessons from memory that you applied. source = human-readable origin such as
  "Engineer feedback on INC-027", "INC-011 postmortem" or "Postmortem review" (never "M3"-style refs).
  Every relevant ENGINEER FEEDBACK memory in the log MUST appear here with from_engineer_feedback=true;
  set it true ONLY for memories marked ENGINEER FEEDBACK.
- recommended_actions: ordered, safe, reversible steps with a rationale tied to evidence.
- warnings: risks, conflicts between memory / runbooks / current evidence, and actions to avoid.

Weighting of evidence: memories marked ENGINEER FEEDBACK are explicit decisions by this team's engineers.
When their failure signature matches the current evidence, they take precedence over generic runbooks.
Never recommend (not even as a fallback) an action that matching engineer feedback or a documented
failed attempt says not to take; instead call out the conflict in warnings."""

DIAGNOSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "root_cause": {"type": "string"},
        "confidence": {"type": "number"},
        "current_evidence": {"type": "array", "items": {"type": "string"}},
        "historical_matches": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"incident_id": {"type": "string"}, "reason": {"type": "string"}, "outcome": {"type": "string"}},
                "required": ["incident_id", "reason", "outcome"],
                "additionalProperties": False,
            },
        },
        "failed_approaches": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"incident_id": {"type": "string"}, "action": {"type": "string"}, "result": {"type": "string"}},
                "required": ["incident_id", "action", "result"],
                "additionalProperties": False,
            },
        },
        "learned_patterns": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"pattern": {"type": "string"}, "source": {"type": "string"}, "from_engineer_feedback": {"type": "boolean"}},
                "required": ["pattern", "source", "from_engineer_feedback"],
                "additionalProperties": False,
            },
        },
        "recommended_actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"action": {"type": "string"}, "rationale": {"type": "string"}},
                "required": ["action", "rationale"],
                "additionalProperties": False,
            },
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "summary", "root_cause", "confidence", "current_evidence", "historical_matches",
        "failed_approaches", "learned_patterns", "recommended_actions", "warnings",
    ],
    "additionalProperties": False,
}

Emit = Callable[[dict[str, Any]], Awaitable[None]]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Tracer:
    def __init__(self, emit: Emit | None):
        self.events: list[TraceEvent] = []
        self._emit = emit
        self._t0: dict[str, float] = {}

    async def _send(self, ev: TraceEvent):
        if self._emit:
            await self._emit({"type": "trace", "event": ev.model_dump()})

    async def start(self, step: str, tool: str | None = None, detail: str | None = None) -> TraceEvent:
        ev = TraceEvent(id=uuid.uuid4().hex[:8], step=step, status="running", tool=tool, detail=detail, started_at=_now())
        self.events.append(ev)
        self._t0[ev.id] = time.perf_counter()
        await self._send(ev)
        return ev

    async def finish(self, ev: TraceEvent, status: str = "completed", detail: str | None = None):
        ev.status = status  # type: ignore[assignment]
        if detail is not None:
            ev.detail = detail
        ev.duration_ms = int((time.perf_counter() - self._t0.get(ev.id, time.perf_counter())) * 1000)
        await self._send(ev)

    async def point(self, step: str, status: str = "completed", detail: str | None = None, tool: str | None = None):
        ev = await self.start(step, tool=tool, detail=detail)
        await self.finish(ev, status=status, detail=detail)


def _step_label(name: str, args: dict[str, Any], ctx: dict[str, Any]) -> str:
    if name == "get_service_health":
        return "Analyzing current metrics"
    if name == "get_recent_deployments":
        return "Checking recent deployment"
    if name == "search_historical_incidents":
        return "Searching Hindsight memory"
    if name == "get_runbook":
        return "Checking runbook"
    if name == "get_incident":
        iid = str(args.get("incident_id", "")).upper()
        return "Inspecting incident record" if iid == ctx["incident"].id else f"Comparing previous resolution ({iid})"
    return name


def _tool_detail(name: str, args: dict[str, Any], result: dict[str, Any]) -> str:
    if "error" in result:
        return str(result["error"])[:160]
    if name == "get_service_health":
        rc, rs = result.get("redis_client", {}), result.get("redis_server", {})
        parts = [f"{k.replace('_', ' ')} {v}" for k, v in (result.get("api") or {}).items() if k in ("latency_p99", "error_rate")]
        if rc:
            parts.append(f"Redis pool {rc.get('pool_active')}")
        if rs:
            parts.append(f"Redis server CPU {rs.get('cpu')}, evictions {rs.get('evictions')}")
        if result.get("db_client"):
            parts.append(f"DB pool {result['db_client'].get('pool_active')}")
        return " · ".join(parts) or "Telemetry retrieved"
    if name == "get_recent_deployments":
        deps = result.get("deployments") or []
        if not deps:
            return "No recent deployments"
        d = deps[0]
        return f"{d['version']} deployed {d['deployed_minutes_ago']}m ago — {d['change']}"
    if name == "search_historical_incidents":
        return f"query: “{args.get('query', '')}”"
    if name == "get_runbook":
        return ", ".join(f"{r['id']} (reviewed {r['last_reviewed']})" for r in result.get("runbooks", []))
    if name == "get_incident":
        return (result.get("title") or "")[:120]
    return ""


def _memory_label(m: MemoryItem) -> str:
    if m.source == "engineer_feedback":
        return "ENGINEER FEEDBACK"
    return (m.memory_type or m.fact_type or "memory").upper()


def _investigation_log(incident, steps: list[dict[str, Any]], memories: list[MemoryItem]) -> str:
    lines = ["# INCIDENT UNDER INVESTIGATION", json.dumps({
        "id": incident.id, "title": incident.title, "service": incident.service, "severity": incident.severity,
        "summary": incident.summary, "alerts": incident.alerts, "metrics": [m.model_dump() for m in incident.metrics],
    }, indent=1), "", "# TOOL CALLS AND RESULTS (current evidence + runbooks)"]
    for s in steps:
        if s["name"] == "search_historical_incidents":
            lines.append(f"- search_historical_incidents(query={s['args'].get('query')!r}) -> {s.get('count', 0)} memories (listed below)")
        else:
            lines.append(f"- {s['name']}({json.dumps(s['args'])}) -> {json.dumps(s['result'])[:1500]}")
    lines += ["", "# HINDSIGHT MEMORIES RECALLED (historical evidence)"]
    if not memories:
        lines.append("(none — Hindsight memory unavailable or no matches)")
    # Engineer-taught memories first so they are never truncated away; then Hindsight's ranking.
    ordered = [m for m in memories if m.source == "engineer_feedback"] + [m for m in memories if m.source != "engineer_feedback"]
    for n, m in enumerate(ordered[:16], start=1):
        meta = f"incident={m.incident_id or '-'} type={_memory_label(m)}"
        if m.occurred_at:
            meta += f" when={m.occurred_at[:10]}"
        lines.append(f"[M{n}] ({meta}) {m.text[:450]}")
    return "\n".join(lines)


def _coerce_diagnosis(raw: dict[str, Any]) -> Diagnosis:
    """Validate with Pydantic, repairing common near-misses (e.g. confidence as 85 or '0.8')."""
    try:
        c = raw.get("confidence")
        if isinstance(c, str):
            c = float(c.strip().rstrip("%"))
        if isinstance(c, (int, float)) and c > 1:
            c = c / 100.0
        raw["confidence"] = max(0.0, min(1.0, float(c if c is not None else 0.5)))
    except (TypeError, ValueError):
        raw["confidence"] = 0.5
    for key in ("current_evidence", "historical_matches", "failed_approaches", "learned_patterns", "recommended_actions", "warnings"):
        if not isinstance(raw.get(key), list):
            raw[key] = []
    return Diagnosis.model_validate(raw)


async def investigate(incident_id: str, emit: Emit | None = None) -> InvestigationResponse:
    settings = get_settings()
    incident = incident_service.get_active_incident(incident_id)  # raises IncidentNotFound
    started, t0 = _now(), time.perf_counter()
    tracer = Tracer(emit)
    ctx: dict[str, Any] = {"incident": incident, "memories": {}, "memory_queries": [], "memory_error": None}
    steps: list[dict[str, Any]] = []
    diagnosis: Diagnosis | None = None
    diagnosis_error: str | None = None
    diagnosis_model = llm_service.model_name()
    tool_calls = 0

    incident_service.set_status(incident.id, "investigating")
    await tracer.point(f"Loaded incident {incident.id}", detail=f"{incident.service} · {incident.severity} · {incident.title}")

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "Investigate this incident. Incident record:\n" + json.dumps({
            "id": incident.id, "title": incident.title, "service": incident.service, "severity": incident.severity,
            "summary": incident.summary, "alerts": incident.alerts, "metrics": [m.model_dump() for m in incident.metrics],
        })},
    ]

    async def on_wait(seconds: float, reason: str):
        await tracer.point("Waiting for Groq rate limit", status="warning", detail=f"{reason} — retrying in {seconds:.0f}s")

    async def on_switch(frm: str, to: str):
        await tracer.point("Switching model (rate limit)", status="warning", detail=f"{frm} is rate limited — failing over to {to}")

    async def run_search(query: str, label: str = "Searching Hindsight memory") -> dict[str, Any]:
        ev = await tracer.start(label, tool="search_historical_incidents", detail=f"query: “{query}”")
        result = await execute_tool("search_historical_incidents", {"query": query}, ctx)
        if "error" in result:
            await tracer.finish(ev, status="failed", detail=result["error"])
        else:
            await tracer.finish(ev)
            ids = sorted({i for m in ctx["memories"].values() for i in m.mentioned_incidents})
            await tracer.point(
                "Found relevant historical memories" if result["count"] else "No matching memories found",
                status="completed" if result["count"] else "warning",
                detail=f"{result['count']} memories recalled · incidents referenced: {', '.join(ids[:8]) or '—'}",
            )
            if emit:
                await emit({"type": "memories", "memories": [m.model_dump() for m in ctx["memories"].values()],
                            "queries": ctx["memory_queries"]})
        return result

    # ------------------------------------------------------------------ agent loop
    try:
        for iteration in range(settings.max_tool_iterations):
            thinking = await tracer.start("Planning next investigation step", detail=f"iteration {iteration + 1}/{settings.max_tool_iterations}")
            msg, used_model = await llm_service.chat_with_tools(messages, TOOL_SCHEMAS, on_wait=on_wait, on_switch=on_switch)
            calls = msg.tool_calls or []
            if not calls:
                await tracer.finish(thinking, detail=f"Agent has enough evidence · {used_model}")
                break
            await tracer.finish(thinking, detail=", ".join(c.function.name for c in calls) + f" · {used_model}")
            messages.append({
                "role": "assistant", "content": msg.content or "",
                "tool_calls": [{"id": c.id, "type": "function", "function": {"name": c.function.name, "arguments": c.function.arguments or "{}"}} for c in calls],
            })
            for call in calls:
                tool_calls += 1
                name = call.function.name
                try:
                    args = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = None
                if name == "search_historical_incidents" and isinstance(args, dict) and isinstance(args.get("query"), str) and args["query"].strip():
                    result = await run_search(args["query"][:500])
                    steps.append({"name": name, "args": args, "result": {}, "count": result.get("count", 0)})
                else:
                    ev = await tracer.start(_step_label(name, args if isinstance(args, dict) else {}, ctx), tool=name)
                    try:
                        if args is None:
                            raise ToolError("Tool arguments were not valid JSON")
                        result = await execute_tool(name, args, ctx)
                        await tracer.finish(ev, status="warning" if "error" in result else "completed", detail=_tool_detail(name, args, result))
                    except ToolError as e:
                        result = {"error": str(e)}
                        await tracer.finish(ev, status="warning", detail=str(e))
                    steps.append({"name": name, "args": args if isinstance(args, dict) else {}, "result": result})
                messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result)[:6000]})
        else:
            await tracer.point("Tool budget used", detail=f"{settings.max_tool_iterations}/{settings.max_tool_iterations} tool iterations — proceeding to diagnosis")
    except LLMError as e:
        diagnosis_error = e.message
        await tracer.point("LLM unavailable", status="failed", detail=e.message)

    # Guardrail: the agent must consult organizational memory. If it did not, do it now.
    if not ctx["memory_queries"] and ctx["memory_error"] is None:
        query = f"{incident.service} {incident.title}. " + "; ".join(f"{m.label} {m.value}" for m in incident.metrics)
        result = await run_search(query, label="Searching Hindsight memory (guardrail)")
        steps.append({"name": "search_historical_incidents", "args": {"query": query}, "result": {}, "count": result.get("count", 0)})

    memories = sorted(ctx["memories"].values(), key=lambda m: m.score if m.score is not None else -1, reverse=True)

    # Derived from the actually-recalled memories (not from any hard-coded answer).
    failed = [m for m in memories if mentions_failure(m)]
    if memories:
        await tracer.point(
            "Checking failed remediation attempts",
            status="completed",
            detail=(f"{len(failed)} memories describe failed or discouraged actions · incidents: "
                    + (", ".join(sorted({i for m in failed for i in m.mentioned_incidents})) or "—"))
            if failed else "No failed attempts recalled",
        )
    taught = [m for m in memories if m.source == "engineer_feedback"]
    if taught:
        await tracer.point("Applying engineer-taught lessons", detail=f"{len(taught)} memory(ies) retained from engineer feedback recalled")

    # ------------------------------------------------------------------ final synthesis
    if diagnosis_error is None:
        ev = await tracer.start("Generating recommendation", detail=f"{llm_service.model_name()} · structured output")
        used: dict[str, str] = {}
        try:
            raw = await llm_service.structured(
                [{"role": "system", "content": SYSTEM_PROMPT},
                 {"role": "user", "content": _investigation_log(incident, steps, memories) + "\n\n" + FINAL_INSTRUCTION}],
                "incident_diagnosis", DIAGNOSIS_SCHEMA, effort="medium", max_tokens=3000, on_wait=on_wait, on_switch=on_switch, used=used,
            )
            diagnosis = _coerce_diagnosis(raw)
            diagnosis_model = used.get("model", llm_service.model_name())
            await tracer.finish(ev, detail=f"{diagnosis_model} · Root cause: {diagnosis.root_cause[:110]}")
        except LLMError as e:
            diagnosis_error = e.message
            await tracer.finish(ev, status="failed", detail=e.message)
        except ValidationError as e:
            log.warning("Diagnosis failed validation: %s", e)
            diagnosis_error = "The LLM returned a diagnosis that failed validation."
            await tracer.finish(ev, status="failed", detail=diagnosis_error)

    memory_status = "unavailable" if ctx["memory_error"] and not memories else ("ok" if ctx["memory_queries"] else "not_used")
    response = InvestigationResponse(
        investigation_id=uuid.uuid4().hex[:12],
        incident=incident,
        diagnosis=diagnosis,
        diagnosis_error=diagnosis_error,
        memories=memories,
        memory_status=memory_status,
        memory_error=ctx["memory_error"],
        memory_queries=ctx["memory_queries"],
        trace=tracer.events,
        tool_calls=tool_calls,
        model=diagnosis_model,
        started_at=started,
        completed_at=_now(),
        duration_ms=int((time.perf_counter() - t0) * 1000),
    )
    incident_service.set_status(incident.id, "diagnosed" if diagnosis else "open")
    if diagnosis:
        incident_service.save_investigation(incident.id, {
            "investigation_id": response.investigation_id,
            "root_cause": diagnosis.root_cause,
            "confidence": diagnosis.confidence,
            "recommended_actions": [a.action for a in diagnosis.recommended_actions],
            "current_evidence": diagnosis.current_evidence,
            "completed_at": response.completed_at,
        })
    return response
