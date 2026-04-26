"""
FastAPI application for the forensic-ml-service.

Routes:
  GET  /health                          — model counts per tenant (from DB)
  POST /score                           — synchronous scoring; auth required
  GET  /anomalies                       — paginated anomaly score list for tenant
  GET  /anomalies/{score_id}            — full anomaly score detail
  PATCH /anomalies/{score_id}/review    — HITL review; requires auditor role
  POST /training/trigger                — immediate training trigger; requires admin
  GET  /training/status                 — latest training job status per model type
  GET  /benford/{entity_id}             — Benford stats for entity; requires auditor
  GET  /risk-heatmap                    — top-50 highest-risk entities for Firm Mode

Lifespan: DB pool, MLflow connection, Kafka consumer (background task),
          APScheduler weekly retraining cron (Sunday 02:00 UTC).
"""

import asyncio
import json
import structlog
from contextlib import asynccontextmanager
from datetime import datetime, timezone, date
from typing import Optional
from uuid import UUID

import asyncpg
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import Depends, FastAPI, HTTPException, Query, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from .config import settings
from .db import create_pool, close_pool
from .kafka_consumer import MLKafkaConsumer
from .model_store import ModelStore
from .scorer import AnomalyScorer, _model_cache
from .training import TenantTrainingPipeline

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Globals set during lifespan
# ---------------------------------------------------------------------------
_pool: asyncpg.Pool | None = None
_model_store: ModelStore | None = None
_scorer: AnomalyScorer | None = None
_kafka_consumer: MLKafkaConsumer | None = None
_training_pipeline: TenantTrainingPipeline | None = None
_scheduler: AsyncIOScheduler | None = None


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool, _model_store, _scorer, _kafka_consumer, _training_pipeline, _scheduler

    # DB pool
    _pool = await create_pool()
    logger.info("DB pool created")

    # MLflow model store
    _model_store = ModelStore(tracking_uri=settings.mlflow_tracking_uri)
    logger.info("ModelStore initialised", tracking_uri=settings.mlflow_tracking_uri)

    # Scorer and training pipeline
    _scorer = AnomalyScorer(_pool, _model_store)
    _training_pipeline = TenantTrainingPipeline(_pool, _model_store)

    # Kafka consumer — run in background
    _kafka_consumer = MLKafkaConsumer(_scorer)
    await _kafka_consumer.start()
    asyncio.create_task(_kafka_consumer.consume_loop())
    logger.info("Kafka consumer started")

    # APScheduler — weekly retraining Sunday 02:00 UTC
    _scheduler = AsyncIOScheduler(timezone='UTC')
    _scheduler.add_job(
        _run_weekly_training,
        trigger='cron',
        day_of_week='sun',
        hour=2,
        minute=0,
        id='weekly_retraining',
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("APScheduler started — weekly retraining scheduled Sun 02:00 UTC")

    yield

    # Shutdown
    _scheduler.shutdown(wait=False)
    await _kafka_consumer.stop()
    await close_pool(_pool)
    logger.info("forensic-ml-service shut down")


async def _run_weekly_training():
    """Cron callback: retrain all active tenants."""
    if _pool is None or _training_pipeline is None:
        return
    async with _pool.acquire() as conn:
        rows = await conn.fetch("SELECT DISTINCT tenant_id, framework FROM ml_model_registry WHERE is_active=TRUE")
    seen = set()
    for row in rows:
        key = (str(row['tenant_id']), row['framework'])
        if key not in seen:
            seen.add(key)
            try:
                await _training_pipeline.train_tenant(str(row['tenant_id']), row['framework'])
            except Exception as exc:
                logger.error("Weekly training failed", tenant_id=str(row['tenant_id']), error=str(exc))


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="forensic-ml-service",
    version="1.0.0",
    description="Project Aegis 2026 — ML anomaly scoring and DRI computation",
    lifespan=lifespan,
)

