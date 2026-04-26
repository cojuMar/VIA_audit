from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Annotated

import asyncpg
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile, status

from .config import settings
from .db import close_pool, create_pool
from .engagement_manager import EngagementManager
from .export_engine import ExportEngine
from .issue_tracker import IssueTracker
from .models import (
    EngagementCreate,
    IssueCreate,
    IssueResponseCreate,
    PBCFulfillmentCreate,
    PBCListCreate,
    PBCRequestCreate,
    SectionUpdate,
    WorkpaperCreate,
)
from .pbc_manager import PBCManager
from .workpaper_manager import WorkpaperManager


# ---------------------------------------------------------------------------
# App state
# ---------------------------------------------------------------------------


class AppState:
    pool: asyncpg.Pool | None = None


state = AppState()


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    state.pool = await create_pool()

    # Ensure MinIO bucket exists
    try:
        from minio import Minio

        client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=False,
        )
        if not client.bucket_exists(settings.minio_bucket_workpapers):
            client.make_bucket(settings.minio_bucket_workpapers)
    except Exception:
        pass  # Graceful — service still starts without MinIO

    yield

    # Shutdown
    if state.pool:
        await close_pool(state.pool)


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="PBC Service",
    version="1.0.0",
    description="Project Aegis 2026 Sprint 13 — PBC Request Management, Issue Lifecycle & Workpapers",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Managers (singletons)
# ---------------------------------------------------------------------------

_eng_mgr = EngagementManager()
_pbc_mgr = PBCManager()
_issue_tracker = IssueTracker()
_wp_mgr = WorkpaperManager()
_export_engine = ExportEngine()


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


def get_db() -> asyncpg.Pool:
    if state.pool is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database pool not initialized",
        )
    return state.pool


def get_tenant_id(request: Request) -> str:
    tenant_id = request.headers.get("X-Tenant-ID")
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Tenant-ID header is required",
        )
    return tenant_id


def get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/health", tags=["ops"])
async def health():
    return {"status": "ok", "service": "pbc-service"}


# ---------------------------------------------------------------------------
# Engagements
# ---------------------------------------------------------------------------


@app.get("/engagements", tags=["engagements"])
async def list_engagements(
    pool: Annotated[asyncpg.Pool, Depends(get_db)],
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    status: str | None = Query(default=None),
) -> list[dict]:
    return await _eng_mgr.list(pool, tenant_id, status=status)


@app.post("/engagements", tags=["engagements"], status_code=201)
async def create_engagement(
    data: EngagementCreate,
    pool: Annotated[asyncpg.Pool, Depends(get_db)],
    tenant_id: Annotated[str, Depends(get_tenant_id)],
) -> dict:
    return await _eng_mgr.create(pool, tenant_id, data)


