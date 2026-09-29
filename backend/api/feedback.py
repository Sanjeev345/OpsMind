from fastapi import APIRouter

from models.feedback import FeedbackRequest, FeedbackResponse
from services import learning_service

router = APIRouter(prefix="/api", tags=["learning"])


@router.post("/feedback", response_model=FeedbackResponse)
async def feedback(req: FeedbackRequest):
    """Engineer feedback -> retained into Hindsight (synchronously, so it is immediately recallable)."""
    return await learning_service.learn_from_feedback(req)
