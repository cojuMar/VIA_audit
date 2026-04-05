"""
TPRM Service — FastAPI application

Routes:
  GET  /health

  # Vendor CRUD
  GET  /vendors                              → list all vendors (X-Tenant-ID, filters: risk_tier, status, search)
  POST /vendors                              → create vendor (runs intake rubric, returns risk score)
  GET  /vendors/{vendor_id}                  → get vendor detail
  PATCH /vendors/{vendor_id}                 → update vendor fields
  GET  /vendors/{vendor_id}/risk-score       → latest risk score snapshot
  GET  /vendors/expiring-reviews             → vendors whose next_review_at is within 30 days

  # Questionnaires
  GET  /questionnaires/templates             → list available templates
  GET  /questionnaires/templates/{slug}      → get template detail with questions
  POST /vendors/{vendor_id}/questionnaires   → send questionnaire
  GET  /vendors/{vendor_id}/questionnaires   → list questionnaires for vendor
  POST /questionnaires/{q_id}/responses      → submit responses + trigger AI scoring
  GET  /questionnaires/{q_id}               → get questionnaire with responses and AI score

  # Documents
  POST /vendors/{vendor_id}/documents        → upload document (multipart/form-data)
  GET  /vendors/{vendor_id}/documents        → list documents
  POST /documents/{doc_id}/analyze           → trigger AI analysis
  GET  /documents/{doc_id}/analysis          → get analysis results

  # Monitoring
  GET  /vendors/{vendor_id}/monitoring-events → recent monitoring events
  POST /vendors/{vendor_id}/monitoring/run    → trigger immediate monitoring cycle
  GET  /monitoring/alerts                    → all critical/high events (last 7 days)

  # Contracts
  GET  /vendors/{vendor_id}/contracts        → list contracts for vendor
  POST /vendors/{vendor_id}/contracts        → add contract
  GET  /contracts/expiring                   → contracts expiring within 90 days

  # Fourth-party
  GET  /fourth-party/graph                   → full vendor→sub-processor graph
  POST /vendors/{vendor_id}/fourth-party     → add fourth-party relationship
  POST /vendors/{vendor_id}/fourth-party/sync → sync from vendor.sub_processors field
"""

import logging
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any
from uuid import UUID

import asyncpg
import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, HTTPException, Depends, Header, Query, UploadFile, File, Form
from pydantic import BaseModel

from .config import settings
from .contract_tracker import ContractTracker
from .db import get_pool, close_pool
from .fourth_party import FourthPartyAnalyzer
from .questionnaire_engine import QuestionnaireEngine
from .vendor_doc_analyzer import VendorDocAnalyzer
from .vendor_intake import VendorIntake
from .vendor_monitor import VendorMonitor

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

_scheduler: Optional[AsyncIOScheduler] = None
_monitor: Optional[VendorMonitor] = None


