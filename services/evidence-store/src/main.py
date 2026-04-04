from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

import httpx
import structlog
from aiokafka import AIOKafkaProducer
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwk, jwt

from .config import settings
from .db import (
    close_pool,
    create_pool,
    get_chain_state,
    get_evidence_by_id,
    get_records_for_chain_verify,
    insert_evidence_record,
    list_evidence_records,
)
from .hasher import compute_chain_hash, compute_payload_hash, verify_chain_segment
from .kafka_consumer import EvidenceKafkaConsumer
from .models import (
    ChainVerificationResult,
    EvidenceRecordCreate,
    EvidenceRecordResponse,
    WORMPromotionResult,
)
from .worm_client import WORMStorageClient
from .worm_promoter import WORMPromoter

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Application state container
# ---------------------------------------------------------------------------


class AppState:
    pool = None
    worm_client: WORMStorageClient | None = None
    kafka_consumer: EvidenceKafkaConsumer | None = None
    kafka_producer: AIOKafkaProducer | None = None
    worm_promoter: WORMPromoter | None = None
    _consumer_task: asyncio.Task | None = None
    _promoter_task: asyncio.Task | None = None
    jwks_cache: dict | None = None


state = AppState()

# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ---- Startup ----
    logger.info("evidence_store_starting")

    # Database pool
    state.pool = await create_pool()

    # WORM client
    state.worm_client = WORMStorageClient(
        endpoint=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        bucket=settings.minio_evidence_bucket,
        use_ssl=settings.minio_use_ssl,
    )

    # Kafka producer (shared by the consumer for normalized topic publishing)
    state.kafka_producer = AIOKafkaProducer(
        bootstrap_servers=settings.kafka_bootstrap_servers
    )
    await state.kafka_producer.start()

    # Kafka consumer
    state.kafka_consumer = EvidenceKafkaConsumer(
        pool=state.pool,
        worm_client=state.worm_client,
        publisher=state.kafka_producer,
    )
    await state.kafka_consumer.start()
    state._consumer_task = asyncio.create_task(
        state.kafka_consumer.consume_loop(),
        name="kafka-consume-loop",
    )

    # WORM promoter
    state.worm_promoter = WORMPromoter(
        pool=state.pool,
        worm_client=state.worm_client,
    )
    state._promoter_task = asyncio.create_task(
        state.worm_promoter.run_periodic(),
        name="worm-promoter-loop",
    )

    logger.info("evidence_store_ready", port=settings.server_port)

    yield

    # ---- Shutdown ----
    logger.info("evidence_store_shutting_down")

    if state._consumer_task:
        state._consumer_task.cancel()
        try:
            await state._consumer_task
        except asyncio.CancelledError:
            pass

    if state._promoter_task:
        state._promoter_task.cancel()
        try:
            await state._promoter_task
        except asyncio.CancelledError:
            pass

    if state.kafka_consumer:
        await state.kafka_consumer.stop()

    if state.kafka_producer:
        await state.kafka_producer.stop()

    if state.pool:
        await close_pool(state.pool)

    logger.info("evidence_store_stopped")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Evidence Store",
    version="1.0.0",
    description="Project Aegis 2026 — authoritative evidence record writer",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Auth / JWKS
# ---------------------------------------------------------------------------

bearer_scheme = HTTPBearer(auto_error=True)


async def _fetch_jwks() -> dict:
    """Fetch and cache JWKS from the auth service."""
    if state.jwks_cache is not None:
        return state.jwks_cache
    async with httpx.AsyncClient() as client:
        resp = await client.get(settings.auth_service_jwks_url, timeout=10)
        resp.raise_for_status()
        state.jwks_cache = resp.json()
    return state.jwks_cache


