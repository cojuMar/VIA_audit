"""
Trust Portal Service — Sprint 10
Port: 3015

Public routes  — tenant resolved from portal slug
Admin routes   — tenant from X-Tenant-ID header
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Optional
from uuid import UUID

import asyncpg
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import JSONResponse

from .access_logger import AccessLogger
from .chatbot import PortalChatbot
from .compliance_badges import ComplianceBadgeService
from .config import settings
from .db import close_pool, get_pool
from .document_gateway import DocumentGateway
from .models import DeflectionRequest, NDAAcceptance
from .nda_manager import NDAManager
from .portal_config import PortalConfigManager
from .questionnaire_deflector import QuestionnaireDeflector

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ---------------------------------------------------------------------------
# Singletons (initialised in lifespan)
# ---------------------------------------------------------------------------

_portal_config_mgr = PortalConfigManager()
_doc_gateway = DocumentGateway(settings)
_nda_manager = NDAManager()
_deflector = QuestionnaireDeflector(settings)
_chatbot = PortalChatbot(settings)
_access_logger = AccessLogger()
_badge_service = ComplianceBadgeService(settings)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = await get_pool()
    logger.info("DB pool ready")

    # Ensure MinIO bucket exists (best-effort)
    if _doc_gateway._minio is not None:
        try:
            _doc_gateway._ensure_bucket()
            logger.info("MinIO bucket '%s' ready", settings.minio_bucket_portal)
        except Exception as exc:
            logger.warning("Could not verify MinIO bucket: %s", exc)

    yield

    await close_pool()
    logger.info("DB pool closed")


app = FastAPI(
    title="Trust Portal Service",
    version="10.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

async def get_db() -> asyncpg.Pool:
    return await get_pool()


async def get_tenant_id(x_tenant_id: str = Header(..., alias="X-Tenant-ID")) -> str:
    """Validate and return the tenant UUID from the X-Tenant-ID header."""
    try:
        UUID(x_tenant_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid X-Tenant-ID: must be a UUID")
    return x_tenant_id


def get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


# ---------------------------------------------------------------------------
# Helper: resolve tenant_id from slug (public routes)
# ---------------------------------------------------------------------------

async def _resolve_slug(pool: asyncpg.Pool, slug: str) -> str:
    config = await _portal_config_mgr.get_by_slug(pool, slug)
    if config is None:
        raise HTTPException(status_code=404, detail="Portal not found")
    return str(config["tenant_id"])


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok", "service": "trust-portal-service"}


# ---------------------------------------------------------------------------
# PUBLIC ROUTES
# ---------------------------------------------------------------------------

@app.get("/portal/{slug}")
async def get_portal(
    slug: str,
    request: Request,
    pool: asyncpg.Pool = Depends(get_db),
):
    """Return portal config + compliance badges."""
    config = await _portal_config_mgr.get_by_slug(pool, slug)
    if config is None:
        raise HTTPException(status_code=404, detail="Portal not found")

    tenant_id = str(config["tenant_id"])
    ip = get_client_ip(request)

    badges: list[dict] = []
    if config.get("show_compliance_scores") and config.get("allowed_frameworks"):
        badges = await _badge_service.get_badges(
            tenant_id, config["allowed_frameworks"]
        )

    await _access_logger.log(
        pool,
        tenant_id,
        event_type="portal_view",
        ip=ip,
        user_agent=request.headers.get("User-Agent", ""),
    )

    return {**_serialize(config), "compliance_badges": badges}


@app.get("/portal/{slug}/documents")
async def list_portal_documents(
    slug: str,
    request: Request,
    nda_email: Optional[str] = Query(default=None),
    pool: asyncpg.Pool = Depends(get_db),
):
    """List visible portal documents.  NDA-gated docs hidden unless nda_email verified."""
    config = await _portal_config_mgr.get_by_slug(pool, slug)
    if config is None:
        raise HTTPException(status_code=404, detail="Portal not found")

    tenant_id = str(config["tenant_id"])
    nda_verified = False

    if nda_email and config.get("require_nda"):
        nda_verified = await _nda_manager.has_valid_nda(
            pool, tenant_id, nda_email, config["nda_version"]
        )
    elif not config.get("require_nda"):
        nda_verified = True

    docs = await _doc_gateway.get_visible_documents(pool, tenant_id, nda_verified)
    return {"documents": [_serialize(d) for d in docs], "nda_verified": nda_verified}


@app.post("/portal/{slug}/nda")
async def sign_nda(
    slug: str,
    acceptance: NDAAcceptance,
    request: Request,
    pool: asyncpg.Pool = Depends(get_db),
):
    """Record an NDA acceptance."""
    config = await _portal_config_mgr.get_by_slug(pool, slug)
    if config is None:
        raise HTTPException(status_code=404, detail="Portal not found")

    tenant_id = str(config["tenant_id"])
    ip = get_client_ip(request)
    user_agent = request.headers.get("User-Agent", "")

    # Ensure the NDA version matches the portal's current version
    acceptance.nda_version = config["nda_version"]

    record = await _nda_manager.record_acceptance(
        pool, tenant_id, acceptance, ip, user_agent
    )

    await _access_logger.log(
        pool,
        tenant_id,
        event_type="nda_signed",
        ip=ip,
        user_agent=user_agent,
        visitor_email=acceptance.signatory_email,
        visitor_company=acceptance.signatory_company,
    )

    return _serialize(record)


@app.get("/portal/{slug}/documents/{doc_id}/download")
async def download_document(
    slug: str,
    doc_id: str,
    request: Request,
    nda_email: Optional[str] = Query(default=None),
    pool: asyncpg.Pool = Depends(get_db),
):
    """Return a presigned download URL, enforcing NDA gate when required."""
    config = await _portal_config_mgr.get_by_slug(pool, slug)
    if config is None:
        raise HTTPException(status_code=404, detail="Portal not found")

    tenant_id = str(config["tenant_id"])

    # NDA check
    if config.get("require_nda"):
        if not nda_email:
            raise HTTPException(
                status_code=403,
                detail="NDA acceptance required — provide ?nda_email=",
            )
        verified = await _nda_manager.has_valid_nda(
            pool, tenant_id, nda_email, config["nda_version"]
        )
        if not verified:
            raise HTTPException(
                status_code=403,
                detail="Valid NDA not found for this email address",
            )

    try:
        url = await _doc_gateway.generate_presigned_url(
            pool, tenant_id, doc_id, nda_email or "anonymous"
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    return {"download_url": url}


@app.post("/portal/{slug}/chat/session")
async def create_chat_session(
    slug: str,
    request: Request,
    visitor_email: Optional[str] = None,
    visitor_company: Optional[str] = None,
    pool: asyncpg.Pool = Depends(get_db),
):
    """Create a new chatbot session."""
    config = await _portal_config_mgr.get_by_slug(pool, slug)
    if config is None:
        raise HTTPException(status_code=404, detail="Portal not found")

    if not config.get("chatbot_enabled"):
        raise HTTPException(status_code=403, detail="Chatbot is not enabled for this portal")

    tenant_id = str(config["tenant_id"])
    session = await _chatbot.create_session(
        pool, tenant_id, visitor_email, visitor_company
    )
    return _serialize(session)


@app.post("/portal/{slug}/chat/{token}")
async def send_chat_message(
    slug: str,
    token: str,
    message: dict,
    request: Request,
    pool: asyncpg.Pool = Depends(get_db),
):
    """Send a message to the portal chatbot."""
    config = await _portal_config_mgr.get_by_slug(pool, slug)
    if config is None:
        raise HTTPException(status_code=404, detail="Portal not found")

    if not config.get("chatbot_enabled"):
        raise HTTPException(status_code=403, detail="Chatbot is not enabled for this portal")

    tenant_id = str(config["tenant_id"])
    user_message = (message.get("content") or message.get("message") or "").strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="Message content is required")

    ip = get_client_ip(request)

    try:
        response = await _chatbot.send_message(
            pool, tenant_id, token, user_message, ip
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return response


@app.post("/portal/{slug}/deflect")
async def submit_deflection(
    slug: str,
    deflection_req: DeflectionRequest,
    request: Request,
    pool: asyncpg.Pool = Depends(get_db),
):
    """Submit a vendor questionnaire for AI-assisted deflection."""
    config = await _portal_config_mgr.get_by_slug(pool, slug)
    if config is None:
        raise HTTPException(status_code=404, detail="Portal not found")

    tenant_id = str(config["tenant_id"])
    ip = get_client_ip(request)

    result = await _deflector.deflect(pool, tenant_id, deflection_req)

    await _access_logger.log(
        pool,
        tenant_id,
        event_type="deflection_submitted",
        ip=ip,
        user_agent=request.headers.get("User-Agent", ""),
        visitor_email=deflection_req.requester_email,
        visitor_company=deflection_req.requester_company,
    )

    return _serialize(result)


@app.get("/portal/{slug}/deflect/{deflection_id}")
async def get_deflection_result(
    slug: str,
    deflection_id: str,
    pool: asyncpg.Pool = Depends(get_db),
):
    """Retrieve a previously submitted deflection result."""
    config = await _portal_config_mgr.get_by_slug(pool, slug)
    if config is None:
        raise HTTPException(status_code=404, detail="Portal not found")

    tenant_id = str(config["tenant_id"])
    record = await _deflector.get_deflection(pool, tenant_id, deflection_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Deflection record not found")

    return _serialize(record)


# ---------------------------------------------------------------------------
# ADMIN ROUTES
# ---------------------------------------------------------------------------

@app.get("/admin/portal/config")
async def admin_get_config(
    tenant_id: str = Depends(get_tenant_id),
    pool: asyncpg.Pool = Depends(get_db),
):
    config = await _portal_config_mgr.get_by_tenant(pool, tenant_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Portal config not found")
    return _serialize(config)


@app.post("/admin/portal/config")
async def admin_upsert_config(
    data: dict,
    tenant_id: str = Depends(get_tenant_id),
    pool: asyncpg.Pool = Depends(get_db),
):
    config = await _portal_config_mgr.upsert(pool, tenant_id, {**data, "tenant_id": tenant_id})
    return _serialize(config)


@app.get("/admin/portal/documents")
async def admin_list_documents(
    tenant_id: str = Depends(get_tenant_id),
    pool: asyncpg.Pool = Depends(get_db),
):
    docs = await _doc_gateway.list_all_documents(pool, tenant_id)
    return {"documents": [_serialize(d) for d in docs]}


@app.post("/admin/portal/documents")
async def admin_upload_document(
    display_name: str = Form(...),
    doc_type: str = Form(...),
    requires_nda: bool = Form(False),
    description: Optional[str] = Form(default=None),
    file: UploadFile = File(...),
    tenant_id: str = Depends(get_tenant_id),
    pool: asyncpg.Pool = Depends(get_db),
):
    file_bytes = await file.read()
    try:
        doc = await _doc_gateway.upload_document(
            pool,
            tenant_id,
            display_name=display_name,
            doc_type=doc_type,
            file_bytes=file_bytes,
            requires_nda=requires_nda,
            filename=file.filename or "document",
            description=description,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return _serialize(doc)


@app.delete("/admin/portal/documents/{doc_id}")
async def admin_delete_document(
    doc_id: str,
    tenant_id: str = Depends(get_tenant_id),
    pool: asyncpg.Pool = Depends(get_db),
):
    deleted = await _doc_gateway.soft_delete(pool, tenant_id, doc_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"status": "ok", "document_id": doc_id}


@app.get("/admin/portal/access-logs")
async def admin_access_logs(
    limit: int = Query(default=100, le=500),
    event_type: Optional[str] = Query(default=None),
    tenant_id: str = Depends(get_tenant_id),
    pool: asyncpg.Pool = Depends(get_db),
):
    events = await _access_logger.get_recent_events(
        pool, tenant_id, limit=limit, event_type=event_type
    )
    return {"events": [_serialize(e) for e in events]}


@app.get("/admin/portal/access-logs/stats")
async def admin_access_log_stats(
    tenant_id: str = Depends(get_tenant_id),
    pool: asyncpg.Pool = Depends(get_db),
):
    return await _access_logger.get_stats(pool, tenant_id)


@app.get("/admin/portal/ndas")
async def admin_list_ndas(
    limit: int = Query(default=200, le=1000),
    tenant_id: str = Depends(get_tenant_id),
    pool: asyncpg.Pool = Depends(get_db),
):
    records = await _nda_manager.list_acceptances(pool, tenant_id, limit=limit)
    return {"ndas": [_serialize(r) for r in records]}


@app.get("/admin/portal/ndas/stats")
async def admin_nda_stats(
    tenant_id: str = Depends(get_tenant_id),
    pool: asyncpg.Pool = Depends(get_db),
):
    return await _nda_manager.get_nda_stats(pool, tenant_id)


@app.get("/admin/portal/deflections")
async def admin_list_deflections(
    limit: int = Query(default=50, le=200),
    tenant_id: str = Depends(get_tenant_id),
    pool: asyncpg.Pool = Depends(get_db),
):
    records = await _deflector.list_deflections(pool, tenant_id, limit=limit)
    return {"deflections": [_serialize(r) for r in records]}


# ---------------------------------------------------------------------------
# Serialisation helper
# ---------------------------------------------------------------------------

def _serialize(obj: dict) -> dict:
    """Convert asyncpg Record values (UUID, date, datetime) to JSON-safe types."""
    import datetime
    import json

    result: dict = {}
    for k, v in obj.items():
        if isinstance(v, (UUID,)):
            result[k] = str(v)
        elif isinstance(v, (datetime.datetime, datetime.date)):
            result[k] = v.isoformat()
        elif isinstance(v, memoryview):
            result[k] = bytes(v).decode("utf-8", errors="replace")
        else:
            result[k] = v
    return result
