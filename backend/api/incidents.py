from fastapi import APIRouter

from services import incident_service

router = APIRouter(prefix="/api", tags=["incidents"])


@router.get("/incidents")
async def list_incidents():
    return {"incidents": [i.model_dump() for i in incident_service.list_incidents()]}


@router.get("/incidents/{incident_id}")
async def get_incident(incident_id: str):
    inc = incident_service.get_any_incident(incident_id)  # IncidentNotFound -> 404 handler
    if inc["kind"] == "active":
        return {"kind": "active", "incident": incident_service.get_active_incident(incident_id).model_dump(),
                "last_investigation": incident_service.last_investigation(inc["id"])}
    return {"kind": "historical", "incident": inc}