async def _run_monitoring_all_tenants():
    """APScheduler job: run monitoring cycle for all tenants with active vendors."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            tenant_rows = await conn.fetch("""
                SELECT DISTINCT tenant_id FROM vendors WHERE status = 'active'
            """)
        monitor = VendorMonitor(pool, settings.securityscorecard_api_key)
        for row in tenant_rows:
            try:
                count = await monitor.run_monitoring_cycle(row['tenant_id'])
                if count:
                    logger.info(f"Monitoring cycle: tenant={row['tenant_id']} events={count}")
            except Exception as e:
                logger.error(f"Monitoring cycle failed for tenant {row['tenant_id']}: {e}")
        await monitor.close()
    except Exception as e:
        logger.error(f"Monitoring scheduler job error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler

    pool = await get_pool()
    logger.info("DB pool ready")

    # Ensure MinIO bucket exists (graceful degradation)
    try:
        from minio import Minio
        endpoint = settings.minio_endpoint.replace('http://', '').replace('https://', '')
        secure = settings.minio_endpoint.startswith('https://')
        minio_client = Minio(
            endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=secure
        )
        if not minio_client.bucket_exists(settings.minio_vendor_docs_bucket):
            minio_client.make_bucket(settings.minio_vendor_docs_bucket)
            logger.info(f"MinIO bucket created: {settings.minio_vendor_docs_bucket}")
        else:
            logger.info(f"MinIO bucket exists: {settings.minio_vendor_docs_bucket}")
    except Exception as e:
        logger.warning(f"MinIO bucket setup failed (dev mode): {e}")

    # Start background monitoring scheduler
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        _run_monitoring_all_tenants,
        'interval',
        hours=settings.monitoring_interval_hours,
        id='vendor_monitoring',
        replace_existing=True,
    )
    _scheduler.start()
    logger.info(f"APScheduler started — monitoring every {settings.monitoring_interval_hours}h")

    yield

    _scheduler.shutdown(wait=False)
    await close_pool()
    logger.info("TPRM service shut down")


app = FastAPI(title="Aegis TPRM Service", version="1.0.0", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

async def get_db() -> asyncpg.Pool:
    pool = await get_pool()
    if pool is None:
        raise HTTPException(503, "DB pool not ready")
    return pool


async def _get_tenant_id(x_tenant_id: str = Header(..., alias="X-Tenant-ID")) -> UUID:
    try:
        return UUID(x_tenant_id)
    except ValueError:
        raise HTTPException(400, "Invalid X-Tenant-ID header: must be a UUID")


# ---------------------------------------------------------------------------
# Pydantic request schemas
# ---------------------------------------------------------------------------

class VendorCreateRequest(BaseModel):
    name: str
    vendor_type: str
    website: Optional[str] = None
    description: Optional[str] = None
    primary_contact_name: Optional[str] = None
    primary_contact_email: Optional[str] = None
    data_types_processed: List[str] = []
    integrations_depth: str = "none"
    processes_pii: bool = False
    processes_phi: bool = False
    processes_pci: bool = False
    uses_ai: bool = False
    sub_processors: List[str] = []


class VendorPatchRequest(BaseModel):
    name: Optional[str] = None
    website: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    primary_contact_name: Optional[str] = None
    primary_contact_email: Optional[str] = None
    risk_tier: Optional[str] = None


class SendQuestionnaireRequest(BaseModel):
    template_slug: str
    due_days: int = 14


class SubmitResponsesRequest(BaseModel):
    responses: Dict[str, Any]


class ContractCreateRequest(BaseModel):
    contract_type: str
    title: str
    effective_date: Optional[str] = None
    expiry_date: Optional[str] = None
    auto_renews: bool = False
    renewal_notice_days: int = 90
    contract_value: Optional[float] = None
    currency: str = "USD"
    sla_commitments: Dict[str, Any] = {}
    notes: Optional[str] = None


class FourthPartyAddRequest(BaseModel):
    sub_processor_name: str
    risk_tier: str = "unrated"
    data_types: List[str] = []


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok", "service": "tprm-service"}


# ---------------------------------------------------------------------------
# Vendor CRUD
# ---------------------------------------------------------------------------

@app.get("/vendors")
async def list_vendors(
    risk_tier: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    tenant_id: UUID = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
):
    """List all vendors with optional filtering."""
    async with db.acquire() as conn:
        await conn.execute("SELECT set_config('app.tenant_id', $1, false)", str(tenant_id))

        conditions = ["tenant_id = $1"]
        params: List[Any] = [tenant_id]
        idx = 2

        if risk_tier:
            conditions.append(f"risk_tier = ${idx}")
            params.append(risk_tier)
            idx += 1
        if status:
            conditions.append(f"status = ${idx}")
            params.append(status)
            idx += 1
        if search:
            conditions.append(f"(name ILIKE ${idx} OR description ILIKE ${idx})")
            params.append(f"%{search}%")
            idx += 1

        where_clause = " AND ".join(conditions)
        rows = await conn.fetch(f"""
            SELECT id, name, vendor_type, status, risk_tier, inherent_risk_score,
                   primary_contact_name, primary_contact_email, website,
                   processes_pii, processes_phi, processes_pci, uses_ai,
                   next_review_at, created_at, updated_at
            FROM vendors
            WHERE {where_clause}
            ORDER BY name
        """, *params)
    return [dict(r) for r in rows]


@app.post("/vendors", status_code=201)
async def create_vendor(
    body: VendorCreateRequest,
    tenant_id: UUID = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
):
    """Create a vendor, run the intake risk rubric, and return risk score."""
    from .models import VendorIntakeRequest, VendorType
    try:
        vendor_type = VendorType(body.vendor_type)
    except ValueError:
        raise HTTPException(400, f"Invalid vendor_type: {body.vendor_type}")

    intake = VendorIntakeRequest(
        name=body.name,
        vendor_type=vendor_type,
        website=body.website,
        description=body.description,
        primary_contact_name=body.primary_contact_name,
        primary_contact_email=body.primary_contact_email,
        data_types_processed=body.data_types_processed,
        integrations_depth=body.integrations_depth,
        processes_pii=body.processes_pii,
        processes_phi=body.processes_phi,
        processes_pci=body.processes_pci,
        uses_ai=body.uses_ai,
        sub_processors=body.sub_processors,
    )
    engine = VendorIntake(db)
    return await engine.create_vendor(tenant_id, intake)


@app.get("/vendors/expiring-reviews")
async def get_expiring_reviews(
    tenant_id: UUID = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
):
    """List vendors whose next_review_at is within 30 days."""
    async with db.acquire() as conn:
        await conn.execute("SELECT set_config('app.tenant_id', $1, false)", str(tenant_id))
        rows = await conn.fetch("""
            SELECT id, name, vendor_type, risk_tier, inherent_risk_score,
                   next_review_at,
                   (next_review_at::date - CURRENT_DATE) AS days_until_review
            FROM vendors
            WHERE tenant_id = $1
              AND status = 'active'
              AND next_review_at IS NOT NULL
              AND next_review_at <= NOW() + INTERVAL '30 days'
            ORDER BY next_review_at ASC
        """, tenant_id)
    return [dict(r) for r in rows]


@app.get("/vendors/{vendor_id}")
async def get_vendor(
    vendor_id: UUID,
    tenant_id: UUID = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
):
    """Get full vendor detail."""
    async with db.acquire() as conn:
        await conn.execute("SELECT set_config('app.tenant_id', $1, false)", str(tenant_id))
        row = await conn.fetchrow("""
            SELECT * FROM vendors WHERE id = $1 AND tenant_id = $2
        """, vendor_id, tenant_id)
    if not row:
        raise HTTPException(404, f"Vendor {vendor_id} not found")
    return dict(row)


@app.patch("/vendors/{vendor_id}")
async def patch_vendor(
    vendor_id: UUID,
    body: VendorPatchRequest,
    tenant_id: UUID = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
):
    """Update mutable vendor fields."""
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "No fields to update")

    set_clauses = []
    params: List[Any] = []
    idx = 1
    for field, value in updates.items():
        set_clauses.append(f"{field} = ${idx}")
        params.append(value)
        idx += 1

    set_clauses.append(f"updated_at = NOW()")
    params.extend([vendor_id, tenant_id])

    async with db.acquire() as conn:
        await conn.execute("SELECT set_config('app.tenant_id', $1, false)", str(tenant_id))
        result = await conn.execute(f"""
            UPDATE vendors SET {', '.join(set_clauses)}
            WHERE id = ${idx} AND tenant_id = ${idx + 1}
        """, *params)

    if result == "UPDATE 0":
        raise HTTPException(404, f"Vendor {vendor_id} not found")
    return {"status": "updated", "vendor_id": str(vendor_id)}


@app.get("/vendors/{vendor_id}/risk-score")
async def get_vendor_risk_score(
    vendor_id: UUID,
    tenant_id: UUID = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
):
    """Get the latest risk score snapshot for a vendor."""
    async with db.acquire() as conn:
        await conn.execute("SELECT set_config('app.tenant_id', $1, false)", str(tenant_id))
        row = await conn.fetchrow("""
            SELECT vrs.*, v.name as vendor_name, v.risk_tier
            FROM vendor_risk_scores vrs
            JOIN vendors v ON v.id = vrs.vendor_id
            WHERE vrs.vendor_id = $1 AND vrs.tenant_id = $2
            ORDER BY vrs.scored_at DESC
            LIMIT 1
        """, vendor_id, tenant_id)
    if not row:
        raise HTTPException(404, f"No risk score found for vendor {vendor_id}")
    return dict(row)


# ---------------------------------------------------------------------------
# Questionnaires
# ---------------------------------------------------------------------------

@app.get("/questionnaires/templates")
async def list_questionnaire_templates(
    tenant_id: UUID = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
):
    """List all available questionnaire templates."""
    engine = QuestionnaireEngine(db, settings.templates_dir, settings.anthropic_api_key)
    try:
        return engine.list_templates()
    except Exception as e:
        logger.warning(f"Template listing failed: {e}")
        return []


@app.get("/questionnaires/templates/{slug}")
async def get_questionnaire_template(
    slug: str,
    tenant_id: UUID = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
):
    """Get template detail with all questions."""
    engine = QuestionnaireEngine(db, settings.templates_dir, settings.anthropic_api_key)
    try:
        return engine.load_template(slug)
    except FileNotFoundError:
        raise HTTPException(404, f"Template '{slug}' not found")


@app.post("/vendors/{vendor_id}/questionnaires", status_code=201)
async def send_questionnaire(
    vendor_id: UUID,
    body: SendQuestionnaireRequest,
    tenant_id: UUID = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
):
    """Send a questionnaire to a vendor."""
    engine = QuestionnaireEngine(db, settings.templates_dir, settings.anthropic_api_key)
    try:
        qid = await engine.send_questionnaire(tenant_id, vendor_id, body.template_slug, body.due_days)
    except FileNotFoundError:
        raise HTTPException(404, f"Template '{body.template_slug}' not found")
    return {"questionnaire_id": str(qid), "template_slug": body.template_slug, "vendor_id": str(vendor_id)}


@app.get("/vendors/{vendor_id}/questionnaires")
async def list_vendor_questionnaires(
    vendor_id: UUID,
    tenant_id: UUID = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
):
    """List all questionnaires for a vendor."""
    async with db.acquire() as conn:
        await conn.execute("SELECT set_config('app.tenant_id', $1, false)", str(tenant_id))
        rows = await conn.fetch("""
            SELECT id, template_slug, template_version, status, sent_at,
                   due_date, completed_at, ai_score, ai_summary
            FROM vendor_questionnaires
            WHERE vendor_id = $1 AND tenant_id = $2
            ORDER BY sent_at DESC
        """, vendor_id, tenant_id)
    return [dict(r) for r in rows]


@app.post("/questionnaires/{q_id}/responses")
async def submit_questionnaire_responses(
    q_id: UUID,
    body: SubmitResponsesRequest,
    tenant_id: UUID = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
):
    """Submit vendor responses and trigger AI scoring."""
    engine = QuestionnaireEngine(db, settings.templates_dir, settings.anthropic_api_key)
    try:
        result = await engine.submit_responses(tenant_id, q_id, body.responses)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"questionnaire_id": str(q_id), "ai_result": result}


@app.get("/questionnaires/{q_id}")
async def get_questionnaire(
    q_id: UUID,
    tenant_id: UUID = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
):
    """Get questionnaire detail including responses and AI score."""
    async with db.acquire() as conn:
        await conn.execute("SELECT set_config('app.tenant_id', $1, false)", str(tenant_id))
        row = await conn.fetchrow("""
            SELECT vq.*, v.name as vendor_name
            FROM vendor_questionnaires vq
            JOIN vendors v ON v.id = vq.vendor_id
            WHERE vq.id = $1 AND vq.tenant_id = $2
        """, q_id, tenant_id)
    if not row:
        raise HTTPException(404, f"Questionnaire {q_id} not found")
    return dict(row)


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

@app.post("/vendors/{vendor_id}/documents", status_code=201)
async def upload_vendor_document(
    vendor_id: UUID,
    document_type: str = Form(...),
    file: UploadFile = File(...),
    tenant_id: UUID = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
):
    """Upload a compliance document for a vendor."""
    content = await file.read()
    analyzer = VendorDocAnalyzer(
        db,
        settings.minio_endpoint,
        settings.minio_access_key,
        settings.minio_secret_key,
        settings.minio_vendor_docs_bucket,
        settings.anthropic_api_key,
    )
    doc_id = await analyzer.upload_document(
        tenant_id, vendor_id, document_type, file.filename, content
    )
    return {
        "document_id": str(doc_id),
        "vendor_id": str(vendor_id),
        "filename": file.filename,
        "document_type": document_type,
        "analysis_status": "pending"
    }


@app.get("/vendors/{vendor_id}/documents")
async def list_vendor_documents(
    vendor_id: UUID,
    tenant_id: UUID = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
):
    """List all documents for a vendor."""
    async with db.acquire() as conn:
        await conn.execute("SELECT set_config('app.tenant_id', $1, false)", str(tenant_id))
        rows = await conn.fetch("""
            SELECT id, document_type, filename, file_size_bytes,
                   analysis_status, expiry_date, created_at
            FROM vendor_documents
            WHERE vendor_id = $1 AND tenant_id = $2
            ORDER BY created_at DESC
        """, vendor_id, tenant_id)
    return [dict(r) for r in rows]


@app.post("/documents/{doc_id}/analyze")
async def trigger_document_analysis(
    doc_id: UUID,
    tenant_id: UUID = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
):
    """Trigger AI analysis of a previously uploaded document."""
    async with db.acquire() as conn:
        await conn.execute("SELECT set_config('app.tenant_id', $1, false)", str(tenant_id))
        row = await conn.fetchrow("""
            SELECT minio_path, filename FROM vendor_documents
            WHERE id = $1 AND tenant_id = $2
        """, doc_id, tenant_id)

    if not row:
        raise HTTPException(404, f"Document {doc_id} not found")

    analyzer = VendorDocAnalyzer(
        db,
        settings.minio_endpoint,
        settings.minio_access_key,
        settings.minio_secret_key,
        settings.minio_vendor_docs_bucket,
        settings.anthropic_api_key,
    )

    # Attempt to fetch content from MinIO; fall back to empty bytes in dev
    content = b""
    if analyzer._minio and row['minio_path']:
        try:
            response = analyzer._minio.get_object(settings.minio_vendor_docs_bucket, row['minio_path'])
            content = response.read()
        except Exception as e:
            logger.warning(f"MinIO fetch failed for doc {doc_id} (dev mode): {e}")

    result = await analyzer.analyze_document(tenant_id, doc_id, content)
    return {"document_id": str(doc_id), "analysis": result}


@app.get("/documents/{doc_id}/analysis")
async def get_document_analysis(
    doc_id: UUID,
    tenant_id: UUID = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
):
    """Get analysis results for a document."""
    async with db.acquire() as conn:
        await conn.execute("SELECT set_config('app.tenant_id', $1, false)", str(tenant_id))
        row = await conn.fetchrow("""
            SELECT id, document_type, filename, analysis_status,
                   ai_analysis, expiry_date, created_at
            FROM vendor_documents
            WHERE id = $1 AND tenant_id = $2
        """, doc_id, tenant_id)
    if not row:
        raise HTTPException(404, f"Document {doc_id} not found")
    return dict(row)


# ---------------------------------------------------------------------------
# Monitoring
# ---------------------------------------------------------------------------

@app.get("/vendors/{vendor_id}/monitoring-events")
async def get_vendor_monitoring_events(
    vendor_id: UUID,
    limit: int = Query(50, le=200),
    tenant_id: UUID = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
):
    """Get recent monitoring events for a vendor."""
    async with db.acquire() as conn:
        await conn.execute("SELECT set_config('app.tenant_id', $1, false)", str(tenant_id))
        rows = await conn.fetch("""
            SELECT id, event_source, event_type, severity, title,
                   description, source_url, created_at
            FROM vendor_monitoring_events
            WHERE vendor_id = $1 AND tenant_id = $2
            ORDER BY created_at DESC
            LIMIT $3
        """, vendor_id, tenant_id, limit)
    return [dict(r) for r in rows]


@app.post("/vendors/{vendor_id}/monitoring/run")
async def run_vendor_monitoring(
    vendor_id: UUID,
    tenant_id: UUID = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
):
    """Trigger an immediate monitoring cycle for a single vendor."""
    async with db.acquire() as conn:
        await conn.execute("SELECT set_config('app.tenant_id', $1, false)", str(tenant_id))
        vendor = await conn.fetchrow("""
            SELECT id, name, website FROM vendors
            WHERE id = $1 AND tenant_id = $2 AND status = 'active'
        """, vendor_id, tenant_id)

    if not vendor:
        raise HTTPException(404, f"Vendor {vendor_id} not found or not active")

    monitor = VendorMonitor(db, settings.securityscorecard_api_key)
    try:
        events = await monitor._monitor_vendor(tenant_id, vendor)
    finally:
        await monitor.close()

    return {"vendor_id": str(vendor_id), "events_recorded": len(events)}


@app.get("/monitoring/alerts")
async def get_monitoring_alerts(
    tenant_id: UUID = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
):
    """Get all critical/high severity events for tenant in the last 7 days."""
    async with db.acquire() as conn:
        await conn.execute("SELECT set_config('app.tenant_id', $1, false)", str(tenant_id))
        rows = await conn.fetch("""
            SELECT vme.id, vme.vendor_id, v.name as vendor_name,
                   vme.event_source, vme.event_type, vme.severity,
                   vme.title, vme.description, vme.source_url, vme.created_at
            FROM vendor_monitoring_events vme
            JOIN vendors v ON v.id = vme.vendor_id
            WHERE vme.tenant_id = $1
              AND vme.severity IN ('critical', 'high')
              AND vme.created_at >= NOW() - INTERVAL '7 days'
            ORDER BY vme.created_at DESC
        """, tenant_id)
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Contracts
# ---------------------------------------------------------------------------

@app.get("/vendors/{vendor_id}/contracts")
async def list_vendor_contracts(
    vendor_id: UUID,
    tenant_id: UUID = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
):
    """List all contracts for a vendor."""
    tracker = ContractTracker(db)
    return await tracker.get_vendor_contracts(tenant_id, vendor_id)


@app.post("/vendors/{vendor_id}/contracts", status_code=201)
async def add_vendor_contract(
    vendor_id: UUID,
    body: ContractCreateRequest,
    tenant_id: UUID = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
):
    """Add a contract for a vendor."""
    from datetime import date as _date

    contract_data = body.model_dump()

    # Parse date strings
    for field in ('effective_date', 'expiry_date'):
        val = contract_data.get(field)
        if val:
            try:
                contract_data[field] = _date.fromisoformat(val)
            except ValueError:
                raise HTTPException(400, f"{field} must be ISO 8601 date (YYYY-MM-DD)")

    tracker = ContractTracker(db)
    contract_id = await tracker.add_contract(tenant_id, vendor_id, contract_data)
    return {"contract_id": str(contract_id), "vendor_id": str(vendor_id)}


@app.get("/contracts/expiring")
async def get_expiring_contracts(
    days_ahead: int = Query(90, ge=1, le=365),
    tenant_id: UUID = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
):
    """List contracts expiring within the specified number of days."""
    tracker = ContractTracker(db)
    return await tracker.get_expiring_contracts(tenant_id, days_ahead)


# ---------------------------------------------------------------------------
# Fourth-party
# ---------------------------------------------------------------------------

@app.get("/fourth-party/graph")
async def get_fourth_party_graph(
    tenant_id: UUID = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
):
    """Return the full vendor → sub-processor graph for the tenant."""
    analyzer = FourthPartyAnalyzer(db)
    return await analyzer.get_fourth_party_graph(tenant_id)


@app.post("/vendors/{vendor_id}/fourth-party", status_code=201)
async def add_fourth_party_relationship(
    vendor_id: UUID,
    body: FourthPartyAddRequest,
    tenant_id: UUID = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
):
    """Manually add a fourth-party (sub-processor) relationship."""
    analyzer = FourthPartyAnalyzer(db)
    rel_id = await analyzer.add_relationship(
        tenant_id, vendor_id, body.sub_processor_name, body.risk_tier, body.data_types
    )
    return {
        "relationship_id": str(rel_id),
        "vendor_id": str(vendor_id),
        "sub_processor_name": body.sub_processor_name
    }


@app.post("/vendors/{vendor_id}/fourth-party/sync")
async def sync_fourth_party_from_vendor(
    vendor_id: UUID,
    tenant_id: UUID = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
):
    """Sync sub-processors from vendor.sub_processors field into fourth_party_relationships."""
    analyzer = FourthPartyAnalyzer(db)
    added = await analyzer.sync_from_vendor(tenant_id, vendor_id)
    return {"vendor_id": str(vendor_id), "relationships_added": added}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=settings.tprm_service_port,
        reload=False,
    )
