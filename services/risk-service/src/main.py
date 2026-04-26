"""
Risk Service — FastAPI application (port 3021)

Routes:
  GET    /risks
  POST   /risks
  GET    /risks/register
  GET    /risks/heatmap
  GET    /risks/{risk_id}
  PUT    /risks/{risk_id}
  POST   /risks/{risk_id}/close
  POST   /risks/{risk_id}/assess

  GET    /appetite
  POST   /appetite/{category_key}
  GET    /appetite/summary
  GET    /appetite/check/{risk_id}

  GET    /treatments
  POST   /treatments
  PUT    /treatments/{treatment_id}
  GET    /treatments/summary

  GET    /indicators
  POST   /indicators
  POST   /indicators/{indicator_id}/reading
  GET    /indicators/red

  POST   /ai/suggest-treatments/{risk_id}
  POST   /ai/assess
  GET    /ai/narrative

  POST   /auto-import/from-findings

  GET    /categories

  GET    /health
"""

import logging
import uuid
from contextlib import asynccontextmanager

import asyncpg
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel

from .ai_risk_advisor import AIRiskAdvisor
from .appetite_manager import AppetiteManager
from .config import settings
from .db import close_pool, get_pool
from .indicator_manager import IndicatorManager
from .models import (
    AssessmentCreate,
    IndicatorCreate,
    IndicatorReading,
    RiskCreate,
    RiskUpdate,
    TreatmentCreate,
    TreatmentUpdate,
)
from .risk_manager import RiskManager
from .treatment_manager import TreatmentManager

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ---------------------------------------------------------------------------
# Module-level singletons
# ---------------------------------------------------------------------------
_pool: asyncpg.Pool | None = None
_risk_manager = RiskManager()
_appetite_manager = AppetiteManager()
_treatment_manager = TreatmentManager()
_indicator_manager = IndicatorManager()
_ai_advisor = AIRiskAdvisor(settings)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool
    _pool = await get_pool()
    logger.info("DB pool created")
    yield
    await close_pool()
    logger.info("risk-service shut down")


