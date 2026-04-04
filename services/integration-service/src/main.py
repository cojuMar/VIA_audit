import json
import logging
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from minio import Minio
from minio.error import S3Error

from src.config import settings
from src.connector_registry import ConnectorRegistry
from src.db import close_pool, get_pool, tenant_conn
from src.encryption import TokenEncryption
from src.integration_manager import IntegrationManager
from src.models import (
    FieldMappingUpdate,
    IntegrationCreate,
    IntegrationUpdate,
    OAuthTokenCreate,
    SyncRequest,
    WebhookPayload,
)
from src.scheduler import IntegrationScheduler
from src.sync_engine import SyncEngine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Global singletons
# ---------------------------------------------------------------------------
encryption = TokenEncryption(settings.encryption_key)
sync_engine = SyncEngine(settings, encryption)
scheduler = IntegrationScheduler(settings)

registry = ConnectorRegistry()
manager = IntegrationManager()


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    pool = await get_pool()

    # Ensure MinIO bucket exists
    try:
        minio_client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=False,
        )
        if not minio_client.bucket_exists(settings.minio_bucket_integrations):
            minio_client.make_bucket(settings.minio_bucket_integrations)
            logger.info("Created MinIO bucket: %s", settings.minio_bucket_integrations)
    except Exception as exc:
        logger.warning("MinIO setup failed (non-fatal): %s", exc)

    scheduler.start(pool, sync_engine)

    yield

    # Shutdown
    scheduler.stop()
    await close_pool()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Integration Service",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------
async def get_db():
    return await get_pool()


async def get_tenant_id(x_tenant_id: Annotated[str | None, Header()] = None) -> str:
    if not x_tenant_id:
        raise HTTPException(status_code=401, detail="X-Tenant-ID header is required")
    return x_tenant_id


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/health")
async def health():
    return {"status": "ok", "service": "integration-service"}


# ---------------------------------------------------------------------------
# Connector catalog
# ---------------------------------------------------------------------------
@app.get("/connectors")
async def list_connectors(pool=Depends(get_db)):
    connectors = await registry.list_connectors(pool)
    return {"connectors": connectors, "total": len(connectors)}


@app.get("/connectors/{connector_key}")
async def get_connector(connector_key: str, pool=Depends(get_db)):
    connector = await registry.get_connector(pool, connector_key)
    if connector is None:
        raise HTTPException(status_code=404, detail="Connector not found")
    return connector


@app.get("/connectors/{connector_key}/field-templates/{data_type}")
async def get_field_templates(connector_key: str, data_type: str, pool=Depends(get_db)):
    templates = await registry.get_field_mapping_templates(pool, connector_key, data_type)
    return {"connector_key": connector_key, "data_type": data_type, "templates": templates}


