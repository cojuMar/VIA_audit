"""
Dashboard BFF Service — Tri-Modal API

Routes:
  GET  /health

  --- Shared ---
  GET  /config/white-label          — Tenant white-label branding
  GET  /config/dashboard            — User dashboard layout/mode preference
  PUT  /config/dashboard            — Save layout/mode preference

  --- Firm Mode ---
  GET  /firm/portfolio              — Portfolio risk summary across all clients
  GET  /firm/risk-heatmap           — Risk heatmap data (framework × control)
  GET  /firm/clients                — List linked client tenants with scores
  GET  /firm/clients/{client_id}/summary — Single client risk summary

  --- SMB Mode ---
  GET  /smb/evidence-locker         — Paginated evidence records
  GET  /smb/audit-hub               — Open audit hub action items
  POST /smb/audit-hub               — Create audit hub item
  PUT  /smb/audit-hub/{item_id}     — Update audit hub item status

  --- Autonomous Mode ---
  GET  /autonomous/health-score     — Current health score
  GET  /autonomous/health-trend     — Historical health score trend
  GET  /autonomous/gauges           — All gauge values (for dashboard dials)
  GET  /autonomous/anomaly-feed     — Real-time anomaly feed (last 50)

  --- WebSocket ---
  WS   /ws                          — Real-time risk score updates (push)
"""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Optional, Set
import asyncpg
import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends, Header, Query
from pydantic import BaseModel, Field
from .config import settings
from .db import create_db_pool
from .health_scorer import HealthScorer

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ---------------------------------------------------------------------------
# App state
# ---------------------------------------------------------------------------

_db_pool: Optional[asyncpg.Pool] = None
_http_client: Optional[httpx.AsyncClient] = None
_scheduler: Optional[AsyncIOScheduler] = None
_ws_clients: Set[WebSocket] = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _db_pool, _http_client, _scheduler
    _db_pool = await create_db_pool()
    _http_client = httpx.AsyncClient(timeout=30.0)

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        _scheduled_health_score_refresh,
        'cron',
        minute='*/15',
        id='health_score_refresh',
        replace_existing=True,
    )
    _scheduler.start()

    logger.info("Dashboard service started")
    yield

    _scheduler.shutdown(wait=False)
    await _http_client.aclose()
    if _db_pool:
        await _db_pool.close()


app = FastAPI(title="Aegis Dashboard BFF", version="1.0.0", lifespan=lifespan)


def get_db() -> asyncpg.Pool:
    if _db_pool is None:
        raise HTTPException(503, "DB pool not ready")
    return _db_pool


def get_http() -> httpx.AsyncClient:
    if _http_client is None:
        raise HTTPException(503, "HTTP client not ready")
    return _http_client


async def _get_tenant_id(x_tenant_id: str = Header(..., alias="X-Tenant-ID")) -> str:
    return x_tenant_id


async def _get_user_id(x_user_id: str = Header(..., alias="X-User-ID")) -> str:
    return x_user_id


