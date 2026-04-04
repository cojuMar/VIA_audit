from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, UploadFile, File, Form
from minio import Minio

from .ai_field_advisor import AIFieldAdvisor
from .config import settings
from .db import get_pool, init_pool, tenant_conn
from .field_audit_manager import FieldAuditManager
from .models import (
    AssignmentCreate,
    FieldAuditCreate,
    ResponsePayload,
    SyncBatchPayload,
)
from .photo_manager import PhotoManager
from .sync_engine import SyncEngine
from .template_manager import TemplateManager

# ---------------------------------------------------------------------------
# MinIO client (module-level, initialised in lifespan)
# ---------------------------------------------------------------------------
_minio_client: Minio | None = None


def get_minio() -> Minio:
    if _minio_client is None:
        raise RuntimeError("MinIO client has not been initialised")
    return _minio_client


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _minio_client

    pool = await init_pool(settings.database_url)

    endpoint = settings.minio_endpoint.removeprefix("http://").removeprefix("https://")
    secure = settings.minio_endpoint.startswith("https://")
    _minio_client = Minio(
        endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=secure,
    )

    # Ensure the evidence bucket exists
    photo_mgr = PhotoManager(pool, _minio_client)
    await photo_mgr.ensure_bucket()

    yield

    await pool.close()


app = FastAPI(
    title="Mobile Sync Service",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tenant(x_tenant_id: str | None) -> str:
    if not x_tenant_id:
        raise HTTPException(status_code=400, detail="X-Tenant-ID header is required")
    return x_tenant_id


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "mobile-sync-service"}


# ---------------------------------------------------------------------------
# Template routes (no tenant required — platform data)
# ---------------------------------------------------------------------------


@app.get("/templates/types")
async def list_template_types(
    x_tenant_id: str | None = Header(default=None),
) -> list[dict]:
    mgr = TemplateManager(get_pool())
    return await mgr.get_template_types()


@app.get("/templates")
async def list_templates(
    type_id: str | None = Query(default=None),
    active_only: bool = Query(default=True),
    x_tenant_id: str | None = Header(default=None),
) -> list[dict]:
    mgr = TemplateManager(get_pool())
    return await mgr.get_templates(type_id=type_id, active_only=active_only)


