"""
Framework Service — FastAPI application

Routes:
  GET  /health
  GET  /frameworks
  GET  /frameworks/{slug}
  POST /admin/reload-frameworks

  GET    /tenants/{tenant_id}/frameworks
  POST   /tenants/{tenant_id}/frameworks/{slug}/activate
  DELETE /tenants/{tenant_id}/frameworks/{slug}

  GET  /tenants/{tenant_id}/score
  POST /tenants/{tenant_id}/score/refresh

  GET  /tenants/{tenant_id}/gaps
  GET  /tenants/{tenant_id}/gaps/{framework_slug}

  GET  /tenants/{tenant_id}/calendar
  POST /tenants/{tenant_id}/calendar/rebuild

  GET  /tenants/{tenant_id}/crosswalk
  POST /controls/{control_id}/evidence
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Optional, List
from uuid import UUID

import asyncpg
import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, HTTPException, Depends, Header, Query
from pydantic import BaseModel

from .calendar_builder import CalendarBuilder
from .compliance_scorer import ComplianceScorer
from .config import settings
from .crosswalk_engine import CrosswalkEngine
from .db import get_pool, close_pool
from .framework_loader import FrameworkLoader
from .gap_analyzer import GapAnalyzer

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

_scheduler: Optional[AsyncIOScheduler] = None


async def _refresh_all_scores():
    """APScheduler job: refresh compliance scores for all tenants with active frameworks."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            tenant_rows = await conn.fetch("""
                SELECT DISTINCT tenant_id FROM tenant_frameworks WHERE is_active = TRUE
            """)
        scorer = ComplianceScorer(pool)
        for row in tenant_rows:
            try:
                await scorer.compute_all_tenant_scores(row['tenant_id'])
            except Exception as e:
                logger.error(f"Score refresh failed for tenant {row['tenant_id']}: {e}")
    except Exception as e:
        logger.error(f"Score refresh job error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler

    pool = await get_pool()
    logger.info("DB pool ready")

    # Load framework YAML files into DB
    loader = FrameworkLoader(pool, settings.frameworks_dir)
    try:
        results = await loader.load_all()
        logger.info(f"Framework loader results: {results}")
    except Exception as e:
        logger.warning(f"Framework loader encountered errors: {e}")

    # Start background score refresh scheduler
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        _refresh_all_scores,
        'interval',
        minutes=settings.score_refresh_interval_minutes,
        id='score_refresh',
        replace_existing=True,
    )
    _scheduler.start()
    logger.info(f"APScheduler started — score refresh every {settings.score_refresh_interval_minutes} min")

    yield

    _scheduler.shutdown(wait=False)
    await close_pool()
    logger.info("Framework service shut down")


app = FastAPI(title="Aegis Framework Service", version="1.0.0", lifespan=lifespan)


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
# Pydantic request/response schemas
# ---------------------------------------------------------------------------

class ActivateFrameworkRequest(BaseModel):
    target_cert_date: Optional[str] = None  # ISO date string


class LinkEvidenceRequest(BaseModel):
    tenant_id: str
    evidence_record_id: str
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok", "service": "framework-service"}


# ---------------------------------------------------------------------------
# Framework catalogue (no tenant context required)
# ---------------------------------------------------------------------------

@app.get("/frameworks")
async def list_frameworks(db: asyncpg.Pool = Depends(get_db)):
    """List all available compliance frameworks."""
    async with db.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, slug, name, version, category, issuing_body, description,
                   (SELECT COUNT(*) FROM framework_controls fc WHERE fc.framework_id = cf.id) AS control_count
            FROM compliance_frameworks cf
            ORDER BY name
        """)
    return [dict(r) for r in rows]


@app.get("/frameworks/{slug}")
async def get_framework(slug: str, db: asyncpg.Pool = Depends(get_db)):
    """Get framework detail including all controls."""
    async with db.acquire() as conn:
        fw = await conn.fetchrow(
            "SELECT * FROM compliance_frameworks WHERE slug = $1", slug
        )
        if not fw:
            raise HTTPException(404, f"Framework '{slug}' not found")

        controls = await conn.fetch("""
            SELECT id, control_id, domain, title, description, guidance,
                   evidence_types, testing_frequency, is_key_control
            FROM framework_controls
            WHERE framework_id = $1
            ORDER BY domain, control_id
        """, fw['id'])

    return {**dict(fw), "controls": [dict(c) for c in controls]}


@app.post("/admin/reload-frameworks", status_code=200)
async def reload_frameworks(db: asyncpg.Pool = Depends(get_db)):
    """Reload framework YAML definitions from disk. Admin use only."""
    loader = FrameworkLoader(db, settings.frameworks_dir)
    results = await loader.load_all()
    return {"reloaded": results}


# ---------------------------------------------------------------------------
# Tenant framework management
# ---------------------------------------------------------------------------