security = HTTPBearer()


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------
async def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise HTTPException(status_code=503, detail="DB pool not initialised")
    return _pool


async def get_scorer() -> AnomalyScorer:
    if _scorer is None:
        raise HTTPException(status_code=503, detail="Scorer not initialised")
    return _scorer


async def get_training_pipeline() -> TenantTrainingPipeline:
    if _training_pipeline is None:
        raise HTTPException(status_code=503, detail="Training pipeline not initialised")
    return _training_pipeline


async def _resolve_token(
    credentials: HTTPAuthorizationCredentials = Security(security),
    pool: asyncpg.Pool = Depends(get_pool),
) -> dict:
    """
    Validate Bearer JWT and return the claims dict.
    Looks up the session in auth_sessions joined to org_members.
    Returns: {tenant_id, user_id, role}
    """
    token = credentials.credentials
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT s.tenant_id, s.user_id, om.role
            FROM auth_sessions s
            JOIN org_members om ON om.user_id = s.user_id AND om.tenant_id = s.tenant_id
            WHERE s.token_hash = encode(digest($1, 'sha256'), 'hex')
              AND s.expires_at > NOW()
              AND s.revoked = FALSE
        """, token)
    if not row:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return {'tenant_id': str(row['tenant_id']), 'user_id': str(row['user_id']), 'role': row['role']}


def _require_role(*roles: str):
    async def checker(claims: dict = Depends(_resolve_token)) -> dict:
        if claims['role'] not in roles:
            raise HTTPException(status_code=403, detail=f"Role '{claims['role']}' not authorised for this endpoint")
        return claims
    return checker


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class ScoreRequest(BaseModel):
    tenant_id: str
    evidence_record: dict
    framework: str = 'soc2'


class ScoreResponse(BaseModel):
    dynamic_risk_index: float
    risk_level: str
    vae_score: float
    isolation_score: float
    benford_risk: float
    scored_by: str
    top_risk_factors: list[dict]


class ReviewRequest(BaseModel):
    false_positive: bool
    justification: str = Field(..., min_length=10, max_length=2000)


class TriggerTrainingRequest(BaseModel):
    framework: str = 'soc2'


class AnomalyListItem(BaseModel):
    score_id: str
    evidence_id: str
    dynamic_risk_index: float
    risk_level: str
    source_system: str
    scored_at: datetime
    reviewed: bool


class AnomalyDetail(AnomalyListItem):
    vae_score: float
    isolation_score: float
    benford_risk: float
    scored_by: str
    top_risk_factors: list[dict]
    feature_vector: dict | None
    false_positive: bool | None
    justification: str | None


class BenfordStats(BaseModel):
    entity_id: str
    entity_type: str
    transaction_count: int
    first_digit_distribution: dict
    expected_distribution: dict
    mad: float
    chi2_statistic: float
    chi2_pvalue: float
    conforming: bool
    window_start: datetime
    window_end: datetime


class RiskHeatmapEntry(BaseModel):
    entity_id: str
    entity_type: str
    avg_dri: float
    max_dri: float
    anomaly_count: int
    last_scored_at: datetime


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health", tags=["ops"])
async def health(pool: asyncpg.Pool = Depends(get_pool)):
    """Returns active model counts per tenant."""
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT tenant_id, COUNT(*) AS model_count
            FROM ml_model_registry
            WHERE is_active = TRUE
            GROUP BY tenant_id
        """)
    return {
        "status": "ok",
        "service": "forensic-ml-service",
        "active_model_tenants": len(rows),
        "model_counts": [
            {"tenant_id": str(r["tenant_id"]), "count": r["model_count"]} for r in rows
        ],
        "kafka_consumer": _kafka_consumer is not None,
        "scheduler_running": _scheduler.running if _scheduler else False,
    }


