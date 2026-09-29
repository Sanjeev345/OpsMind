"""Hindsight-backed tools. They go through services (never the Hindsight SDK directly)."""
import asyncio
import re
from typing import Any

from services import hindsight_service, learning_service
from models.feedback import FeedbackRequest


FAILURE_RE = re.compile(r"\bfail(ed|ure)?\b|did not (resolve|help|work)|no effect|persisted|wrong call|not required|do not|don't", re.I)


def mentions_failure(m) -> bool:
    return m.memory_type == "failed_approach" or bool(FAILURE_RE.search(m.text))


LESSON_TAGS = ["failed_approach", "engineer_decision", "engineer_feedback"]


async def search_historical_incidents(query: str, ctx: dict[str, Any]) -> dict[str, Any]:
    """Recall organizational memory from Hindsight. Results are recorded in ctx for the UI.

    Runs the agent's query plus a companion recall focused on failed remediations and engineer
    lessons for the same situation (both queries are shown in the UI).
    """
    companion = f"{query} — failed remediation attempts, what did not work, engineer lessons and decisions"
    try:
        primary, lessons = await asyncio.gather(
            hindsight_service.recall_memories(query, limit=10),
            # Tag-filtered recall: only failed attempts, engineer decisions and engineer-taught lessons.
            hindsight_service.recall_memories(companion, limit=8, tags=LESSON_TAGS, tags_match="any_strict"),
        )
    except hindsight_service.HindsightError as e:
        ctx["memory_error"] = e.message
        return {"error": f"Hindsight memory unavailable: {e.message}. Continue with current evidence only."}
    ctx["memory_queries"] += [query, f"{companion}  [tags: {', '.join(LESSON_TAGS)}]"]
    memories = list({m.id: m for m in primary + lessons}.values())
    for m in memories:
        ctx["memories"].setdefault(m.id, m)
    # Compact view for the tool loop (token budget); the final synthesis receives full memory text.
    # Engineer lessons and failure memories are always included in the compact view.
    priority = [m for m in memories if m.source == "engineer_feedback"] + [m for m in memories if mentions_failure(m)]
    compact = list({m.id: m for m in priority[:4] + primary[:4]}.values())
    results = []
    for m in compact:
        results.append({
            "incident_id": m.incident_id,
            "memory_type": m.memory_type or m.fact_type,
            "source": m.source,
            "text": m.text[:220],
            "hindsight_score": round(m.score, 3) if m.score is not None else None,
        })
    return {"query": query, "count": len(memories), "memories": results}


async def record_engineer_feedback(
    incident_id: str, correct: bool, actual_root_cause: str, actual_resolution: str, engineer_note: str
) -> dict[str, Any]:
    """Human-in-the-loop tool: only invoked from the /api/feedback endpoint, never by the LLM itself."""
    req = FeedbackRequest(
        incident_id=incident_id, correct=correct, actual_root_cause=actual_root_cause,
        actual_resolution=actual_resolution, engineer_note=engineer_note,
    )
    return (await learning_service.learn_from_feedback(req)).model_dump()