@app.get("/engagements/{engagement_id}", tags=["engagements"])
async def get_engagement(
    engagement_id: str,
    pool: Annotated[asyncpg.Pool, Depends(get_db)],
    tenant_id: Annotated[str, Depends(get_tenant_id)],
) -> dict:
    try:
        return await _eng_mgr.get_dashboard(pool, tenant_id, engagement_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.put("/engagements/{engagement_id}/status", tags=["engagements"])
async def update_engagement_status(
    engagement_id: str,
    body: dict,
    pool: Annotated[asyncpg.Pool, Depends(get_db)],
    tenant_id: Annotated[str, Depends(get_tenant_id)],
) -> dict:
    new_status = body.get("status")
    if not new_status:
        raise HTTPException(status_code=422, detail="'status' field is required")
    try:
        return await _eng_mgr.update_status(pool, tenant_id, engagement_id, new_status)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ---------------------------------------------------------------------------
# PBC — Lists
# ---------------------------------------------------------------------------


@app.get("/pbc/lists", tags=["pbc"])
async def list_pbc_lists(
    pool: Annotated[asyncpg.Pool, Depends(get_db)],
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    engagement_id: str | None = Query(default=None),
) -> list[dict]:
    return await _pbc_mgr.list_pbc_lists(pool, tenant_id, engagement_id=engagement_id)


@app.post("/pbc/lists", tags=["pbc"], status_code=201)
async def create_pbc_list(
    data: PBCListCreate,
    pool: Annotated[asyncpg.Pool, Depends(get_db)],
    tenant_id: Annotated[str, Depends(get_tenant_id)],
) -> dict:
    return await _pbc_mgr.create_list(pool, tenant_id, data)


@app.put("/pbc/lists/{list_id}", tags=["pbc"])
async def update_pbc_list(
    list_id: str,
    updates: dict,
    pool: Annotated[asyncpg.Pool, Depends(get_db)],
    tenant_id: Annotated[str, Depends(get_tenant_id)],
) -> dict:
    try:
        return await _pbc_mgr.update_list(pool, tenant_id, list_id, updates)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/pbc/lists/{list_id}", tags=["pbc"])
async def get_pbc_list(
    list_id: str,
    pool: Annotated[asyncpg.Pool, Depends(get_db)],
    tenant_id: Annotated[str, Depends(get_tenant_id)],
) -> dict:
    try:
        return await _pbc_mgr.get_list_with_requests(pool, tenant_id, list_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/pbc/lists/{list_id}/status", tags=["pbc"])
async def get_pbc_list_status(
    list_id: str,
    pool: Annotated[asyncpg.Pool, Depends(get_db)],
    tenant_id: Annotated[str, Depends(get_tenant_id)],
) -> dict:
    return await _pbc_mgr.get_list_status(pool, tenant_id, list_id)


# ---------------------------------------------------------------------------
# PBC — Requests
# ---------------------------------------------------------------------------


@app.post("/pbc/lists/{list_id}/requests", tags=["pbc"], status_code=201)
async def add_pbc_request(
    list_id: str,
    data: PBCRequestCreate,
    pool: Annotated[asyncpg.Pool, Depends(get_db)],
    tenant_id: Annotated[str, Depends(get_tenant_id)],
) -> dict:
    # Ensure list_id in path and body are consistent
    data = data.model_copy(update={"list_id": list_id})
    return await _pbc_mgr.add_request(pool, tenant_id, data)


@app.post("/pbc/lists/{list_id}/requests/bulk", tags=["pbc"], status_code=201)
async def bulk_add_pbc_requests(
    list_id: str,
    requests: list[PBCRequestCreate],
    pool: Annotated[asyncpg.Pool, Depends(get_db)],
    tenant_id: Annotated[str, Depends(get_tenant_id)],
) -> dict:
    return await _pbc_mgr.bulk_add_requests(pool, tenant_id, list_id, requests)


@app.post("/pbc/requests/{request_id}/fulfill", tags=["pbc"], status_code=201)
async def fulfill_pbc_request(
    request_id: str,
    pool: Annotated[asyncpg.Pool, Depends(get_db)],
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    data: str = Form(...),
    file: UploadFile | None = File(default=None),
) -> dict:
    try:
        parsed = json.loads(data)
        ful_data = PBCFulfillmentCreate(**parsed)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid fulfillment data: {e}")

    file_bytes: bytes | None = None
    file_name: str | None = None
    if file and file.filename:
        file_bytes = await file.read()
        file_name = file.filename

    try:
        return await _pbc_mgr.fulfill_request(
            pool, tenant_id, request_id, ful_data, file_bytes, file_name
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/pbc/requests/{request_id}/na", tags=["pbc"])
async def mark_pbc_not_applicable(
    request_id: str,
    body: dict,
    pool: Annotated[asyncpg.Pool, Depends(get_db)],
    tenant_id: Annotated[str, Depends(get_tenant_id)],
) -> dict:
    reason = body.get("reason", "")
    try:
        return await _pbc_mgr.mark_not_applicable(pool, tenant_id, request_id, reason)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/pbc/requests/{request_id}/history", tags=["pbc"])
async def get_fulfillment_history(
    request_id: str,
    pool: Annotated[asyncpg.Pool, Depends(get_db)],
    tenant_id: Annotated[str, Depends(get_tenant_id)],
) -> list[dict]:
    return await _pbc_mgr.get_fulfillment_history(pool, tenant_id, request_id)


@app.get("/pbc/overdue", tags=["pbc"])
async def get_overdue_requests(
    pool: Annotated[asyncpg.Pool, Depends(get_db)],
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    engagement_id: str | None = Query(default=None),
) -> list[dict]:
    return await _pbc_mgr.get_overdue_requests(pool, tenant_id, engagement_id=engagement_id)


# ---------------------------------------------------------------------------
# Issues
# ---------------------------------------------------------------------------


@app.get("/issues", tags=["issues"])
async def list_issues(
    pool: Annotated[asyncpg.Pool, Depends(get_db)],
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    engagement_id: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    status: str | None = Query(default=None),
) -> list[dict]:
    return await _issue_tracker.list_issues(
        pool, tenant_id, engagement_id=engagement_id, severity=severity, status=status
    )


@app.post("/issues", tags=["issues"], status_code=201)
async def create_issue(
    data: IssueCreate,
    pool: Annotated[asyncpg.Pool, Depends(get_db)],
    tenant_id: Annotated[str, Depends(get_tenant_id)],
) -> dict:
    return await _issue_tracker.create_issue(pool, tenant_id, data)


@app.patch("/issues/{issue_id}/status", tags=["issues"])
async def update_issue_status(
    issue_id: str,
    body: dict,
    pool: Annotated[asyncpg.Pool, Depends(get_db)],
    tenant_id: Annotated[str, Depends(get_tenant_id)],
) -> dict:
    """Direct status update for Kanban drag-and-drop. Writes an immutable audit-trail response."""
    new_status = body.get("status")
    changed_by = body.get("changed_by", "kanban_board")
    if not new_status:
        raise HTTPException(status_code=422, detail="'status' field is required")
    try:
        return await _issue_tracker.update_status(pool, tenant_id, issue_id, new_status, changed_by)
    except ValueError as e:
        raise HTTPException(status_code=404 if "not found" in str(e) else 422, detail=str(e))


@app.get("/issues/metrics/{engagement_id}", tags=["issues"])
async def get_issue_metrics(
    engagement_id: str,
    pool: Annotated[asyncpg.Pool, Depends(get_db)],
    tenant_id: Annotated[str, Depends(get_tenant_id)],
) -> dict:
    return await _issue_tracker.get_issue_metrics(pool, tenant_id, engagement_id)


@app.get("/issues/{issue_id}", tags=["issues"])
async def get_issue(
    issue_id: str,
    pool: Annotated[asyncpg.Pool, Depends(get_db)],
    tenant_id: Annotated[str, Depends(get_tenant_id)],
) -> dict:
    result = await _issue_tracker.get_issue(pool, tenant_id, issue_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Issue {issue_id} not found")
    return result


@app.post("/issues/{issue_id}/respond", tags=["issues"], status_code=201)
async def add_issue_response(
    issue_id: str,
    pool: Annotated[asyncpg.Pool, Depends(get_db)],
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    data: str = Form(...),
    file: UploadFile | None = File(default=None),
) -> dict:
    try:
        parsed = json.loads(data)
        resp_data = IssueResponseCreate(**parsed)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid response data: {e}")

    # Ensure issue_id in path is used
    resp_data = resp_data.model_copy(update={"issue_id": issue_id})

    file_bytes: bytes | None = None
    file_name: str | None = None
    if file and file.filename:
        file_bytes = await file.read()
        file_name = file.filename

    return await _issue_tracker.add_response(
        pool, tenant_id, resp_data, file_bytes, file_name
    )


# ---------------------------------------------------------------------------
# Workpapers
# ---------------------------------------------------------------------------


@app.get("/workpapers/templates", tags=["workpapers"])
async def list_workpaper_templates(
    pool: Annotated[asyncpg.Pool, Depends(get_db)],
) -> list[dict]:
    return await _wp_mgr.list_templates(pool)


@app.get("/workpapers", tags=["workpapers"])
async def list_workpapers(
    pool: Annotated[asyncpg.Pool, Depends(get_db)],
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    engagement_id: str = Query(...),
) -> list[dict]:
    return await _wp_mgr.list_workpapers(pool, tenant_id, engagement_id)


@app.post("/workpapers", tags=["workpapers"], status_code=201)
async def create_workpaper(
    data: WorkpaperCreate,
    pool: Annotated[asyncpg.Pool, Depends(get_db)],
    tenant_id: Annotated[str, Depends(get_tenant_id)],
) -> dict:
    if data.template_id:
        return await _wp_mgr.create_from_template(pool, tenant_id, data)
    return await _wp_mgr.create_blank(pool, tenant_id, data)


@app.get("/workpapers/{wp_id}", tags=["workpapers"])
async def get_workpaper(
    wp_id: str,
    pool: Annotated[asyncpg.Pool, Depends(get_db)],
    tenant_id: Annotated[str, Depends(get_tenant_id)],
) -> dict:
    result = await _wp_mgr.get_workpaper(pool, tenant_id, wp_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Workpaper {wp_id} not found")
    return result


@app.get("/workpapers/{wp_id}/status", tags=["workpapers"])
async def get_workpaper_status(
    wp_id: str,
    pool: Annotated[asyncpg.Pool, Depends(get_db)],
    tenant_id: Annotated[str, Depends(get_tenant_id)],
) -> dict:
    return await _wp_mgr.get_completion_status(pool, tenant_id, wp_id)


@app.put("/workpapers/{wp_id}/sections/{sec_id}", tags=["workpapers"])
async def update_workpaper_section(
    wp_id: str,
    sec_id: str,
    data: SectionUpdate,
    pool: Annotated[asyncpg.Pool, Depends(get_db)],
    tenant_id: Annotated[str, Depends(get_tenant_id)],
) -> dict:
    try:
        return await _wp_mgr.update_section(pool, tenant_id, sec_id, data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/workpapers/{wp_id}/sections", tags=["workpapers"], status_code=201)
async def add_workpaper_section(
    wp_id: str,
    body: dict,
    pool: Annotated[asyncpg.Pool, Depends(get_db)],
    tenant_id: Annotated[str, Depends(get_tenant_id)],
) -> dict:
    section_key = body.get("section_key", "")
    title = body.get("title", "")
    sort_order = body.get("sort_order", 0)
    return await _wp_mgr.add_section(pool, tenant_id, wp_id, section_key, title, sort_order)


@app.post("/workpapers/{wp_id}/submit-review", tags=["workpapers"])
async def submit_workpaper_for_review(
    wp_id: str,
    pool: Annotated[asyncpg.Pool, Depends(get_db)],
    tenant_id: Annotated[str, Depends(get_tenant_id)],
) -> dict:
    try:
        return await _wp_mgr.submit_for_review(pool, tenant_id, wp_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/workpapers/{wp_id}/finalize", tags=["workpapers"])
async def finalize_workpaper(
    wp_id: str,
    body: dict,
    pool: Annotated[asyncpg.Pool, Depends(get_db)],
    tenant_id: Annotated[str, Depends(get_tenant_id)],
) -> dict:
    reviewer = body.get("reviewer", "")
    review_notes = body.get("review_notes")
    try:
        return await _wp_mgr.finalize(pool, tenant_id, wp_id, reviewer, review_notes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


@app.get("/export/pbc/{list_id}", tags=["export"])
async def export_pbc_list(
    list_id: str,
    pool: Annotated[asyncpg.Pool, Depends(get_db)],
    tenant_id: Annotated[str, Depends(get_tenant_id)],
) -> dict:
    try:
        return await _export_engine.export_pbc_list(pool, tenant_id, list_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/export/issues/{engagement_id}", tags=["export"])
async def export_issue_register(
    engagement_id: str,
    pool: Annotated[asyncpg.Pool, Depends(get_db)],
    tenant_id: Annotated[str, Depends(get_tenant_id)],
) -> dict:
    try:
        return await _export_engine.export_issue_register(pool, tenant_id, engagement_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/export/workpaper/{wp_id}", tags=["export"])
async def export_workpaper(
    wp_id: str,
    pool: Annotated[asyncpg.Pool, Depends(get_db)],
    tenant_id: Annotated[str, Depends(get_tenant_id)],
) -> dict:
    try:
        return await _export_engine.export_workpaper(pool, tenant_id, wp_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/export/ai-summary/{engagement_id}", tags=["export"])
async def generate_ai_summary(
    engagement_id: str,
    pool: Annotated[asyncpg.Pool, Depends(get_db)],
    tenant_id: Annotated[str, Depends(get_tenant_id)],
) -> dict:
    summary = await _export_engine.generate_ai_finding_summary(
        pool, tenant_id, engagement_id
    )
    return {"engagement_id": engagement_id, "summary": summary}