# ---------------------------------------------------------------------------
# Integrations
# ---------------------------------------------------------------------------
@app.get("/integrations")
async def list_integrations(
    status: str | None = Query(default=None),
    pool=Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    integrations = await manager.list(pool, tenant_id, status=status)
    return {"integrations": integrations, "total": len(integrations)}


@app.post("/integrations", status_code=201)
async def create_integration(
    body: IntegrationCreate,
    pool=Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    try:
        integration = await manager.create(pool, tenant_id, body, encryption)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return integration


@app.get("/integrations/{integration_id}")
async def get_integration(
    integration_id: str,
    pool=Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    integration = await manager.get(pool, tenant_id, integration_id)
    if integration is None:
        raise HTTPException(status_code=404, detail="Integration not found")
    return integration


@app.put("/integrations/{integration_id}")
async def update_integration(
    integration_id: str,
    body: IntegrationUpdate,
    pool=Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    try:
        integration = await manager.update(pool, tenant_id, integration_id, body, encryption)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return integration


@app.post("/integrations/{integration_id}/pause")
async def pause_integration(
    integration_id: str,
    pool=Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    try:
        integration = await manager.pause(pool, tenant_id, integration_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return integration


@app.post("/integrations/{integration_id}/resume")
async def resume_integration(
    integration_id: str,
    pool=Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    try:
        integration = await manager.resume(pool, tenant_id, integration_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return integration


@app.delete("/integrations/{integration_id}", status_code=204)
async def delete_integration(
    integration_id: str,
    pool=Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    try:
        await manager.delete(pool, tenant_id, integration_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return None


@app.post("/integrations/{integration_id}/oauth-token", status_code=201)
async def store_oauth_token(
    integration_id: str,
    body: OAuthTokenCreate,
    pool=Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    try:
        token = await manager.store_oauth_token(
            pool, tenant_id, integration_id, body, encryption
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"message": "OAuth token stored successfully", "integration_id": integration_id}


@app.post("/integrations/{integration_id}/sync")
async def trigger_sync(
    integration_id: str,
    body: SyncRequest = SyncRequest(),
    pool=Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    try:
        result = await sync_engine.run_sync(pool, tenant_id, integration_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.exception("Sync failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Sync failed: {exc!s}")
    return result


@app.get("/integrations/{integration_id}/sync-logs")
async def get_sync_logs(
    integration_id: str,
    limit: int = Query(default=20, ge=1, le=200),
    pool=Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    async with tenant_conn(pool, tenant_id) as conn:
        rows = await conn.fetch(
            """
            SELECT isl.*
            FROM integration_sync_logs isl
            JOIN tenant_integrations ti ON ti.id = isl.integration_id
            WHERE isl.integration_id = $1
              AND ti.tenant_id = $2
            ORDER BY isl.started_at DESC
            LIMIT $3
            """,
            integration_id,
            tenant_id,
            limit,
        )
    logs = []
    for row in rows:
        d = dict(row)
        if isinstance(d.get("data_types_synced"), str):
            d["data_types_synced"] = json.loads(d["data_types_synced"])
        logs.append(d)
    return {"sync_logs": logs, "total": len(logs)}


@app.get("/integrations/{integration_id}/records")
async def get_records(
    integration_id: str,
    data_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    pool=Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    async with tenant_conn(pool, tenant_id) as conn:
        if data_type:
            rows = await conn.fetch(
                """
                SELECT ir.*
                FROM integration_records ir
                JOIN tenant_integrations ti ON ti.id = ir.integration_id
                WHERE ir.integration_id = $1
                  AND ti.tenant_id = $2
                  AND ir.data_type = $3
                ORDER BY ir.synced_at DESC
                LIMIT $4
                """,
                integration_id,
                tenant_id,
                data_type,
                limit,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT ir.*
                FROM integration_records ir
                JOIN tenant_integrations ti ON ti.id = ir.integration_id
                WHERE ir.integration_id = $1
                  AND ti.tenant_id = $2
                ORDER BY ir.synced_at DESC
                LIMIT $3
                """,
                integration_id,
                tenant_id,
                limit,
            )
    records = []
    for row in rows:
        d = dict(row)
        for field in ("raw_data", "normalized_data"):
            if isinstance(d.get(field), str):
                d[field] = json.loads(d[field])
        records.append(d)
    return {"records": records, "total": len(records)}


@app.get("/integrations/{integration_id}/stats")
async def get_stats(
    integration_id: str,
    pool=Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    try:
        stats = await manager.get_sync_stats(pool, tenant_id, integration_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return stats


@app.get("/integrations/{integration_id}/field-mappings")
async def get_field_mappings(
    integration_id: str,
    pool=Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    integration = await manager.get(pool, tenant_id, integration_id)
    if integration is None:
        raise HTTPException(status_code=404, detail="Integration not found")
    return {
        "integration_id": integration_id,
        "field_mappings": integration.get("field_mappings", {}),
    }


@app.put("/integrations/{integration_id}/field-mappings")
async def update_field_mappings(
    integration_id: str,
    body: FieldMappingUpdate,
    pool=Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    integration = await manager.get(pool, tenant_id, integration_id)
    if integration is None:
        raise HTTPException(status_code=404, detail="Integration not found")

    existing_mappings: dict = integration.get("field_mappings") or {}

    if body.auto_populate_from_template and body.mappings:
        # Use provided mappings directly (already derived from template)
        new_mappings_for_type = body.mappings
    else:
        new_mappings_for_type = body.mappings

    existing_mappings[body.data_type] = new_mappings_for_type

    update_data = IntegrationUpdate(field_mappings=existing_mappings)
    updated = await manager.update(pool, tenant_id, integration_id, update_data, encryption)
    return {
        "integration_id": integration_id,
        "data_type": body.data_type,
        "field_mappings": updated.get("field_mappings", {}),
    }


# ---------------------------------------------------------------------------
# Webhooks — public endpoints (no X-Tenant-ID required; resolved from integration)
# ---------------------------------------------------------------------------
@app.post("/webhooks/{webhook_id}")
async def receive_webhook(
    webhook_id: str,
    request: Request,
    pool=Depends(get_db),
):
    """webhook_id is the integration_id. Tenant is resolved from the DB."""
    try:
        body_bytes = await request.body()
        try:
            payload = await request.json()
        except Exception:
            payload = {"raw": body_bytes.decode(errors="replace")}
    except Exception:
        payload = {}

    headers = dict(request.headers)

    # Resolve tenant from integration
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT tenant_id FROM tenant_integrations WHERE id = $1 AND status != 'disabled'",
            webhook_id,
        )

    if row is None:
        raise HTTPException(status_code=404, detail="Webhook endpoint not found")

    tenant_id = str(row["tenant_id"])
    event_type = payload.get("event_type", "generic")
    source_event_id = payload.get("source_event_id") or payload.get("id")

    try:
        result = await sync_engine.process_webhook(
            pool=pool,
            tenant_id=tenant_id,
            integration_id=webhook_id,
            event_type=event_type,
            payload=payload,
            headers=headers,
            source_event_id=str(source_event_id) if source_event_id else None,
        )
    except Exception as exc:
        logger.exception("Webhook processing error: %s", exc)
        raise HTTPException(status_code=500, detail="Webhook processing failed")

    return result


@app.get("/webhooks/{webhook_id}/events")
async def get_webhook_events(
    webhook_id: str,
    limit: int = Query(default=50, ge=1, le=500),
    pool=Depends(get_db),
):
    """Return recent webhook events for an integration (public endpoint)."""
    # Verify the integration exists (no tenant check — public endpoint)
    async with pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT id FROM tenant_integrations WHERE id = $1 AND status != 'disabled'",
            webhook_id,
        )
        if not exists:
            raise HTTPException(status_code=404, detail="Webhook endpoint not found")

        tenant_id_row = await conn.fetchrow(
            "SELECT tenant_id FROM tenant_integrations WHERE id = $1",
            webhook_id,
        )
        tenant_id = str(tenant_id_row["tenant_id"])

    async with tenant_conn(pool, tenant_id) as conn:
        rows = await conn.fetch(
            """
            SELECT *
            FROM webhook_events
            WHERE integration_id = $1
            ORDER BY received_at DESC
            LIMIT $2
            """,
            webhook_id,
            limit,
        )

    events = []
    for row in rows:
        d = dict(row)
        for field in ("payload", "headers"):
            if isinstance(d.get(field), str):
                d[field] = json.loads(d[field])
        events.append(d)

    return {"events": events, "total": len(events)}


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@app.get("/dashboard")
async def get_dashboard(
    pool=Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    summary = await manager.get_integration_summary(pool, tenant_id)
    return summary