app = FastAPI(
    title="Aegis Risk Service",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

def get_db() -> asyncpg.Pool:
    if _pool is None:
        raise HTTPException(503, "DB pool not ready")
    return _pool


async def get_tenant_id(x_tenant_id: str = Header(..., alias="X-Tenant-ID")) -> str:
    try:
        uuid.UUID(x_tenant_id)
    except ValueError:
        raise HTTPException(400, "X-Tenant-ID must be a valid UUID")
    return x_tenant_id


# ---------------------------------------------------------------------------
# Request bodies (local — not in models.py)
# ---------------------------------------------------------------------------

class CloseRiskRequest(BaseModel):
    reason: str = ""


class AppetiteUpsertRequest(BaseModel):
    appetite_level: str
    max_acceptable_score: float
    description: str | None = None
    approved_by: str | None = None


class AIAssessRequest(BaseModel):
    title: str
    description: str


class AutoImportRequest(BaseModel):
    limit: int = 50


# ---------------------------------------------------------------------------
# Risk Register endpoints
# ---------------------------------------------------------------------------

@app.get("/risks")
async def list_risks(
    status: str | None = Query(None),
    category_key: str | None = Query(None),
    min_score: float | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    pool: asyncpg.Pool = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    risks = await _risk_manager.list(
        pool, tenant_id,
        status=status,
        category_key=category_key,
        min_score=min_score,
        limit=limit,
    )
    return {"risks": risks, "count": len(risks)}


@app.post("/risks", status_code=201)
async def create_risk(
    body: RiskCreate,
    pool: asyncpg.Pool = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    try:
        risk = await _risk_manager.create(pool, tenant_id, body)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return risk


@app.get("/risks/register")
async def get_register(
    pool: asyncpg.Pool = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    return await _risk_manager.get_register(pool, tenant_id)


@app.get("/risks/heatmap")
async def get_heatmap(
    pool: asyncpg.Pool = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    data = await _risk_manager.get_heatmap_data(pool, tenant_id)
    return {"risks": data, "count": len(data)}


@app.get("/risks/{risk_id}")
async def get_risk(
    risk_id: str,
    pool: asyncpg.Pool = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    risk = await _risk_manager.get(pool, tenant_id, risk_id)
    if not risk:
        raise HTTPException(404, "Risk not found")
    return risk


@app.put("/risks/{risk_id}")
async def update_risk(
    risk_id: str,
    body: RiskUpdate,
    changed_by: str = Header("api", alias="X-Changed-By"),
    pool: asyncpg.Pool = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    try:
        risk = await _risk_manager.update(pool, tenant_id, risk_id, body, changed_by=changed_by)
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    return risk


@app.post("/risks/{risk_id}/close")
async def close_risk(
    risk_id: str,
    body: CloseRiskRequest,
    pool: asyncpg.Pool = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    try:
        risk = await _risk_manager.close(pool, tenant_id, risk_id, body.reason)
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    return risk


@app.post("/risks/{risk_id}/assess", status_code=201)
async def add_assessment(
    risk_id: str,
    body: AssessmentCreate,
    pool: asyncpg.Pool = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    # Override risk_id in body with path param
    body_data = body.model_copy(update={"risk_id": risk_id})
    try:
        assessment = await _risk_manager.add_assessment(pool, tenant_id, body_data)
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    return assessment


# ---------------------------------------------------------------------------
# Risk Appetite endpoints
# ---------------------------------------------------------------------------

@app.get("/appetite")
async def get_appetite(
    pool: asyncpg.Pool = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    statements = await _appetite_manager.get_all(pool, tenant_id)
    return {"appetite": statements, "count": len(statements)}


@app.post("/appetite/{category_key}", status_code=201)
async def upsert_appetite(
    category_key: str,
    body: AppetiteUpsertRequest,
    pool: asyncpg.Pool = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    try:
        result = await _appetite_manager.upsert(
            pool, tenant_id, category_key,
            appetite_level=body.appetite_level,
            max_acceptable_score=body.max_acceptable_score,
            description=body.description,
            approved_by=body.approved_by,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return result


@app.get("/appetite/summary")
async def appetite_summary(
    pool: asyncpg.Pool = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    return await _appetite_manager.get_summary(pool, tenant_id)


@app.get("/appetite/check/{risk_id}")
async def check_appetite(
    risk_id: str,
    pool: asyncpg.Pool = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    try:
        result = await _appetite_manager.check_risk_vs_appetite(pool, tenant_id, risk_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    return result


# ---------------------------------------------------------------------------
# Treatment endpoints
# ---------------------------------------------------------------------------

@app.get("/treatments")
async def list_treatments(
    status: str | None = Query(None),
    risk_id: str | None = Query(None),
    pool: asyncpg.Pool = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    treatments = await _treatment_manager.list(pool, tenant_id, status=status, risk_id=risk_id)
    return {"treatments": treatments, "count": len(treatments)}


@app.post("/treatments", status_code=201)
async def create_treatment(
    body: TreatmentCreate,
    pool: asyncpg.Pool = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    try:
        treatment = await _treatment_manager.create(pool, tenant_id, body)
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    return treatment


@app.put("/treatments/{treatment_id}")
async def update_treatment(
    treatment_id: str,
    body: TreatmentUpdate,
    pool: asyncpg.Pool = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    try:
        treatment = await _treatment_manager.update(pool, tenant_id, treatment_id, body)
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    return treatment


@app.get("/treatments/summary")
async def treatment_summary(
    pool: asyncpg.Pool = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    return await _treatment_manager.get_effectiveness_summary(pool, tenant_id)


# ---------------------------------------------------------------------------
# Indicator endpoints
# ---------------------------------------------------------------------------

@app.get("/indicators")
async def list_indicators(
    risk_id: str | None = Query(None),
    status: str | None = Query(None),
    pool: asyncpg.Pool = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    indicators = await _indicator_manager.list(
        pool, tenant_id, risk_id=risk_id, status=status
    )
    return {"indicators": indicators, "count": len(indicators)}


@app.post("/indicators", status_code=201)
async def create_indicator(
    body: IndicatorCreate,
    pool: asyncpg.Pool = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    try:
        indicator = await _indicator_manager.create(pool, tenant_id, body)
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    return indicator


@app.post("/indicators/{indicator_id}/reading", status_code=201)
async def record_reading(
    indicator_id: str,
    body: IndicatorReading,
    pool: asyncpg.Pool = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    body_data = body.model_copy(update={"indicator_id": indicator_id})
    try:
        reading = await _indicator_manager.record_reading(pool, tenant_id, body_data)
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    return reading


@app.get("/indicators/red")
async def get_red_indicators(
    pool: asyncpg.Pool = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    indicators = await _indicator_manager.get_red_indicators(pool, tenant_id)
    return {"indicators": indicators, "count": len(indicators)}


# ---------------------------------------------------------------------------
# AI endpoints
# ---------------------------------------------------------------------------

@app.post("/ai/suggest-treatments/{risk_id}")
async def ai_suggest_treatments(
    risk_id: str,
    pool: asyncpg.Pool = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    risk = await _risk_manager.get(pool, tenant_id, risk_id)
    if not risk:
        raise HTTPException(404, "Risk not found")
    suggestions = await _ai_advisor.suggest_treatments(risk)
    return {"risk_id": risk_id, "suggestions": suggestions}


@app.post("/ai/assess")
async def ai_assess(
    body: AIAssessRequest,
    pool: asyncpg.Pool = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    result = await _ai_advisor.assess_risk_description(body.title, body.description)
    return result


@app.get("/ai/narrative")
async def ai_narrative(
    pool: asyncpg.Pool = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    narrative = await _ai_advisor.generate_risk_narrative(pool, tenant_id)
    return {"narrative": narrative}


# ---------------------------------------------------------------------------
# Auto-import endpoint
# ---------------------------------------------------------------------------

@app.post("/auto-import/from-findings")
async def auto_import_from_findings(
    body: AutoImportRequest,
    pool: asyncpg.Pool = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    """
    Pull recent open findings from monitoring-service and auto-create risks.
    """
    import httpx

    created: list[dict] = []
    skipped = 0
    errors = 0

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{settings.monitoring_service_url}/findings",
                headers={"X-Tenant-ID": tenant_id},
                params={"status": "open", "limit": body.limit},
            )
            resp.raise_for_status()
            findings_data = resp.json().get("findings", [])
    except Exception as exc:
        logger.error("Failed to fetch findings from monitoring-service: %s", exc)
        raise HTTPException(502, f"Could not reach monitoring-service: {exc}")

    for finding in findings_data:
        finding_id = str(finding.get("id", ""))
        if not finding_id:
            continue
        try:
            result = await _risk_manager.auto_create_from_finding(
                pool, tenant_id, finding_id, finding
            )
            if result is None:
                skipped += 1
            else:
                created.append(result)
        except Exception as exc:
            logger.error("auto_create_from_finding error for %s: %s", finding_id, exc)
            errors += 1

    return {
        "created": len(created),
        "skipped_duplicates": skipped,
        "errors": errors,
        "risks": created,
    }


# ---------------------------------------------------------------------------
# Categories endpoint
# ---------------------------------------------------------------------------

@app.get("/categories")
async def list_categories(pool: asyncpg.Pool = Depends(get_db)):
    """List all risk categories (platform-level, no tenant filter)."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, category_key, name, description, created_at
            FROM risk_categories
            ORDER BY name
            """
        )
    return {"categories": [dict(r) for r in rows]}


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok", "service": "risk-service"}