async def _decode_token(token: str) -> dict:
    """Decode and validate a JWT, returning the claims dict."""
    try:
        jwks_data = await _fetch_jwks()
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        # Find the matching key
        public_key = None
        for key_data in jwks_data.get("keys", []):
            if key_data.get("kid") == kid:
                public_key = jwk.construct(key_data)
                break
        if public_key is None and jwks_data.get("keys"):
            # Fall back to first key if kid not present
            public_key = jwk.construct(jwks_data["keys"][0])
        if public_key is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="No matching JWKS key found",
            )
        claims = jwt.decode(
            token,
            public_key.to_dict(),
            algorithms=["RS256", "ES256"],
        )
        return claims
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
        )


async def get_current_claims(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
) -> dict:
    return await _decode_token(credentials.credentials)


def require_role(*roles: str):
    """Dependency factory — raises 403 if the token does not have one of the given roles."""

    async def _check(
        claims: Annotated[dict, Depends(get_current_claims)],
    ) -> dict:
        token_roles = claims.get("roles", [])
        if not any(r in token_roles for r in roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required role(s): {roles}",
            )
        return claims

    return _check


def extract_tenant_id(claims: dict) -> str:
    tenant_id = claims.get("tenant_id") or claims.get("sub")
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="tenant_id not present in token",
        )
    return str(tenant_id)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _store_evidence_record(record: EvidenceRecordCreate) -> EvidenceRecordResponse:
    """
    Core write path shared by the HTTP POST and batch endpoints.
    Computes chain hash and sequence, inserts into DB, returns response model.
    """
    tenant_id = str(record.tenant_id)
    chain_state = await get_chain_state(state.pool, tenant_id)

    payload_hash_bytes = compute_payload_hash(record.canonical_payload)
    chain_hash_bytes = compute_chain_hash(chain_state.last_hash, payload_hash_bytes)
    chain_sequence = chain_state.next_seq

    await insert_evidence_record(
        state.pool,
        record,
        chain_hash=chain_hash_bytes,
        chain_sequence=chain_sequence,
        tenant_id=tenant_id,
    )

    return EvidenceRecordResponse(
        evidence_id=record.evidence_id,
        tenant_id=record.tenant_id,
        source_system=record.source_system,
        collected_at_utc=record.collected_at_utc,
        chain_sequence=chain_sequence,
        chain_hash=chain_hash_bytes.hex(),
        freshness_status="fresh",
        zk_proof_id=None,
        created_at=datetime.now(tz=timezone.utc),
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health", tags=["ops"])
async def health():
    return {"status": "ok", "service": "evidence-store"}


# ---- Single record write ---------------------------------------------------


@app.post(
    "/evidence",
    response_model=EvidenceRecordResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["evidence"],
    summary="Ingest a single evidence record (bypasses Kafka)",
)
async def create_evidence(
    record: EvidenceRecordCreate,
    claims: Annotated[dict, Depends(get_current_claims)],
):
    """
    Receives a single EvidenceRecordCreate, applies hash-chaining, and stores it.
    Called by services that bypass Kafka (e.g., direct API ingestion).
    """
    tenant_id = extract_tenant_id(claims)
    # Enforce that the record's tenant_id matches the token
    if str(record.tenant_id) != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="record.tenant_id does not match authenticated tenant",
        )
    return await _store_evidence_record(record)


# ---- Batch write -----------------------------------------------------------


@app.post(
    "/evidence/batch",
    response_model=list[EvidenceRecordResponse],
    status_code=status.HTTP_201_CREATED,
    tags=["evidence"],
    summary="Ingest a batch of up to 100 evidence records",
)
async def create_evidence_batch(
    records: list[EvidenceRecordCreate],
    claims: Annotated[dict, Depends(get_current_claims)],
):
    """
    Receives an ordered list of evidence records (max 100).
    Processes them sequentially to preserve chain integrity.
    """
    if len(records) > 100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Batch size must not exceed 100 records",
        )

    tenant_id = extract_tenant_id(claims)
    responses: list[EvidenceRecordResponse] = []

    for record in records:
        if str(record.tenant_id) != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"record {record.evidence_id}: tenant_id mismatch",
            )
        resp = await _store_evidence_record(record)
        responses.append(resp)

    return responses


