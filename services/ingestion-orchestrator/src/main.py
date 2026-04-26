"""
FastAPI application — control plane for the ingestion orchestrator.

Endpoints:
  GET  /health                               — liveness / readiness probe
  GET  /connectors                           — list active connectors (tenant-scoped)
  POST /connectors                           — register a new connector
  DELETE /connectors/{connector_id}          — soft-delete and unschedule
  GET  /connectors/{connector_id}/runs       — paginated run history
  POST /connectors/{connector_id}/trigger    — manually trigger an immediate poll
  GET  /connectors/{connector_id}/watermark  — current ingestion cursor

Authentication:
  All routes (except /health) require a Bearer JWT issued by the auth-service.
  JWTs are verified against the JWKS endpoint configured in settings.
  Admin-only routes additionally check the 'admin' role claim.

Port: 3004 (configurable via settings.server_port)
"""

import json
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg
import httpx
import structlog
from fastapi import Depends, FastAPI, HTTPException, Query, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from .config import settings
from .connectors.registry import get_connector_class
from .kafka_publisher import KafkaPublisher
from .scheduler import PollScheduler
from .vault_credentials import ConnectorVaultLoader

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Application state (injected via lifespan)
# ---------------------------------------------------------------------------

_pool: asyncpg.Pool | None = None
_kafka: KafkaPublisher | None = None
_scheduler: PollScheduler | None = None
_jwks_cache: dict | None = None


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool, _kafka, _scheduler

    # Startup
    _pool = await asyncpg.create_pool(settings.database_url, min_size=2, max_size=10)
    _kafka = KafkaPublisher()
    await _kafka.start()
    _scheduler = PollScheduler(kafka=_kafka)
    await _scheduler.start(_pool)
    logger.info("ingestion_orchestrator: started")

    yield

    # Shutdown
    if _scheduler:
        await _scheduler.stop()
    if _kafka:
        await _kafka.stop()
    if _pool:
        await _pool.close()
    logger.info("ingestion_orchestrator: stopped")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Aegis Ingestion Orchestrator",
    version="1.0.0",
    description="Polls 400+ integrations on an hourly cadence, normalizes "
                "evidence to a canonical schema, and publishes to Kafka.",
    lifespan=lifespan,
)

_bearer_scheme = HTTPBearer()


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

async def _get_jwks() -> dict:
    global _jwks_cache
    if _jwks_cache is None:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(settings.auth_service_jwks_url)
            resp.raise_for_status()
            _jwks_cache = resp.json()
    return _jwks_cache


async def _verify_token(
    credentials: HTTPAuthorizationCredentials = Security(_bearer_scheme),
) -> dict:
    """Verify a Bearer JWT and return the decoded claims."""
    token = credentials.credentials
    try:
        jwks = await _get_jwks()
        # jose will select the correct key via the 'kid' header claim
        claims = jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
        return claims
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
        ) from exc


async def _require_admin(claims: dict = Depends(_verify_token)) -> dict:
    """Dependency that additionally enforces the 'admin' role."""
    roles = claims.get("roles", [])
    if "admin" not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
    return claims


def _tenant_id_from_claims(claims: dict) -> UUID:
    tid = claims.get("tenant_id")
    if not tid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="tenant_id missing from token claims",
        )
    return UUID(str(tid))


def _get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialised")
    return _pool


def _get_kafka() -> KafkaPublisher:
    if _kafka is None:
        raise RuntimeError("KafkaPublisher not initialised")
    return _kafka


def _get_scheduler() -> PollScheduler:
    if _scheduler is None:
        raise RuntimeError("PollScheduler not initialised")
    return _scheduler


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ConnectorRegistrationRequest(BaseModel):
    connector_type: str
    config: dict[str, Any] = {}
    polling_interval_seconds: int = settings.default_polling_interval_seconds
    vault_path: str  # path in Vault where credentials live


class ConnectorResponse(BaseModel):
    connector_id: UUID
    tenant_id: UUID
    connector_type: str
    config: dict[str, Any]
    polling_interval_seconds: int
    vault_path: str
    is_active: bool
    created_at: datetime