async def _require_bearer(authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing Bearer token")
    return authorization[7:]


# ---------------------------------------------------------------------------
# Scheduled health score refresh
# ---------------------------------------------------------------------------

async def _scheduled_health_score_refresh():
    """Refresh health scores for all active tenants (runs every 15 minutes)."""
    if _db_pool is None:
        return
    try:
        async with _db_pool.acquire() as conn:
            # Get all active tenants (platform-level query, no RLS)
            rows = await conn.fetch("SELECT tenant_id FROM tenants WHERE is_active = TRUE LIMIT 100")

        scorer = HealthScorer(_db_pool)
        for row in rows:
            for framework in ('soc2', 'iso27001', 'pci_dss'):
                try:
                    score = await scorer.compute_and_persist(str(row['tenant_id']), framework)
                    # Broadcast to WebSocket subscribers
                    await _broadcast_ws({
                        "type": "health_score_update",
                        "tenant_id": str(row['tenant_id']),
                        "framework": framework,
                        "overall_score": score.overall_score,
                    })
                except Exception as e:
                    logger.warning("Health score refresh failed for %s/%s: %s",
                                   row['tenant_id'], framework, e)
    except Exception as e:
        logger.error("Scheduled health score refresh failed: %s", e, exc_info=True)


async def _broadcast_ws(message: dict):
    """Broadcast a message to all connected WebSocket clients."""
    if not _ws_clients:
        return
    dead = set()
    payload = json.dumps(message, default=str)
    for ws in list(_ws_clients):
        try:
            await ws.send_text(payload)
        except Exception:
            dead.add(ws)
    _ws_clients.difference_update(dead)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok", "ws_clients": len(_ws_clients)}


# ---------------------------------------------------------------------------
# Config endpoints
# ---------------------------------------------------------------------------

@app.get("/config/white-label")
async def get_white_label(
    tenant_id: str = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
    _auth = Depends(_require_bearer),
):
    async with db.acquire() as conn:
        await conn.execute('SELECT set_config('app.tenant_id', $1, false)', tenant_id)
        row = await conn.fetchrow(
            "SELECT * FROM white_label_configs WHERE tenant_id = $1::uuid", tenant_id
        )
    if not row:
        # Return defaults
        return {
            "firm_name": "Aegis Compliance",
            "primary_color": "#1a56db",
            "secondary_color": "#7e3af2",
            "accent_color": "#0e9f6e",
            "font_family": "Inter",
        }
    return dict(row)


class DashboardConfigUpdate(BaseModel):
    mode: Optional[str] = Field(None, pattern=r'^(firm|smb|autonomous)$')
    layout_json: Optional[dict] = None
    pinned_controls: Optional[list] = None
    default_framework: Optional[str] = None
    date_range_days: Optional[int] = Field(None, ge=7, le=365)


@app.get("/config/dashboard")
async def get_dashboard_config(
    tenant_id: str = Depends(_get_tenant_id),
    user_id: str = Depends(_get_user_id),
    db: asyncpg.Pool = Depends(get_db),
    _auth = Depends(_require_bearer),
):
    async with db.acquire() as conn:
        await conn.execute('SELECT set_config('app.tenant_id', $1, false)', tenant_id)
        row = await conn.fetchrow(
            "SELECT * FROM dashboard_configs WHERE tenant_id=$1::uuid AND user_id=$2::uuid",
            tenant_id, user_id
        )
    if not row:
        return {"mode": "smb", "default_framework": "soc2", "date_range_days": 30}
    return dict(row)


@app.put("/config/dashboard")
async def update_dashboard_config(
    body: DashboardConfigUpdate,
    tenant_id: str = Depends(_get_tenant_id),
    user_id: str = Depends(_get_user_id),
    db: asyncpg.Pool = Depends(get_db),
    _auth = Depends(_require_bearer),
):
    import json as _json
    fields = body.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(400, "No fields to update")

    set_clauses = []
    params = [tenant_id, user_id]
    idx = 3
    for key, value in fields.items():
        if key == 'layout_json':
            set_clauses.append(f"{key} = ${idx}::jsonb")
            params.append(_json.dumps(value))
        elif key == 'pinned_controls':
            set_clauses.append(f"{key} = ${idx}::text[]")
            params.append(value)
        else:
            set_clauses.append(f"{key} = ${idx}")
            params.append(value)
        idx += 1

    async with db.acquire() as conn:
        await conn.execute('SELECT set_config('app.tenant_id', $1, false)', tenant_id)
        await conn.execute(f"""
            INSERT INTO dashboard_configs (tenant_id, user_id, {', '.join(fields.keys())})
            VALUES ($1::uuid, $2::uuid, {', '.join(f'${i}' for i in range(3, idx))})
            ON CONFLICT (tenant_id, user_id) DO UPDATE
            SET {', '.join(set_clauses)}, updated_at = NOW()
        """, *params)
    return {"status": "saved"}


# ---------------------------------------------------------------------------
# Firm Mode endpoints
# ---------------------------------------------------------------------------

@app.get("/firm/clients")
async def list_firm_clients(
    tenant_id: str = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
    _auth = Depends(_require_bearer),
):
    """List all clients linked to this firm tenant."""
    async with db.acquire() as conn:
        rows = await conn.fetch("""
            SELECT fcl.client_tenant_id::text, fcl.client_alias, fcl.engagement_code,
                   t.tenant_name,
                   hs.overall_score, hs.open_issues, hs.critical_issues
            FROM firm_client_links fcl
            JOIN tenants t ON t.tenant_id = fcl.client_tenant_id
            LEFT JOIN LATERAL (
                SELECT overall_score, open_issues, critical_issues
                FROM health_score_snapshots
                WHERE tenant_id = fcl.client_tenant_id AND framework = 'soc2'
                ORDER BY snapshot_time DESC LIMIT 1
            ) hs ON TRUE
            WHERE fcl.firm_tenant_id = $1::uuid AND fcl.is_active = TRUE
            ORDER BY hs.overall_score ASC NULLS LAST
        """, tenant_id)
    return [dict(r) for r in rows]


@app.get("/firm/risk-heatmap")
async def get_risk_heatmap(
    tenant_id: str = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
    http: httpx.AsyncClient = Depends(get_http),
    _auth = Depends(_require_bearer),
    framework: str = Query("soc2"),
    days: int = Query(30, ge=1, le=365),
):
    """
    Risk heatmap data: for each linked client, get their anomaly risk by category.
    Returns a matrix suitable for rendering a heatmap: rows=clients, cols=risk categories.

    For Firm Mode: aggregates across all linked clients.
    For single-tenant: aggregates across control categories.
    """
    async with db.acquire() as conn:
        # Get linked client tenant IDs
        client_rows = await conn.fetch("""
            SELECT client_tenant_id::text, COALESCE(client_alias, tenant_name) AS label
            FROM firm_client_links fcl
            JOIN tenants t ON t.tenant_id = fcl.client_tenant_id
            WHERE fcl.firm_tenant_id = $1::uuid AND fcl.is_active = TRUE
        """, tenant_id)

    # If no clients linked, return own tenant heatmap
    tenant_ids = [r['client_tenant_id'] for r in client_rows] or [tenant_id]
    labels = {r['client_tenant_id']: r['label'] for r in client_rows}
    labels[tenant_id] = "Self"

    heatmap_rows = []
    for tid in tenant_ids:
        async with db.acquire() as conn:
            await conn.execute('SELECT set_config('app.tenant_id', $1, false)', tid)
            rows = await conn.fetch("""
                SELECT
                    COALESCE(er.canonical_payload->>'entity_type', 'unknown') AS category,
                    AVG(ans.dri_score) AS avg_risk,
                    COUNT(*) AS count
                FROM anomaly_scores ans
                JOIN evidence_records er ON er.evidence_id = ans.evidence_record_id
                WHERE ans.tenant_id = $1::uuid
                  AND ans.scored_at > NOW() - ($2 || ' days')::INTERVAL
                GROUP BY category
                ORDER BY avg_risk DESC
            """, tid, str(days))
        heatmap_rows.append({
            "tenant_id": tid,
            "label": labels.get(tid, tid[:8]),
            "categories": [dict(r) for r in rows],
        })

    return {"framework": framework, "days": days, "data": heatmap_rows}


@app.get("/firm/portfolio")
async def get_portfolio_summary(
    tenant_id: str = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
    _auth = Depends(_require_bearer),
    framework: str = Query("soc2"),
):
    """Portfolio-level risk summary for Firm Mode dashboard."""
    async with db.acquire() as conn:
        rows = await conn.fetch("""
            SELECT
                fcl.client_tenant_id::text,
                COALESCE(fcl.client_alias, t.tenant_name) AS client_name,
                hs.overall_score,
                hs.open_issues,
                hs.critical_issues,
                hs.snapshot_time
            FROM firm_client_links fcl
            JOIN tenants t ON t.tenant_id = fcl.client_tenant_id
            LEFT JOIN LATERAL (
                SELECT overall_score, open_issues, critical_issues, snapshot_time
                FROM health_score_snapshots
                WHERE tenant_id = fcl.client_tenant_id AND framework = $2
                ORDER BY snapshot_time DESC LIMIT 1
            ) hs ON TRUE
            WHERE fcl.firm_tenant_id = $1::uuid AND fcl.is_active = TRUE
        """, tenant_id, framework)

    clients = [dict(r) for r in rows]
    scores = [c['overall_score'] for c in clients if c['overall_score'] is not None]

    return {
        "framework": framework,
        "client_count": len(clients),
        "avg_health_score": round(sum(scores) / len(scores), 3) if scores else None,
        "clients_at_risk": sum(1 for c in clients if (c['overall_score'] or 1.0) < 0.6),
        "critical_issues_total": sum(c['critical_issues'] or 0 for c in clients),
        "clients": clients,
    }


# ---------------------------------------------------------------------------
# SMB Mode endpoints
# ---------------------------------------------------------------------------

@app.get("/smb/evidence-locker")
async def get_evidence_locker(
    tenant_id: str = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
    _auth = Depends(_require_bearer),
    event_type: Optional[str] = Query(None),
    source_system: Optional[str] = Query(None),
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Evidence Locker: paginated list of evidence records for SMB Mode."""
    conditions = ["tenant_id = $1::uuid", "ingested_at > NOW() - ($2 || ' days')::INTERVAL"]
    params: list = [tenant_id, str(days)]
    idx = 3

    if event_type:
        conditions.append(f"canonical_payload->>'event_type' = ${idx}")
        params.append(event_type)
        idx += 1
    if source_system:
        conditions.append(f"source_system = ${idx}")
        params.append(source_system)
        idx += 1

    params.extend([limit, offset])
    where = " AND ".join(conditions)

    async with db.acquire() as conn:
        await conn.execute('SELECT set_config('app.tenant_id', $1, false)', tenant_id)
        rows = await conn.fetch(f"""
            SELECT
                evidence_id,
                source_system,
                canonical_payload->>'event_type' AS event_type,
                canonical_payload->>'entity_type' AS entity_type,
                canonical_payload->>'outcome' AS outcome,
                canonical_payload->>'timestamp_utc' AS event_timestamp,
                ingested_at,
                chain_sequence
            FROM evidence_records
            WHERE {where}
            ORDER BY ingested_at DESC
            LIMIT ${idx} OFFSET ${idx+1}
        """, *params)

        total = await conn.fetchval(f"""
            SELECT COUNT(*) FROM evidence_records WHERE {where}
        """, *params[:-2])

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "records": [dict(r) for r in rows],
    }


class AuditHubItemCreate(BaseModel):
    framework: str
    control_id: str
    title: str
    description: Optional[str] = None
    priority: str = Field("medium", pattern=r'^(low|medium|high|critical)$')
    due_date: Optional[str] = None
    assigned_to: Optional[str] = None


@app.get("/smb/audit-hub")
async def get_audit_hub(
    tenant_id: str = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
    _auth = Depends(_require_bearer),
    status: str = Query("open"),
    framework: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """Audit Hub: action items for SMB Mode."""
    conditions = ["tenant_id = $1::uuid", f"status = $2"]
    params: list = [tenant_id, status]
    idx = 3
    if framework:
        conditions.append(f"framework = ${idx}")
        params.append(framework)
        idx += 1
    params.append(limit)

    where = " AND ".join(conditions)
    async with db.acquire() as conn:
        await conn.execute('SELECT set_config('app.tenant_id', $1, false)', tenant_id)
        rows = await conn.fetch(f"""
            SELECT * FROM audit_hub_items
            WHERE {where}
            ORDER BY priority DESC, due_date ASC NULLS LAST, created_at ASC
            LIMIT ${idx}
        """, *params)
    return [dict(r) for r in rows]


@app.post("/smb/audit-hub", status_code=201)
async def create_audit_hub_item(
    body: AuditHubItemCreate,
    tenant_id: str = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
    _auth = Depends(_require_bearer),
):
    async with db.acquire() as conn:
        await conn.execute('SELECT set_config('app.tenant_id', $1, false)', tenant_id)
        item_id = await conn.fetchval("""
            INSERT INTO audit_hub_items
                (tenant_id, framework, control_id, title, description, priority, due_date, assigned_to)
            VALUES ($1::uuid, $2, $3, $4, $5, $6, $7::date, $8::uuid)
            RETURNING item_id::text
        """,
            tenant_id, body.framework, body.control_id, body.title,
            body.description, body.priority, body.due_date, body.assigned_to,
        )
    return {"item_id": item_id}


@app.put("/smb/audit-hub/{item_id}")
async def update_audit_hub_item(
    item_id: str,
    status: str = Query(..., pattern=r'^(open|in_progress|resolved|waived)$'),
    tenant_id: str = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
    _auth = Depends(_require_bearer),
):
    async with db.acquire() as conn:
        await conn.execute('SELECT set_config('app.tenant_id', $1, false)', tenant_id)
        result = await conn.execute("""
            UPDATE audit_hub_items SET status=$1, updated_at=NOW()
            WHERE item_id=$2::uuid AND tenant_id=$3::uuid
        """, status, item_id, tenant_id)
    if result == "UPDATE 0":
        raise HTTPException(404, "Item not found")
    return {"status": "updated"}


# ---------------------------------------------------------------------------
# Autonomous Mode endpoints
# ---------------------------------------------------------------------------

@app.get("/autonomous/health-score")
async def get_health_score(
    tenant_id: str = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
    _auth = Depends(_require_bearer),
    framework: str = Query("soc2"),
):
    """Current health score for Autonomous Mode gauges."""
    async with db.acquire() as conn:
        await conn.execute('SELECT set_config('app.tenant_id', $1, false)', tenant_id)
        row = await conn.fetchrow("""
            SELECT * FROM health_score_snapshots
            WHERE tenant_id = $1::uuid AND framework = $2
            ORDER BY snapshot_time DESC LIMIT 1
        """, tenant_id, framework)

    if not row:
        # Compute on demand for first request
        scorer = HealthScorer(db)
        score = await scorer.compute_and_persist(tenant_id, framework)
        return {
            "overall_score": score.overall_score,
            "dimensions": {
                "access_control": score.access_control,
                "data_integrity": score.data_integrity,
                "anomaly_rate": score.anomaly_rate,
                "evidence_freshness": score.evidence_freshness,
                "narrative_quality": score.narrative_quality,
            },
            "open_issues": score.open_issues,
            "critical_issues": score.critical_issues,
        }

    return {
        "overall_score": float(row['overall_score']),
        "snapshot_time": row['snapshot_time'].isoformat(),
        "dimensions": {
            "access_control": float(row['access_control'] or 0),
            "data_integrity": float(row['data_integrity'] or 0),
            "anomaly_rate": float(row['anomaly_rate'] or 0),
            "evidence_freshness": float(row['evidence_freshness'] or 0),
            "narrative_quality": float(row['narrative_quality'] or 0),
        },
        "open_issues": row['open_issues'],
        "critical_issues": row['critical_issues'],
    }


@app.get("/autonomous/health-trend")
async def get_health_trend(
    tenant_id: str = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
    _auth = Depends(_require_bearer),
    framework: str = Query("soc2"),
    days: int = Query(30, ge=7, le=365),
):
    scorer = HealthScorer(db)
    trend = await scorer.get_trend(tenant_id, framework, days)
    return {"framework": framework, "days": days, "data": trend}


@app.get("/autonomous/gauges")
async def get_gauges(
    tenant_id: str = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
    _auth = Depends(_require_bearer),
    framework: str = Query("soc2"),
):
    """All gauge values for Autonomous Mode dashboard dials."""
    async with db.acquire() as conn:
        await conn.execute('SELECT set_config('app.tenant_id', $1, false)', tenant_id)
        hs_row = await conn.fetchrow("""
            SELECT * FROM health_score_snapshots
            WHERE tenant_id = $1::uuid AND framework = $2
            ORDER BY snapshot_time DESC LIMIT 1
        """, tenant_id, framework)

        # Connector health
        connector_row = await conn.fetchrow("""
            SELECT
                COUNT(*) FILTER (WHERE circuit_breaker_state = 'closed') AS healthy,
                COUNT(*) AS total
            FROM connector_registry
            WHERE tenant_id = $1::uuid AND is_active = TRUE
        """, tenant_id)

    connector_health = (
        connector_row['healthy'] / connector_row['total']
        if connector_row['total'] > 0 else 1.0
    )

    return {
        "gauges": [
            {
                "id": "overall_health",
                "label": "Overall Health",
                "value": float(hs_row['overall_score']) if hs_row else 0.75,
                "unit": "score",
                "thresholds": {"warning": 0.6, "critical": 0.4},
            },
            {
                "id": "evidence_freshness",
                "label": "Evidence Freshness",
                "value": float(hs_row['evidence_freshness']) if hs_row else 0.8,
                "unit": "score",
                "thresholds": {"warning": 0.7, "critical": 0.5},
            },
            {
                "id": "anomaly_rate",
                "label": "Anomaly Health",
                "value": float(hs_row['anomaly_rate']) if hs_row else 0.9,
                "unit": "score",
                "thresholds": {"warning": 0.7, "critical": 0.5},
            },
            {
                "id": "connector_health",
                "label": "Connector Health",
                "value": round(float(connector_health), 3),
                "unit": "score",
                "thresholds": {"warning": 0.8, "critical": 0.6},
            },
            {
                "id": "data_integrity",
                "label": "Data Integrity",
                "value": float(hs_row['data_integrity']) if hs_row else 1.0,
                "unit": "score",
                "thresholds": {"warning": 0.95, "critical": 0.9},
            },
        ]
    }


@app.get("/autonomous/anomaly-feed")
async def get_anomaly_feed(
    tenant_id: str = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
    _auth = Depends(_require_bearer),
    limit: int = Query(50, ge=1, le=200),
):
    async with db.acquire() as conn:
        await conn.execute('SELECT set_config('app.tenant_id', $1, false)', tenant_id)
        rows = await conn.fetch("""
            SELECT
                ans.anomaly_id, ans.dri_score, ans.risk_level,
                ans.vae_score, ans.isolation_score, ans.benford_risk,
                ans.scored_at, ans.false_positive,
                er.canonical_payload->>'event_type' AS event_type,
                er.canonical_payload->>'entity_type' AS entity_type,
                er.source_system
            FROM anomaly_scores ans
            JOIN evidence_records er ON er.evidence_id = ans.evidence_record_id
            WHERE ans.tenant_id = $1::uuid
            ORDER BY ans.scored_at DESC, ans.dri_score DESC
            LIMIT $2
        """, tenant_id, limit)
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Real-time risk score push channel.

    Clients connect, receive a heartbeat every 30s, and get pushed
    health_score_update events whenever scores are refreshed.
    """
    await websocket.accept()
    _ws_clients.add(websocket)
    try:
        await websocket.send_text(json.dumps({"type": "connected", "heartbeat_interval": settings.ws_heartbeat_interval}))

        while True:
            # Send heartbeat and wait for pong (or timeout)
            try:
                await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=settings.ws_heartbeat_interval * 2
                )
            except asyncio.TimeoutError:
                await websocket.send_text(json.dumps({"type": "ping"}))
    except WebSocketDisconnect:
        pass
    finally:
        _ws_clients.discard(websocket)
