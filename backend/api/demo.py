from fastapi import APIRouter
from pydantic import BaseModel

from services import hindsight_service, incident_service

router = APIRouter(prefix="/api/demo", tags=["demo"])


class ResetRequest(BaseModel):
    reseed: bool = False


@router.post("/reset")
async def reset(req: ResetRequest | None = None):
    """Reset local demo state and delete ONLY engineer-feedback memories created by OpsMind.

    reseed=true additionally re-seeds historical memories (stable ids, no duplicates).
    """
    req = req or ResetRequest()
    incident_service.reset_state()
    learned = await hindsight_service.list_document_ids(hindsight_service.LEARNED_PREFIXES)
    deleted = await hindsight_service.delete_documents(learned)
    seeded = None
    if req.reseed:
        items = incident_service.historical_memory_items(hindsight_service.build_item)
        seeded = await hindsight_service.seed_memories(items, reset=False)
    return {"reset": True, "deleted_learned_memories": deleted, "deleted_document_ids": learned, "seeded": seeded}