@app.get("/tenants/{tenant_id}/frameworks")
async def list_tenant_frameworks(
    tenant_id: UUID,
    x_tenant_id: UUID = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
):
    if tenant_id != x_tenant_id:
        raise HTTPException(403, "Tenant ID mismatch")
    async with db.acquire() as conn:
        await conn.execute("SET LOCAL app.tenant_id = $1", str(tenant_id))
        rows = await conn.fetch("""
            SELECT tf.framework_id, tf.is_active, tf.activated_at, tf.target_cert_date,
                   cf.slug, cf.name, cf.version, cf.category
            FROM tenant_frameworks tf
            JOIN compliance_frameworks cf ON cf.id = tf.framework_id
            WHERE tf.tenant_id = $1
            ORDER BY cf.name
        """, tenant_id)
    return [dict(r) for r in rows]


@app.post("/tenants/{tenant_id}/frameworks/{slug}/activate", status_code=201)
async def activate_framework(
    tenant_id: UUID,
    slug: str,
    body: ActivateFrameworkRequest,
    x_tenant_id: UUID = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
):
    if tenant_id != x_tenant_id:
        raise HTTPException(403, "Tenant ID mismatch")

    async with db.acquire() as conn:
        await conn.execute("SET LOCAL app.tenant_id = $1", str(tenant_id))

        framework_id = await conn.fetchval(
            "SELECT id FROM compliance_frameworks WHERE slug = $1", slug
        )
        if not framework_id:
            raise HTTPException(404, f"Framework '{slug}' not found")

        target_cert_date = None
        if body.target_cert_date:
            from datetime import date as _date
            try:
                target_cert_date = _date.fromisoformat(body.target_cert_date)
            except ValueError:
                raise HTTPException(400, "target_cert_date must be ISO 8601 date (YYYY-MM-DD)")

        await conn.execute("""
            INSERT INTO tenant_frameworks (tenant_id, framework_id, is_active, activated_at, target_cert_date)
            VALUES ($1, $2, TRUE, NOW(), $3)
            ON CONFLICT (tenant_id, framework_id) DO UPDATE SET
                is_active = TRUE,
                activated_at = NOW(),
                target_cert_date = EXCLUDED.target_cert_date
        """, tenant_id, framework_id, target_cert_date)

    return {"status": "activated", "framework": slug, "tenant_id": str(tenant_id)}


@app.delete("/tenants/{tenant_id}/frameworks/{slug}", status_code=200)
async def deactivate_framework(
    tenant_id: UUID,
    slug: str,
    x_tenant_id: UUID = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
):
    if tenant_id != x_tenant_id:
        raise HTTPException(403, "Tenant ID mismatch")

    async with db.acquire() as conn:
        await conn.execute("SET LOCAL app.tenant_id = $1", str(tenant_id))

        framework_id = await conn.fetchval(
            "SELECT id FROM compliance_frameworks WHERE slug = $1", slug
        )
        if not framework_id:
            raise HTTPException(404, f"Framework '{slug}' not found")

        result = await conn.execute("""
            UPDATE tenant_frameworks SET is_active = FALSE
            WHERE tenant_id = $1 AND framework_id = $2
        """, tenant_id, framework_id)

        if result == "UPDATE 0":
            raise HTTPException(404, f"Framework '{slug}' is not activated for this tenant")

    return {"status": "deactivated", "framework": slug, "tenant_id": str(tenant_id)}


# ---------------------------------------------------------------------------
# Compliance scoring
# ---------------------------------------------------------------------------

@app.get("/tenants/{tenant_id}/score")
async def get_scores(
    tenant_id: UUID,
    x_tenant_id: UUID = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
):
    if tenant_id != x_tenant_id:
        raise HTTPException(403, "Tenant ID mismatch")
    scorer = ComplianceScorer(db)
    scores = await scorer.get_latest_scores(tenant_id)
    return scores


@app.post("/tenants/{tenant_id}/score/refresh")
async def refresh_scores(
    tenant_id: UUID,
    x_tenant_id: UUID = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
):
    if tenant_id != x_tenant_id:
        raise HTTPException(403, "Tenant ID mismatch")
    scorer = ComplianceScorer(db)
    scores = await scorer.compute_all_tenant_scores(tenant_id)
    return [asdict(s) for s in scores]


# ---------------------------------------------------------------------------
# Gap analysis
# ---------------------------------------------------------------------------

@app.get("/tenants/{tenant_id}/gaps")
async def get_all_gaps(
    tenant_id: UUID,
    x_tenant_id: UUID = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
):
    if tenant_id != x_tenant_id:
        raise HTTPException(403, "Tenant ID mismatch")

    async with db.acquire() as conn:
        await conn.execute("SET LOCAL app.tenant_id = $1", str(tenant_id))
        active_fws = await conn.fetch("""
            SELECT tf.framework_id, cf.slug
            FROM tenant_frameworks tf
            JOIN compliance_frameworks cf ON cf.id = tf.framework_id
            WHERE tf.tenant_id = $1 AND tf.is_active = TRUE
        """, tenant_id)

    analyzer = GapAnalyzer(db, settings.anthropic_api_key)
    all_gaps = []
    for fw in active_fws:
        gaps = await analyzer.analyze(tenant_id, fw['framework_id'])
        for gap in gaps:
            gap_dict = asdict(gap)
            gap_dict['framework_slug'] = fw['slug']
            all_gaps.append(gap_dict)

    return all_gaps