class IngestionRunResponse(BaseModel):
    run_id: UUID
    connector_id: UUID
    tenant_id: UUID
    status: str
    started_at: datetime
    finished_at: datetime | None
    records_published: int | None
    bytes_ingested: int | None
    error_message: str | None


class WatermarkResponse(BaseModel):
    connector_id: UUID
    tenant_id: UUID
    cursor_data: dict | None
    watermark_to: datetime | None
    last_chain_sequence: int | None
    updated_at: datetime | None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health", tags=["ops"])
async def health():
    """
    Liveness and readiness probe.  Checks DB, Kafka, and Vault connectivity.
    Returns 200 if all checks pass, 503 otherwise.
    """
    checks: dict[str, str] = {}
    healthy = True

    # DB check
    try:
        pool = _get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc}"
        healthy = False

    # Kafka check
    try:
        kafka = _get_kafka()
        if kafka._producer is None:
            raise RuntimeError("producer not started")
        checks["kafka"] = "ok"
    except Exception as exc:
        checks["kafka"] = f"error: {exc}"
        healthy = False

    # Vault check
    try:
        loader = ConnectorVaultLoader()
        # hvac client is sync; a lightweight health check
        import hvac
        client = hvac.Client(url=settings.vault_addr, token=settings.vault_token)
        client.sys.read_health_status()
        checks["vault"] = "ok"
    except Exception as exc:
        checks["vault"] = f"error: {exc}"
        healthy = False

    if not healthy:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=checks,
        )
    return {"status": "ok", "checks": checks}


@app.get("/connectors", response_model=list[ConnectorResponse], tags=["connectors"])
async def list_connectors(
    claims: dict = Depends(_verify_token),
    pool: asyncpg.Pool = Depends(_get_pool),
):
    """List active connectors for the authenticated tenant."""
    tenant_id = _tenant_id_from_claims(claims)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT connector_id, tenant_id, connector_type, config,
                   polling_interval_seconds, vault_path, is_active, created_at
            FROM connectors
            WHERE tenant_id = $1 AND is_active = TRUE
            ORDER BY created_at DESC
            """,
            tenant_id,
        )
    return [ConnectorResponse(**dict(r)) for r in rows]


@app.post(
    "/connectors",
    response_model=ConnectorResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["connectors"],
)
async def register_connector(
    body: ConnectorRegistrationRequest,
    claims: dict = Depends(_require_admin),
    pool: asyncpg.Pool = Depends(_get_pool),
    scheduler: PollScheduler = Depends(_get_scheduler),
):
    """
    Register a new connector.

    Steps:
    1. Validate connector_type is known.
    2. Load credentials from Vault.
    3. Instantiate connector and call test_connection().
    4. Insert row into connectors table.
    5. Schedule polling.
    """
    tenant_id = _tenant_id_from_claims(claims)

    # 1. Validate connector_type
    try:
        connector_cls = get_connector_class(body.connector_type)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    # 2. Load credentials from Vault
    vault_loader = ConnectorVaultLoader()
    try:
        credentials = await vault_loader.load_credentials(body.vault_path)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to load credentials from Vault: {exc}",
        ) from exc

    # 3. Test connection
    connector = connector_cls(
        tenant_id=str(tenant_id),
        connector_config=body.config,
        credentials=credentials,
    )
    try:
        ok = await connector.test_connection()
    except Exception as exc:
        ok = False
        logger.warning("register_connector: test_connection raised", error=str(exc))

    if not ok:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="test_connection failed — check credentials and connectivity",
        )

    # 4. Insert into DB
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO connectors
              (tenant_id, connector_type, config, polling_interval_seconds,
               vault_path, is_active)
            VALUES ($1, $2, $3, $4, $5, TRUE)
            RETURNING connector_id, tenant_id, connector_type, config,
                      polling_interval_seconds, vault_path, is_active, created_at
            """,
            tenant_id,
            body.connector_type,
            json.dumps(body.config),
            body.polling_interval_seconds,
            body.vault_path,
        )

    connector_row = dict(row)
    # config column is stored as jsonb / text; normalise for scheduler
    if isinstance(connector_row.get("config"), str):
        connector_row["config"] = json.loads(connector_row["config"])

    # 5. Schedule
    scheduler.add_connector(connector_row)

    logger.info(
        "register_connector: registered",
        connector_id=str(connector_row["connector_id"]),
        connector_type=body.connector_type,
    )
    return ConnectorResponse(**connector_row)


