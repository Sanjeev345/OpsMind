from fastapi import APIRouter
from pydantic import BaseModel

from services import hindsight_service, incident_service

router = APIRouter(prefix="/api/memory", tags=["memory"])


class SeedRequest(BaseModel):
    reset: bool = False


class RecallRequest(BaseModel):
    query: str


@router.get("/stats")
async def stats():
    s = await hindsight_service.get_memory_stats()
    s["engineer_lessons"] = len(incident_service.get_state().get("feedback", []))
    return s


@router.post("/seed")
async def seed(req: SeedRequest):
    items = incident_service.historical_memory_items(hindsight_service.build_item)
    return await hindsight_service.seed_memories(items, reset=req.reset)


@router.post("/recall")
async def recall(req: RecallRequest):
    """Direct recall (debug / transparency)."""
    return {"query": req.query, "memories": [m.model_dump() for m in await hindsight_service.recall_memories(req.query)]}