# ---- Read single record ----------------------------------------------------


@app.get(
    "/evidence/{evidence_id}",
    response_model=EvidenceRecordResponse,
    tags=["evidence"],
    summary="Retrieve a single evidence record by ID",
)
async def get_evidence(
    evidence_id: UUID,
    claims: Annotated[dict, Depends(get_current_claims)],
):
    tenant_id = extract_tenant_id(claims)
    row = await get_evidence_by_id(state.pool, str(evidence_id), tenant_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    return EvidenceRecordResponse(
        evidence_id=row["evidence_id"],
        tenant_id=row["tenant_id"],
        source_system=row["source_system"],
        collected_at_utc=row["collected_at_utc"],
        chain_sequence=row["chain_sequence"],
        chain_hash=row["chain_hash"]
        if isinstance(row["chain_hash"], str)
        else row["chain_hash"].hex(),
        freshness_status=row["freshness_status"],
        zk_proof_id=row.get("zk_proof_id"),
        created_at=row["created_at"],
    )


# ---- List records ----------------------------------------------------------


@app.get(
    "/evidence",
    response_model=list[EvidenceRecordResponse],
    tags=["evidence"],
    summary="List evidence records for the authenticated tenant",
)
async def list_evidence(
    claims: Annotated[dict, Depends(get_current_claims)],
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    source_system: str | None = Query(default=None),
    collected_after: str | None = Query(default=None),
    collected_before: str | None = Query(default=None),
):
    tenant_id = extract_tenant_id(claims)
    rows = await list_evidence_records(
        state.pool,
        tenant_id=tenant_id,
        limit=limit,
        offset=offset,
        source_system=source_system,
        collected_after=collected_after,
        collected_before=collected_before,
    )

    def _row_to_response(row: dict) -> EvidenceRecordResponse:
        chain_hash = row["chain_hash"]
        if not isinstance(chain_hash, str):
            chain_hash = chain_hash.hex()
        return EvidenceRecordResponse(
            evidence_id=row["evidence_id"],
            tenant_id=row["tenant_id"],
            source_system=row["source_system"],
            collected_at_utc=row["collected_at_utc"],
            chain_sequence=row["chain_sequence"],
            chain_hash=chain_hash,
            freshness_status=row["freshness_status"],
            zk_proof_id=row.get("zk_proof_id"),
            created_at=row["created_at"],
        )

    return [_row_to_response(r) for r in rows]


# ---- Chain verification ----------------------------------------------------


@app.get(
    "/evidence/chain/verify",
    response_model=ChainVerificationResult,
    tags=["audit"],
    summary="Verify the hash-chain integrity for the authenticated tenant",
)
async def verify_chain(
    claims: Annotated[dict, Depends(require_role("auditor", "admin"))],
    limit: int = Query(default=500, ge=1, le=10000),
):
    tenant_id = extract_tenant_id(claims)
    records = await get_records_for_chain_verify(state.pool, tenant_id, limit=limit)
    intact, first_broken = verify_chain_segment(records)

    return ChainVerificationResult(
        tenant_id=UUID(tenant_id),
        records_checked=len(records),
        chain_intact=intact,
        first_broken_sequence=first_broken,
        checked_at=datetime.now(tz=timezone.utc),
    )


# ---- Manual WORM promotion -------------------------------------------------


@app.post(
    "/evidence/worm/promote",
    response_model=WORMPromotionResult,
    tags=["admin"],
    summary="Manually trigger WORM promotion for all pending records",
)
async def trigger_worm_promotion(
    claims: Annotated[dict, Depends(require_role("admin"))],
):
    if state.worm_promoter is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="WORM promoter not initialized",
        )
    result = await state.worm_promoter.promote_batch()
    return result