@app.get("/tenants/{tenant_id}/gaps/{framework_slug}")
async def get_framework_gaps(
    tenant_id: UUID,
    framework_slug: str,
    x_tenant_id: UUID = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
):
    if tenant_id != x_tenant_id:
        raise HTTPException(403, "Tenant ID mismatch")

    async with db.acquire() as conn:
        await conn.execute("SET LOCAL app.tenant_id = $1", str(tenant_id))
        row = await conn.fetchrow("""
            SELECT tf.framework_id
            FROM tenant_frameworks tf
            JOIN compliance_frameworks cf ON cf.id = tf.framework_id
            WHERE tf.tenant_id = $1 AND cf.slug = $2 AND tf.is_active = TRUE
        """, tenant_id, framework_slug)

    if not row:
        raise HTTPException(404, f"Framework '{framework_slug}' is not active for this tenant")

    analyzer = GapAnalyzer(db, settings.anthropic_api_key)
    gaps = await analyzer.analyze(tenant_id, row['framework_id'])
    return [asdict(g) for g in gaps]


# ---------------------------------------------------------------------------
# Compliance calendar
# ---------------------------------------------------------------------------

@app.get("/tenants/{tenant_id}/calendar")
async def get_calendar(
    tenant_id: UUID,
    x_tenant_id: UUID = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
):
    if tenant_id != x_tenant_id:
        raise HTTPException(403, "Tenant ID mismatch")

    async with db.acquire() as conn:
        await conn.execute("SET LOCAL app.tenant_id = $1", str(tenant_id))
        rows = await conn.fetch("""
            SELECT cce.id, cce.framework_id, cf.name as framework_name, cce.event_type,
                   cce.title, cce.due_date, cce.description, cce.is_completed,
                   (cce.due_date - CURRENT_DATE) AS days_until_due
            FROM compliance_calendar_events cce
            JOIN compliance_frameworks cf ON cf.id = cce.framework_id
            WHERE cce.tenant_id = $1
              AND cce.due_date >= CURRENT_DATE
              AND cce.due_date <= CURRENT_DATE + INTERVAL '12 months'
            ORDER BY cce.due_date
        """, tenant_id)
    return [dict(r) for r in rows]


@app.post("/tenants/{tenant_id}/calendar/rebuild")
async def rebuild_calendar(
    tenant_id: UUID,
    x_tenant_id: UUID = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
):
    if tenant_id != x_tenant_id:
        raise HTTPException(403, "Tenant ID mismatch")
    builder = CalendarBuilder(db)
    events = await builder.build_for_tenant(tenant_id)
    return [asdict(e) for e in events]


# ---------------------------------------------------------------------------
# Crosswalk
# ---------------------------------------------------------------------------

@app.get("/tenants/{tenant_id}/crosswalk")
async def get_crosswalk(
    tenant_id: UUID,
    x_tenant_id: UUID = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
):
    if tenant_id != x_tenant_id:
        raise HTTPException(403, "Tenant ID mismatch")
    engine = CrosswalkEngine(db)
    return await engine.get_tenant_crosswalk_coverage(tenant_id)


# ---------------------------------------------------------------------------
# Evidence linking + crosswalk credit
# ---------------------------------------------------------------------------

@app.post("/controls/{control_id}/evidence", status_code=201)
async def link_evidence(
    control_id: UUID,
    body: LinkEvidenceRequest,
    db: asyncpg.Pool = Depends(get_db),
):
    """
    Link an evidence record to a framework control.
    Automatically applies crosswalk credit to equivalent controls for the tenant.
    """
    try:
        tenant_id = UUID(body.tenant_id)
        evidence_record_id = UUID(body.evidence_record_id)
    except ValueError as e:
        raise HTTPException(400, f"Invalid UUID: {e}")

    async with db.acquire() as conn:
        await conn.execute("SET LOCAL app.tenant_id = $1", str(tenant_id))

        # Verify control exists
        ctrl = await conn.fetchrow(
            "SELECT id, framework_id FROM framework_controls WHERE id = $1", control_id
        )
        if not ctrl:
            raise HTTPException(404, f"Control {control_id} not found")

        # Upsert primary evidence link
        await conn.execute("""
            INSERT INTO tenant_control_evidence
                (tenant_id, framework_control_id, evidence_record_id, status, last_tested_at, notes)
            VALUES ($1, $2, $3, 'passing', NOW(), $4)
            ON CONFLICT (tenant_id, framework_control_id) DO UPDATE SET
                status = 'passing',
                evidence_record_id = EXCLUDED.evidence_record_id,
                last_tested_at = NOW(),
                notes = EXCLUDED.notes
        """, tenant_id, control_id, evidence_record_id, body.notes)

    # Apply crosswalk credit to equivalent controls
    engine = CrosswalkEngine(db)
    credited = await engine.apply_crosswalk_credit(tenant_id, evidence_record_id, control_id)

    return {
        "status": "linked",
        "control_id": str(control_id),
        "evidence_record_id": str(evidence_record_id),
        "crosswalk_credits_applied": credited,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=settings.framework_service_port,
        reload=False,
    )