@app.post("/score", response_model=ScoreResponse, tags=["scoring"])
async def score_evidence(
    req: ScoreRequest,
    claims: dict = Depends(_resolve_token),
    scorer: AnomalyScorer = Depends(get_scorer),
):
    """
    Synchronous DRI scoring endpoint.
    The authenticated tenant must match req.tenant_id.
    """
    if claims['tenant_id'] != req.tenant_id:
        raise HTTPException(status_code=403, detail="Cannot score records for a different tenant")

    try:
        result = await scorer.score(req.tenant_id, req.evidence_record, req.framework)
    except Exception as exc:
        logger.error("Scoring failed", tenant_id=req.tenant_id, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Scoring error: {exc}")

    return ScoreResponse(
        dynamic_risk_index=result.dynamic_risk_index,
        risk_level=result.risk_level,
        vae_score=result.vae_score,
        isolation_score=result.isolation_score,
        benford_risk=result.benford_risk,
        scored_by=result.scored_by,
        top_risk_factors=[
            {"factor": f, "contribution": c} for f, c in result.top_risk_factors
        ],
    )


@app.get("/anomalies", response_model=list[AnomalyListItem], tags=["anomalies"])
async def list_anomalies(
    risk_level: Optional[str] = Query(None, pattern="^(low|medium|high|critical)$"),
    source_system: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    claims: dict = Depends(_resolve_token),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """List anomaly scores for the authenticated tenant with optional filters."""
    tenant_id = claims['tenant_id']
    offset = (page - 1) * page_size

    conditions = ["a.tenant_id = $1"]
    params: list = [UUID(tenant_id)]
    idx = 2

    if risk_level:
        conditions.append(f"a.risk_level = ${idx}")
        params.append(risk_level)
        idx += 1
    if source_system:
        conditions.append(f"e.source_system = ${idx}")
        params.append(source_system)
        idx += 1
    if date_from:
        conditions.append(f"a.scored_at >= ${idx}")
        params.append(datetime(date_from.year, date_from.month, date_from.day, tzinfo=timezone.utc))
        idx += 1
    if date_to:
        conditions.append(f"a.scored_at < ${idx}")
        params.append(datetime(date_to.year, date_to.month, date_to.day, tzinfo=timezone.utc))
        idx += 1

    where_clause = " AND ".join(conditions)
    query = f"""
        SELECT a.score_id, a.evidence_id, a.dynamic_risk_index, a.risk_level,
               e.source_system, a.scored_at, a.reviewed
        FROM anomaly_scores a
        JOIN evidence_records e ON e.evidence_id = a.evidence_id
        WHERE {where_clause}
        ORDER BY a.scored_at DESC
        LIMIT ${idx} OFFSET ${idx + 1}
    """
    params.extend([page_size, offset])

    async with pool.acquire() as conn:
        await conn.execute(f"SET LOCAL app.tenant_id = '{tenant_id}'")
        rows = await conn.fetch(query, *params)

    return [
        AnomalyListItem(
            score_id=str(r['score_id']),
            evidence_id=str(r['evidence_id']),
            dynamic_risk_index=float(r['dynamic_risk_index']),
            risk_level=r['risk_level'],
            source_system=r['source_system'],
            scored_at=r['scored_at'],
            reviewed=r['reviewed'],
        )
        for r in rows
    ]


@app.get("/anomalies/{score_id}", response_model=AnomalyDetail, tags=["anomalies"])
async def get_anomaly(
    score_id: UUID,
    claims: dict = Depends(_resolve_token),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Return full anomaly score detail including feature_vector."""
    tenant_id = claims['tenant_id']
    async with pool.acquire() as conn:
        await conn.execute(f"SET LOCAL app.tenant_id = '{tenant_id}'")
        row = await conn.fetchrow("""
            SELECT a.score_id, a.evidence_id, a.dynamic_risk_index, a.risk_level,
                   e.source_system, a.scored_at, a.reviewed,
                   a.vae_score, a.isolation_score, a.benford_mad,
                   a.scored_by, a.top_risk_factors, a.feature_vector,
                   a.false_positive, a.justification
            FROM anomaly_scores a
            JOIN evidence_records e ON e.evidence_id = a.evidence_id
            WHERE a.score_id = $1 AND a.tenant_id = $2
        """, score_id, UUID(tenant_id))

    if not row:
        raise HTTPException(status_code=404, detail="Anomaly score not found")

    top_rf = row['top_risk_factors']
    if isinstance(top_rf, str):
        top_rf = json.loads(top_rf)

    fv = row['feature_vector']
    if isinstance(fv, str):
        fv = json.loads(fv)

    return AnomalyDetail(
        score_id=str(row['score_id']),
        evidence_id=str(row['evidence_id']),
        dynamic_risk_index=float(row['dynamic_risk_index']),
        risk_level=row['risk_level'],
        source_system=row['source_system'],
        scored_at=row['scored_at'],
        reviewed=row['reviewed'],
        vae_score=float(row['vae_score'] or 0.5),
        isolation_score=float(row['isolation_score'] or 0.5),
        benford_risk=float(row['benford_mad'] or 0.0),
        scored_by=row['scored_by'] or 'weighted_sum',
        top_risk_factors=top_rf or [],
        feature_vector=fv,
        false_positive=row['false_positive'],
        justification=row['justification'],
    )


@app.patch("/anomalies/{score_id}/review", tags=["anomalies"])
async def review_anomaly(
    score_id: UUID,
    req: ReviewRequest,
    claims: dict = Depends(_require_role('auditor', 'admin')),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """
    Record HITL review decision.
    Marks the anomaly as reviewed and records false_positive flag + justification.
    Requires auditor or admin role.
    """
    tenant_id = claims['tenant_id']
    async with pool.acquire() as conn:
        await conn.execute(f"SET LOCAL app.tenant_id = '{tenant_id}'")
        result = await conn.execute("""
            UPDATE anomaly_scores
            SET reviewed = TRUE,
                false_positive = $1,
                justification = $2,
                reviewed_at = NOW(),
                reviewed_by = $3
            WHERE score_id = $4 AND tenant_id = $5
        """, req.false_positive, req.justification, UUID(claims['user_id']), score_id, UUID(tenant_id))

    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Anomaly score not found")

    # Invalidate model cache so next training cycle picks up the new label
    cache_keys = [k for k in _model_cache if k.startswith(tenant_id)]
    for key in cache_keys:
        del _model_cache[key]

    return {"status": "reviewed", "score_id": str(score_id), "false_positive": req.false_positive}


@app.post("/training/trigger", tags=["training"])
async def trigger_training(
    req: TriggerTrainingRequest,
    claims: dict = Depends(_require_role('admin')),
    pipeline: TenantTrainingPipeline = Depends(get_training_pipeline),
):
    """
    Trigger immediate model retraining for the authenticated tenant.
    Runs asynchronously — returns immediately, training runs in background.
    Requires admin role.
    """
    tenant_id = claims['tenant_id']

    async def _run():
        try:
            result = await pipeline.train_tenant(tenant_id, req.framework)
            logger.info("Manual training complete", tenant_id=tenant_id, result=result)
        except Exception as exc:
            logger.error("Manual training failed", tenant_id=tenant_id, error=str(exc))

    asyncio.create_task(_run())
    return {"status": "training_triggered", "tenant_id": tenant_id, "framework": req.framework}


@app.get("/training/status", tags=["training"])
async def training_status(
    claims: dict = Depends(_resolve_token),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Returns latest training job status per model type for the authenticated tenant."""
    tenant_id = claims['tenant_id']
    async with pool.acquire() as conn:
        await conn.execute(f"SET LOCAL app.tenant_id = '{tenant_id}'")
        rows = await conn.fetch("""
            SELECT model_type, framework, version, mlflow_run_id,
                   training_started_at, training_completed_at, is_active, deployed_at, retired_at
            FROM ml_model_registry
            WHERE tenant_id = $1
            ORDER BY training_completed_at DESC
        """, UUID(tenant_id))

    return [
        {
            "model_type": r["model_type"],
            "framework": r["framework"],
            "version": r["version"],
            "mlflow_run_id": r["mlflow_run_id"],
            "training_started_at": r["training_started_at"],
            "training_completed_at": r["training_completed_at"],
            "is_active": r["is_active"],
            "deployed_at": r["deployed_at"],
            "retired_at": r["retired_at"],
        }
        for r in rows
    ]


@app.get("/benford/{entity_id}", response_model=BenfordStats, tags=["benford"])
async def get_benford_stats(
    entity_id: str,
    claims: dict = Depends(_require_role('auditor', 'admin')),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """
    Return the most recent Benford's Law analysis for a specific entity.
    Requires auditor or admin role.
    """
    tenant_id = claims['tenant_id']
    async with pool.acquire() as conn:
        await conn.execute(f"SET LOCAL app.tenant_id = '{tenant_id}'")
        row = await conn.fetchrow("""
            SELECT entity_id, entity_type, transaction_count,
                   first_digit_distribution, expected_distribution,
                   mad, chi2_statistic, chi2_pvalue, conforming,
                   window_start, window_end
            FROM benford_entity_stats
            WHERE tenant_id = $1 AND entity_id = $2
            ORDER BY window_end DESC
            LIMIT 1
        """, UUID(tenant_id), entity_id)

    if not row:
        raise HTTPException(status_code=404, detail=f"No Benford stats found for entity '{entity_id}'")

    first_digit_dist = row['first_digit_distribution']
    if isinstance(first_digit_dist, str):
        first_digit_dist = json.loads(first_digit_dist)
    expected_dist = row['expected_distribution']
    if isinstance(expected_dist, str):
        expected_dist = json.loads(expected_dist)

    return BenfordStats(
        entity_id=row['entity_id'],
        entity_type=row['entity_type'],
        transaction_count=row['transaction_count'],
        first_digit_distribution=first_digit_dist,
        expected_distribution=expected_dist,
        mad=float(row['mad']),
        chi2_statistic=float(row['chi2_statistic']),
        chi2_pvalue=float(row['chi2_pvalue']),
        conforming=row['conforming'],
        window_start=row['window_start'],
        window_end=row['window_end'],
    )


@app.get("/risk-heatmap", response_model=list[RiskHeatmapEntry], tags=["heatmap"])
async def risk_heatmap(
    claims: dict = Depends(_resolve_token),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """
    Returns aggregated DRI scores for the tenant's top 50 highest-risk entities.
    Used by the Firm Mode dashboard heatmap widget.
    """
    tenant_id = claims['tenant_id']
    async with pool.acquire() as conn:
        await conn.execute(f"SET LOCAL app.tenant_id = '{tenant_id}'")
        rows = await conn.fetch("""
            SELECT
                e.source_system AS entity_id,
                'vendor' AS entity_type,
                AVG(a.dynamic_risk_index) AS avg_dri,
                MAX(a.dynamic_risk_index) AS max_dri,
                COUNT(*) FILTER (WHERE a.risk_level IN ('high','critical')) AS anomaly_count,
                MAX(a.scored_at) AS last_scored_at
            FROM anomaly_scores a
            JOIN evidence_records e ON e.evidence_id = a.evidence_id
            WHERE a.tenant_id = $1
              AND a.scored_at > NOW() - INTERVAL '30 days'
            GROUP BY e.source_system
            ORDER BY avg_dri DESC
            LIMIT 50
        """, UUID(tenant_id))

    return [
        RiskHeatmapEntry(
            entity_id=r['entity_id'],
            entity_type=r['entity_type'],
            avg_dri=float(r['avg_dri']),
            max_dri=float(r['max_dri']),
            anomaly_count=int(r['anomaly_count']),
            last_scored_at=r['last_scored_at'],
        )
        for r in rows
    ]
