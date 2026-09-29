"""OpsMind FastAPI backend."""
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api import demo, feedback, incidents, investigation, memory
from config import get_settings
from services import hindsight_service, llm_service
from services.hindsight_service import HindsightError
from services.incident_service import IncidentNotFound
from services.llm_service import LLMError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("opsmind")


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    log.info("OpsMind starting: bank=%s model=%s hindsight=%s", s.hindsight_bank_id, s.groq_model, s.hindsight_base_url)
    if not s.hindsight_api_key:
        log.warning("HINDSIGHT_API_KEY missing - memory features disabled")
    if not s.groq_api_key:
        log.warning("GROQ_API_KEY missing - agent disabled")
    yield
    await hindsight_service.close()


app = FastAPI(title="OpsMind", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().frontend_url, "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _err(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


@app.exception_handler(IncidentNotFound)
async def _not_found(_: Request, e: IncidentNotFound):
    return _err(404, "incident_not_found", f"Incident {e.incident_id} not found")


@app.exception_handler(HindsightError)
async def _hindsight(_: Request, e: HindsightError):
    return _err(e.status, e.code, e.message)


@app.exception_handler(LLMError)
async def _llm(_: Request, e: LLMError):
    return _err(e.status, e.code, e.message)


@app.exception_handler(RequestValidationError)
async def _validation(_: Request, e: RequestValidationError):
    msgs = []
    for err in e.errors():
        loc = ".".join(str(p) for p in err.get("loc", []) if p != "body")
        msgs.append(f"{loc}: {err.get('msg')}" if loc else str(err.get("msg")))
    return _err(400, "invalid_request", "; ".join(msgs) or "Invalid request")


@app.exception_handler(Exception)
async def _unhandled(_: Request, e: Exception):
    log.exception("Unhandled error")
    return _err(500, "internal", "Internal server error. See server logs.")


app.include_router(incidents.router)
app.include_router(investigation.router)
app.include_router(feedback.router)
app.include_router(memory.router)
app.include_router(demo.router)

_health_cache: dict = {"at": 0.0, "data": None}


@app.get("/api/health")
async def health():
    if _health_cache["data"] and time.time() - _health_cache["at"] < 20:
        return _health_cache["data"]
    s = get_settings()
    out = {"status": "ok", "bank_id": s.hindsight_bank_id, "model": s.groq_model,
           "hindsight": {"configured": hindsight_service.is_configured(), "connected": False},
           "groq": {"configured": llm_service.is_configured(), "connected": False}}
    if out["hindsight"]["configured"]:
        try:
            out["hindsight"].update(await hindsight_service.ping())
        except HindsightError as e:
            out["hindsight"]["error"] = e.message
    if out["groq"]["configured"]:
        try:
            out["groq"].update(await llm_service.ping())
        except LLMError as e:
            out["groq"]["error"] = e.message
    if not (out["hindsight"]["connected"] and out["groq"]["connected"]):
        out["status"] = "degraded"
    _health_cache.update(at=time.time(), data=out)
    return out