@app.delete("/connectors/{connector_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["connectors"])
async def deactivate_connector(
    connector_id: UUID,
    claims: dict = Depends(_require_admin),
    pool: asyncpg.Pool = Depends(_get_pool),
    scheduler: PollScheduler = Depends(_get_scheduler),
):
    """Soft-delete a connector and remove its scheduled job."""
    tenant_id = _tenant_id_from_claims(claims)

    async with pool.acquire() as conn:
        updated = await conn.fetchval(
            """
            UPDATE connectors
            SET is_active = FALSE
            WHERE connector_id = $1 AND tenant_id = $2
            RETURNING connector_id
            """,
            connector_id,
            tenant_id,
        )

    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connector not found",
        )

    scheduler.remove_connector(str(connector_id))
    return  # 204 No Content


@app.get(
    "/connectors/{connector_id}/runs",
    response_model=list[IngestionRunResponse],
    tags=["connectors"],
)
async def get_connector_runs(
    connector_id: UUID,
    claims: dict = Depends(_verify_token),
    pool: asyncpg.Pool = Depends(_get_pool),
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Paginated ingestion run history for a connector."""
    tenant_id = _tenant_id_from_claims(claims)

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT run_id, connector_id, tenant_id, status,
                   started_at, finished_at, records_published,
                   bytes_ingested, error_message
            FROM ingestion_runs
            WHERE connector_id = $1 AND tenant_id = $2
            ORDER BY started_at DESC
            LIMIT $3 OFFSET $4
            """,
            connector_id,
            tenant_id,
            limit,
            offset,
        )

    return [IngestionRunResponse(**dict(r)) for r in rows]


@app.post(
    "/connectors/{connector_id}/trigger",
    status_code=status.HTTP_202_ACCEPTED,
    tags=["connectors"],
)
async def trigger_poll(
    connector_id: UUID,
    claims: dict = Depends(_require_admin),
    pool: asyncpg.Pool = Depends(_get_pool),
    scheduler: PollScheduler = Depends(_get_scheduler),
):
    """Manually trigger an immediate poll for a connector (admin only)."""
    tenant_id = _tenant_id_from_claims(claims)

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT connector_id, tenant_id, connector_type, config,
                   polling_interval_seconds, vault_path
            FROM connectors
            WHERE connector_id = $1 AND tenant_id = $2 AND is_active = TRUE
            """,
            connector_id,
            tenant_id,
        )

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active connector not found",
        )

    connector_row = dict(row)
    if isinstance(connector_row.get("config"), str):
        connector_row["config"] = json.loads(connector_row["config"])

    # Fire-and-forget: run poll in a background task so the HTTP call returns
    # immediately with 202 Accepted
    import asyncio as _asyncio
    _asyncio.create_task(
        scheduler._execute_poll(
            connector_id=str(connector_id),
            tenant_id=str(tenant_id),
            connector_type=connector_row["connector_type"],
            connector_row=connector_row,
        )
    )

    return {"accepted": True, "connector_id": str(connector_id)}


@app.get(
    "/connectors/{connector_id}/watermark",
    response_model=WatermarkResponse,
    tags=["connectors"],
)
async def get_watermark(
    connector_id: UUID,
    claims: dict = Depends(_verify_token),
    pool: asyncpg.Pool = Depends(_get_pool),
):
    """Return the current ingestion cursor / watermark for a connector."""
    tenant_id = _tenant_id_from_claims(claims)

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT connector_id, tenant_id, cursor_data, watermark_to,
                   last_chain_sequence, updated_at
            FROM ingestion_watermarks
            WHERE connector_id = $1 AND tenant_id = $2
            """,
            connector_id,
            tenant_id,
        )

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No watermark found — connector may not have run yet",
        )

    wm = dict(row)
    raw_cursor = wm.get("cursor_data")
    if isinstance(raw_cursor, str):
        wm["cursor_data"] = json.loads(raw_cursor)

    return WatermarkResponse(**wm)
