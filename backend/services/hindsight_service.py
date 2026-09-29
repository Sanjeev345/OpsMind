"""The ONLY module in OpsMind that talks to Hindsight.

Uses the official `hindsight-client` Python SDK (async `a*` methods, as recommended for
FastAPI). Every call is wrapped so callers get a `HindsightError` with a user-safe message
instead of raw SDK / network exceptions.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from typing import Any

from hindsight_client import Hindsight
from hindsight_client_api.exceptions import ApiException

from config import get_settings
from models.investigation import MemoryItem

log = logging.getLogger("opsmind.hindsight")

# Document-id prefixes owned by OpsMind. Reset only ever deletes documents with these
# prefixes, so unrelated data in the bank is never touched.
SEED_PREFIXES = ("incident-", "failed-", "pattern-", "decision-")
LEARNED_PREFIXES = ("feedback-", "lesson-")

BANK_RETAIN_MISSION = (
    "This bank is the organizational memory of an SRE team. Extract durable incident-response "
    "knowledge: incident IDs, affected service, symptoms and metric values, root cause, the "
    "remediation that worked, remediation attempts that FAILED and why, and engineer decisions "
    "or lessons. Always preserve incident IDs (e.g. INC-011) and service names verbatim."
)
BANK_REFLECT_MISSION = (
    "You are the institutional memory of an SRE team. Answer with evidence from past incidents, "
    "citing incident IDs, and highlight failed remediation attempts."
)


class HindsightError(Exception):
    """Application-level Hindsight failure with a message safe to show in the UI."""

    def __init__(self, message: str, code: str = "hindsight_unavailable", status: int = 503):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status


_client: Hindsight | None = None


def is_configured() -> bool:
    return bool(get_settings().hindsight_api_key)


def bank_id() -> str:
    return get_settings().hindsight_bank_id


def _get_client() -> Hindsight:
    global _client
    s = get_settings()
    if not s.hindsight_api_key:
        raise HindsightError(
            "HINDSIGHT_API_KEY is not set. Add it to .env to enable organizational memory.",
            code="hindsight_not_configured",
        )
    if _client is None:
        _client = Hindsight(
            base_url=s.hindsight_base_url,
            api_key=s.hindsight_api_key,
            timeout=s.hindsight_timeout_seconds,
            user_agent="opsmind/1.0",
        )
    return _client


async def close() -> None:
    global _client
    if _client is not None:
        try:
            await _client.aclose()
        finally:
            _client = None


async def _call(op: str, coro, timeout: float | None = None):
    """Run an SDK coroutine, translating every failure into HindsightError."""
    timeout = timeout or get_settings().hindsight_timeout_seconds
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except HindsightError:
        raise
    except asyncio.TimeoutError:
        log.warning("Hindsight %s timed out after %.0fs", op, timeout)
        raise HindsightError(f"Hindsight {op} timed out.", code="hindsight_timeout", status=504)
    except ApiException as e:
        log.warning("Hindsight %s failed: status=%s reason=%s body=%s", op, e.status, e.reason, (e.body or "")[:500])
        if e.status in (401, 403):
            raise HindsightError(
                "Hindsight rejected the API key. Check HINDSIGHT_API_KEY.", code="hindsight_auth", status=502
            )
        if e.status == 404:
            raise HindsightError(f"Hindsight {op}: resource not found.", code="hindsight_not_found", status=404)
        if e.status == 429:
            raise HindsightError("Hindsight rate limit reached. Try again shortly.", code="hindsight_rate_limited")
        raise HindsightError(f"Hindsight {op} failed (HTTP {e.status}).")
    except (ValueError, TypeError, KeyError) as e:
        log.exception("Malformed Hindsight %s response", op)
        raise HindsightError(f"Hindsight returned a malformed {op} response.", code="hindsight_malformed") from e
    except Exception as e:  # network errors (aiohttp.ClientError, OSError, ...)
        log.warning("Hindsight %s network error: %r", op, e)
        raise HindsightError("Hindsight is unreachable (network error).") from e


# --------------------------------------------------------------------------- bank


async def ensure_bank() -> dict[str, Any]:
    """Create the bank if missing, or update its missions (create_or_update is idempotent)."""
    c = _get_client()
    profile = await _call(
        "create_bank",
        c.acreate_bank(
            bank_id(),
            retain_mission=BANK_RETAIN_MISSION,
            reflect_mission=BANK_REFLECT_MISSION,
        ),
    )
    return {"bank_id": profile.bank_id, "name": profile.name}


async def ping(timeout: float = 8.0) -> dict[str, Any]:
    """Cheap connectivity/auth check. Returns whether the configured bank exists."""
    c = _get_client()
    resp = await _call("list_banks", c.banks.list_banks(), timeout=timeout)
    ids = [b.bank_id for b in resp.banks]
    return {"connected": True, "bank_exists": bank_id() in ids}


# --------------------------------------------------------------------------- retain


def _clean_metadata(metadata: dict[str, Any] | None) -> dict[str, str]:
    # Hindsight metadata values must be strings.
    return {str(k): str(v) for k, v in (metadata or {}).items() if v is not None}


def build_item(
    content: str,
    document_id: str,
    metadata: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    context: str | None = None,
    timestamp: datetime | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "content": content,
        "document_id": document_id,
        "metadata": _clean_metadata(metadata),
        "tags": tags or [],
        "update_mode": "replace",  # stable document ids => re-seeding replaces instead of duplicating
    }
    if context:
        item["context"] = context
    if timestamp:
        item["timestamp"] = timestamp
    return item


async def retain_memory(
    content: str,
    document_id: str,
    metadata: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    context: str | None = None,
    timestamp: datetime | None = None,
) -> dict[str, Any]:
    """Synchronously retain one memory (it is recallable as soon as this returns)."""
    return await retain_batch([build_item(content, document_id, metadata, tags, context, timestamp)])


async def retain_batch(items: list[dict[str, Any]], retain_async: bool = False) -> dict[str, Any]:
    c = _get_client()
    resp = await _call(
        "retain",
        c.aretain_batch(bank_id=bank_id(), items=items, retain_async=retain_async),
        timeout=180 if not retain_async else 60,
    )
    if not resp.success:
        raise HindsightError("Hindsight did not confirm the retain operation.", code="hindsight_retain_failed")
    return {
        "success": resp.success,
        "bank_id": resp.bank_id,
        "items_count": resp.items_count,
        "async": resp.var_async,
        "operation_id": resp.operation_id,
    }


# --------------------------------------------------------------------------- recall


_INC_RE = re.compile(r"\bINC-\d{3}\b")


def _to_memory_item(r: Any, query: str) -> MemoryItem:
    md = dict(r.metadata or {})
    score = None
    if r.scores is not None and r.scores.final is not None:
        score = float(r.scores.final)
    mentioned = list(dict.fromkeys(([md["incident_id"]] if md.get("incident_id") else []) + _INC_RE.findall(r.text or "")))
    return MemoryItem(
        id=r.id,
        mentioned_incidents=mentioned,
        text=r.text,
        fact_type=r.type,
        document_id=r.document_id,
        memory_type=md.get("type"),
        incident_id=md.get("incident_id"),
        source=md.get("source"),
        metadata=md,
        tags=list(r.tags or []),
        score=score,
        occurred_at=r.occurred_start or r.mentioned_at,
        query=query,
    )


async def recall_memories(
    query: str,
    limit: int = 12,
    max_tokens: int = 3000,
    budget: str = "mid",
    tags: list[str] | None = None,
    tags_match: str = "any",
) -> list[MemoryItem]:
    """Semantic + keyword + graph + temporal recall from the OpsMind bank (optionally tag-filtered)."""
    if not query.strip():
        return []
    c = _get_client()
    kwargs: dict[str, Any] = {"bank_id": bank_id(), "query": query, "max_tokens": max_tokens, "budget": budget}
    if tags:
        kwargs["tags"] = tags
        kwargs["tags_match"] = tags_match
    resp = await _call("recall", c.arecall(**kwargs))
    if resp is None or not hasattr(resp, "results"):
        raise HindsightError("Hindsight returned a malformed recall response.", code="hindsight_malformed")
    return [_to_memory_item(r, query) for r in resp.results[:limit]]


# --------------------------------------------------------------------------- stats / docs


async def get_memory_stats() -> dict[str, Any]:
    c = _get_client()
    s = await _call("stats", c.banks.get_agent_stats(bank_id(), refresh=True), timeout=20)
    return {
        "bank_id": s.bank_id,
        "total_memories": s.total_nodes,
        "total_documents": s.total_documents,
        "total_links": s.total_links,
        "total_observations": s.total_observations or 0,
        "memories_by_type": dict(s.nodes_by_fact_type or {}),
        "links_by_type": dict(s.links_by_link_type or {}),
        "pending_operations": s.pending_operations,
        "failed_operations": s.failed_operations,
        "last_memory_write_at": s.last_memory_write_at,
        "last_consolidated_at": s.last_consolidated_at,
    }


async def list_document_ids(prefixes: tuple[str, ...]) -> list[str]:
    c = _get_client()
    ids: list[str] = []
    offset = 0
    while True:
        page = await _call("list_documents", c.documents.list_documents(bank_id(), limit=200, offset=offset))
        ids.extend(d.id for d in page.items if d.id.startswith(prefixes))
        offset += len(page.items)
        if not page.items or offset >= page.total:
            break
    return ids


async def delete_documents(document_ids: list[str]) -> int:
    c = _get_client()
    deleted = 0
    for doc_id in document_ids:
        try:
            await _call("delete_document", c.documents.delete_document(bank_id(), doc_id))
            deleted += 1
        except HindsightError as e:
            if e.code != "hindsight_not_found":
                raise
    return deleted


async def wait_for_pending(timeout: float = 240.0, on_progress=None) -> dict[str, Any]:
    """Poll bank stats until async retain operations drain."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        stats = await get_memory_stats()
        if on_progress:
            on_progress(stats)
        if stats["pending_operations"] == 0:
            return stats
        if loop.time() > deadline:
            raise HindsightError("Timed out waiting for Hindsight to process seeded memories.", code="hindsight_timeout")
        await asyncio.sleep(3)


# --------------------------------------------------------------------------- seeding


async def seed_memories(items: list[dict[str, Any]], reset: bool = False, on_progress=None) -> dict[str, Any]:
    """Seed OpsMind historical memories. Stable document ids make this idempotent.

    reset=True first deletes OpsMind-owned documents (seed + learned prefixes only).
    """
    await ensure_bank()
    deleted = 0
    if reset:
        existing = await list_document_ids(SEED_PREFIXES + LEARNED_PREFIXES)
        deleted = await delete_documents(existing)
        if on_progress:
            on_progress({"deleted": deleted})
    submitted = 0
    for i in range(0, len(items), 10):
        chunk = items[i : i + 10]
        await retain_batch(chunk, retain_async=True)
        submitted += len(chunk)
        if on_progress:
            on_progress({"submitted": submitted, "total": len(items)})
    stats = await wait_for_pending(on_progress=on_progress)
    return {"bank_id": bank_id(), "documents_submitted": submitted, "deleted": deleted, "stats": stats}
