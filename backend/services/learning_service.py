"""Turns engineer feedback into durable Hindsight memories (the learning loop)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from models.feedback import FeedbackRequest, FeedbackResponse, RetainedMemory
from services import hindsight_service, incident_service, llm_service

log = logging.getLogger("opsmind.learning")

LESSON_SCHEMA = {
    "type": "object",
    "properties": {
        "lesson": {"type": "string"},
    },
    "required": ["lesson"],
    "additionalProperties": False,
}


def _signature(incident) -> str:
    """Observable failure signature of the incident, so future recalls match on symptoms."""
    parts = [f"{m.label} {m.value}" for m in incident.metrics]
    rs = (incident.health or {}).get("redis_server")
    if rs:
        parts.append(f"Redis server CPU {rs.get('cpu')}, memory {rs.get('memory')}, evictions {rs.get('evictions')}")
    db = (incident.health or {}).get("postgres")
    if db and "db_client" in (incident.health or {}):
        parts.append(f"Postgres CPU {db.get('cpu')}")
    if incident.deployments:
        d = incident.deployments[0]
        parts.append(f"after deploy {d['version']} ({d['change']})")
    return "; ".join(parts)


async def _distill_lesson(req: FeedbackRequest, incident, diagnosis_root_cause: str | None, signature: str) -> tuple[str, str]:
    """Ask the LLM to generalize the feedback into one reusable rule. Falls back to a template."""
    verdict = "CORRECT" if req.correct else "INCORRECT"
    if llm_service.is_configured():
        try:
            out = await llm_service.structured(
                [
                    {"role": "system", "content": "You write concise, reusable SRE lessons for an incident-response memory system. "
                     "Generalize from ONE incident to a rule for future incidents with the same failure signature. "
                     "Use only the facts given. 1-3 sentences. Start with 'When <service> shows ...'. "
                     "Preserve every explicit instruction from the engineer (especially 'do not ...') verbatim in meaning."},
                    {"role": "user", "content": (
                        f"Incident {incident.id} on {incident.service}. Failure signature: {signature}.\n"
                        f"OpsMind diagnosis: {diagnosis_root_cause or 'n/a'} — engineer verdict: {verdict}.\n"
                        f"Actual root cause: {req.actual_root_cause or diagnosis_root_cause or 'n/a'}\n"
                        f"Actual resolution: {req.actual_resolution or 'n/a'}\n"
                        f"Engineer note: {req.engineer_note or 'n/a'}"
                    )},
                ],
                "lesson", LESSON_SCHEMA, effort="low", max_tokens=600,
                # Fallback models first: keeps the primary model's TPM budget for diagnoses.
                models=llm_service.structured_model_chain()[1:] + [llm_service.model_name()],
            )
            lesson = str(out.get("lesson", "")).strip()
            if lesson:
                return lesson, "llm"
        except llm_service.LLMError as e:
            log.warning("Lesson distillation failed, using template: %s", e.message)
    lesson = (
        f"When {incident.service} shows {signature}, the root cause was "
        f"{req.actual_root_cause or diagnosis_root_cause}. Resolution: {req.actual_resolution or 'see incident'}."
        + (f" Engineer guidance: {req.engineer_note}" if req.engineer_note else "")
    )
    return lesson, "template"


async def learn_from_feedback(req: FeedbackRequest) -> FeedbackResponse:
    incident = incident_service.get_active_incident(req.incident_id)  # raises IncidentNotFound
    last = incident_service.last_investigation(incident.id) or {}
    diag_rc = last.get("root_cause")
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%S")
    signature = _signature(incident)
    verdict = "CORRECT" if req.correct else "INCORRECT"
    root_cause = req.actual_root_cause or diag_rc or "unspecified"

    decision_text = "\n".join(filter(None, [
        f"Engineer feedback on incident {incident.id} ({incident.severity}, {incident.service}, {now.date().isoformat()}).",
        f"Failure signature: {signature}.",
        f"OpsMind's diagnosis was: {diag_rc}. The engineer marked it {verdict}." if diag_rc else f"The engineer marked OpsMind's diagnosis {verdict}.",
        f"Confirmed root cause: {root_cause}.",
        f"Resolution that was applied: {req.actual_resolution}." if req.actual_resolution else None,
        f"Engineer note: {req.engineer_note}" if req.engineer_note else None,
    ]))
    lesson, generated_by = await _distill_lesson(req, incident, diag_rc, signature)
    lesson_text = f"Lesson learned from engineer feedback on {incident.id} ({incident.service}): {lesson}"

    base_meta = {"incident_id": incident.id, "service": incident.service, "source": "engineer_feedback",
                 "verdict": verdict.lower(), "stored_at": now.isoformat()}
    docs = [
        (f"feedback-{incident.id}-{stamp}", "engineer_decision", decision_text, "Engineer feedback submitted in OpsMind after an investigation"),
        (f"lesson-{incident.id}-{stamp}", "learned_pattern", lesson_text, "Reusable lesson distilled from engineer feedback"),
    ]
    items = [
        hindsight_service.build_item(
            content=text, document_id=doc_id, metadata={**base_meta, "type": mtype},
            tags=["engineer_feedback", mtype, incident.service], context=context, timestamp=now,
        )
        for doc_id, mtype, text, context in docs
    ]
    # Synchronous retain: when this returns, the memories are already recallable.
    result = await hindsight_service.retain_batch(items, retain_async=False)
    log.info("Retained engineer feedback for %s: %s", incident.id, result)

    incident_service.set_status(incident.id, "resolved")
    incident_service.record_feedback({
        "incident_id": incident.id, "correct": req.correct, "document_ids": [d[0] for d in docs],
        "stored_at": now.isoformat(), "lesson": lesson,
    })
    stats = None
    try:
        stats = await hindsight_service.get_memory_stats()
    except hindsight_service.HindsightError:
        pass
    return FeedbackResponse(
        stored=True,
        incident_id=incident.id,
        bank_id=result["bank_id"],
        retained=[RetainedMemory(document_id=d, memory_type=t, content=c) for d, t, c, _ in docs],
        lesson=lesson,
        lesson_generated_by=generated_by,
        stored_at=now.isoformat(),
        memory_stats=stats,
    )
