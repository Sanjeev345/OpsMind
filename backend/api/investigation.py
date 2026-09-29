import asyncio
import json
import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from models.investigation import InvestigateRequest, InvestigationResponse
from services import agent_service, incident_service
from services.llm_service import LLMError

router = APIRouter(prefix="/api", tags=["investigation"])
log = logging.getLogger("opsmind.api")


@router.post("/investigate", response_model=InvestigationResponse)
async def investigate(req: InvestigateRequest):
    return await agent_service.investigate(req.incident_id)


@router.post("/investigate/stream")
async def investigate_stream(req: InvestigateRequest):
    """NDJSON stream: trace events as they happen, memories as they are recalled, then the result."""
    incident_service.get_active_incident(req.incident_id)  # 404 before the stream starts
    queue: asyncio.Queue = asyncio.Queue()

    async def emit(event: dict):
        await queue.put(event)

    async def run():
        try:
            result = await agent_service.investigate(req.incident_id, emit=emit)
            await queue.put({"type": "result", "result": result.model_dump()})
        except LLMError as e:
            await queue.put({"type": "error", "code": e.code, "message": e.message})
        except Exception:
            log.exception("Investigation failed")
            await queue.put({"type": "error", "code": "internal", "message": "Investigation failed unexpectedly. See server logs."})
        finally:
            await queue.put(None)

    async def body():
        task = asyncio.create_task(run())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield json.dumps(item, default=str) + "\n"
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(body(), media_type="application/x-ndjson", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