@app.get("/templates/{template_id}")
async def get_template(
    template_id: str,
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    mgr = TemplateManager(get_pool())
    result = await mgr.get_template_with_questions(template_id)
    if not result:
        raise HTTPException(status_code=404, detail="Template not found")
    return result


# ---------------------------------------------------------------------------
# Assignment routes
# ---------------------------------------------------------------------------


@app.post("/assignments", status_code=201)
async def create_assignment(
    data: AssignmentCreate,
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    mgr = TemplateManager(get_pool())
    return await mgr.create_assignment(tenant_id, data)


@app.get("/assignments")
async def list_assignments(
    email: str | None = Query(default=None),
    status: str | None = Query(default=None),
    x_tenant_id: str | None = Header(default=None),
) -> list[dict]:
    tenant_id = _tenant(x_tenant_id)
    mgr = TemplateManager(get_pool())
    return await mgr.get_assignments(tenant_id, email=email, status=status)


@app.put("/assignments/{assignment_id}/status")
async def update_assignment_status(
    assignment_id: str,
    body: dict[str, Any],
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    status = body.get("status")
    if not status:
        raise HTTPException(status_code=400, detail="status is required")
    mgr = TemplateManager(get_pool())
    try:
        return await mgr.update_assignment_status(tenant_id, assignment_id, status)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ---------------------------------------------------------------------------
# Field audit routes — static paths declared before parameterised ones
# ---------------------------------------------------------------------------


@app.post("/audits", status_code=201)
async def create_audit(
    data: FieldAuditCreate,
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    mgr = FieldAuditManager(get_pool())
    return await mgr.create_audit(tenant_id, data)


@app.get("/audits")
async def list_audits(
    email: str | None = Query(default=None),
    status: str | None = Query(default=None),
    assignment_id: str | None = Query(default=None),
    x_tenant_id: str | None = Header(default=None),
) -> list[dict]:
    tenant_id = _tenant(x_tenant_id)
    mgr = FieldAuditManager(get_pool())
    return await mgr.list_audits(
        tenant_id, email=email, status=status, assignment_id=assignment_id
    )


@app.get("/audits/{audit_id}/summary")
async def get_audit_summary(
    audit_id: str,
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    mgr = FieldAuditManager(get_pool())
    try:
        return await mgr.get_audit_summary(tenant_id, audit_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/audits/{audit_id}/submit")
async def submit_audit(
    audit_id: str,
    body: dict[str, Any],
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    auditor_signature = body.get("auditor_signature")
    mgr = FieldAuditManager(get_pool())
    try:
        return await mgr.submit_audit(
            tenant_id, audit_id, auditor_signature=auditor_signature
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/audits/{audit_id}")
async def get_audit(
    audit_id: str,
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    mgr = FieldAuditManager(get_pool())
    result = await mgr.get_audit(tenant_id, audit_id)
    if not result:
        raise HTTPException(status_code=404, detail="Audit not found")
    return result


# ---------------------------------------------------------------------------
# Response routes (immutable) — static /batch path before the bare POST
# ---------------------------------------------------------------------------


@app.post("/audits/{audit_id}/responses/batch", status_code=201)
async def add_responses_batch(
    audit_id: str,
    responses: list[ResponsePayload],
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    mgr = FieldAuditManager(get_pool())
    return await mgr.add_responses_batch(tenant_id, audit_id, responses)


@app.post("/audits/{audit_id}/responses", status_code=201)
async def add_response(
    audit_id: str,
    data: ResponsePayload,
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    mgr = FieldAuditManager(get_pool())
    return await mgr.add_response(tenant_id, audit_id, data)


# ---------------------------------------------------------------------------
# Photo routes — static /upload-url path before bare GET/POST
# ---------------------------------------------------------------------------


@app.post("/audits/{audit_id}/photos/upload-url")
async def get_photo_upload_url(
    audit_id: str,
    body: dict[str, Any],
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    filename = body.get("filename")
    if not filename:
        raise HTTPException(status_code=400, detail="filename is required")
    mgr = PhotoManager(get_pool(), get_minio())
    return await mgr.get_photo_upload_url(tenant_id, audit_id, filename)


@app.post("/audits/{audit_id}/photos", status_code=201)
async def upload_photo(
    audit_id: str,
    file: UploadFile = File(...),
    caption: str | None = Form(default=None),
    response_id: str | None = Form(default=None),
    gps_latitude: float | None = Form(default=None),
    gps_longitude: float | None = Form(default=None),
    taken_at: str | None = Form(default=None),
    sync_id: str | None = Form(default=None),
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    file_bytes = await file.read()
    mime_type = file.content_type or "application/octet-stream"
    mgr = PhotoManager(get_pool(), get_minio())
    return await mgr.upload_photo(
        tenant_id=tenant_id,
        audit_id=audit_id,
        file_bytes=file_bytes,
        filename=file.filename or "photo.jpg",
        mime_type=mime_type,
        response_id=response_id,
        caption=caption,
        gps_lat=gps_latitude,
        gps_lon=gps_longitude,
        taken_at=taken_at,
        sync_id=sync_id,
    )


@app.get("/audits/{audit_id}/photos")
async def list_photos(
    audit_id: str,
    x_tenant_id: str | None = Header(default=None),
) -> list[dict]:
    tenant_id = _tenant(x_tenant_id)
    mgr = PhotoManager(get_pool(), get_minio())
    return await mgr.get_photos_for_audit(tenant_id, audit_id)


# ---------------------------------------------------------------------------
# Sync routes — static paths before parameterised
# ---------------------------------------------------------------------------


@app.post("/sync/upload")
async def sync_upload(
    data: SyncBatchPayload,
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    engine = SyncEngine(get_pool(), get_minio())
    return await engine.process_sync_batch(tenant_id, data)


@app.get("/sync/download")
async def sync_download(
    email: str = Query(...),
    last_sync: str | None = Query(default=None),
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    engine = SyncEngine(get_pool(), get_minio())
    return await engine.get_assignments_for_device(
        tenant_id, email, last_sync=last_sync
    )


@app.get("/sync/history")
async def sync_history(
    device_id: str | None = Query(default=None),
    email: str | None = Query(default=None),
    x_tenant_id: str | None = Header(default=None),
) -> list[dict]:
    tenant_id = _tenant(x_tenant_id)
    engine = SyncEngine(get_pool(), get_minio())
    return await engine.get_sync_history(tenant_id, device_id=device_id, email=email)


# ---------------------------------------------------------------------------
# AI routes — static paths, POST-only except checklist-hints
# ---------------------------------------------------------------------------


@app.post("/ai/findings-report")
async def ai_findings_report(
    body: dict[str, Any],
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    audit_id = body.get("audit_id")
    if not audit_id:
        raise HTTPException(status_code=400, detail="audit_id is required")

    audit_mgr = FieldAuditManager(get_pool())
    try:
        audit_summary = await audit_mgr.get_audit_summary(tenant_id, audit_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    advisor = AIFieldAdvisor(settings.anthropic_api_key)
    report = await advisor.generate_audit_findings_report(audit_summary)
    return {"audit_id": audit_id, "report": report}


@app.post("/ai/prioritize-findings")
async def ai_prioritize_findings(
    body: dict[str, Any],
    x_tenant_id: str | None = Header(default=None),
) -> list[dict]:
    tenant_id = _tenant(x_tenant_id)
    audit_id = body.get("audit_id")
    if not audit_id:
        raise HTTPException(status_code=400, detail="audit_id is required")

    pool = get_pool()
    async with tenant_conn(pool, tenant_id) as conn:
        finding_rows = await conn.fetch(
            """
            SELECT * FROM field_audit_responses
            WHERE field_audit_id = $1 AND is_finding = TRUE
            """,
            audit_id,
        )

    findings = [dict(r) for r in finding_rows]
    advisor = AIFieldAdvisor(settings.anthropic_api_key)
    return await advisor.prioritize_findings(findings)


@app.get("/ai/checklist-hints/{template_id}")
async def ai_checklist_hints(
    template_id: str,
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    mgr = TemplateManager(get_pool())
    template = await mgr.get_template_with_questions(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    advisor = AIFieldAdvisor(settings.anthropic_api_key)
    hints = await advisor.generate_offline_checklist_hints(template)
    return {"template_id": template_id, "hints": hints}
