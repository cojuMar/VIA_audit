"""
Post-Quantum Crypto Service — FastAPI application

Routes:
  POST /kyber/keypair          — Generate Kyber768 keypair; store public key in DB
  POST /kyber/encapsulate      — Encapsulate shared secret with a public key
  POST /kyber/decapsulate      — Decapsulate shared secret with secret key
  POST /dilithium/keypair      — Generate Dilithium3 keypair; store public key in DB
  POST /dilithium/sign         — Sign a message with secret key
  POST /dilithium/verify       — Verify a Dilithium3 signature
  GET  /keys/{tenant_id}       — List active PQ public keys for tenant
  GET  /health                 — Service + algorithm availability check
"""

import base64
import logging
from contextlib import asynccontextmanager
from typing import List, Optional

import asyncpg
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from .config import settings
from .dilithium_signer import DilithiumSigner
from .kyber_kem import KyberKEM

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ---------------------------------------------------------------------------
# Attempt to import oqs for health check — tolerate absence
# ---------------------------------------------------------------------------
try:
    import oqs as _oqs
    _OQS_AVAILABLE = True
except ImportError:
    _oqs = None  # type: ignore[assignment]
    _OQS_AVAILABLE = False

# ---------------------------------------------------------------------------
# Singletons
# ---------------------------------------------------------------------------

_db_pool: Optional[asyncpg.Pool] = None
_kyber = KyberKEM()
_dilithium = DilithiumSigner()


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _db_pool
    _db_pool = await asyncpg.create_pool(settings.database_url, min_size=2, max_size=10)
    logger.info("PQ crypto service started on port %d", settings.pq_service_port)
    yield
    if _db_pool:
        await _db_pool.close()


app = FastAPI(
    title="Aegis Post-Quantum Crypto Service",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_db() -> asyncpg.Pool:
    if _db_pool is None:
        raise HTTPException(503, "Database pool not initialized")
    return _db_pool


def _get_tenant(x_tenant_id: str = Header(..., alias="X-Tenant-ID")) -> str:
    return x_tenant_id


def _b64_decode(value: str, field_name: str) -> bytes:
    """Decode standard or URL-safe base64; raise 400 on invalid input."""
    try:
        # Normalise URL-safe variant
        value = value.replace("-", "+").replace("_", "/")
        # Add padding if missing
        padding = 4 - len(value) % 4
        if padding != 4:
            value += "=" * padding
        return base64.b64decode(value)
    except Exception:
        raise HTTPException(400, f"Invalid base64 in field '{field_name}'")


def _b64_encode(data: bytes) -> str:
    return base64.b64encode(data).decode()


async def _store_public_key(
    pool: asyncpg.Pool,
    tenant_id: str,
    algorithm: str,
    public_key: bytes,
    fingerprint: bytes,
) -> str:
    """Persist a public key to pq_public_keys; return the generated key_id."""
    async with pool.acquire() as conn, conn.transaction():
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant_id)
            key_id = await conn.fetchval(
                """
                INSERT INTO pq_public_keys (
                    tenant_id,
                    algorithm,
                    public_key,
                    fingerprint,
                    active
                ) VALUES (
                    $1::uuid,
                    $2,
                    $3,
                    $4,
                    TRUE
                )
                RETURNING key_id::text
                """,
                tenant_id,
                algorithm,
                public_key,
                fingerprint,
            )
    return key_id


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class KyberEncapsulateRequest(BaseModel):
    public_key_b64: str


class KyberEncapsulateResponse(BaseModel):
    ciphertext_b64: str
    shared_secret_b64: str


class KyberDecapsulateRequest(BaseModel):
    ciphertext_b64: str
    secret_key_b64: str


class KyberDecapsulateResponse(BaseModel):
    shared_secret_b64: str


class KyberKeypairResponse(BaseModel):
    key_id: str
    public_key_b64: str
    secret_key_b64: str
    fingerprint_b64: str
    algorithm: str


class DilithiumKeypairResponse(BaseModel):
    key_id: str
    public_key_b64: str
    secret_key_b64: str
    fingerprint_b64: str
    algorithm: str


class DilithiumSignRequest(BaseModel):
    message_b64: str
    secret_key_b64: str


class DilithiumSignResponse(BaseModel):
    signature_b64: str


class DilithiumVerifyRequest(BaseModel):
    message_b64: str
    signature_b64: str
    public_key_b64: str


class DilithiumVerifyResponse(BaseModel):
    valid: bool


class PublicKeyRecord(BaseModel):
    key_id: str
    algorithm: str
    fingerprint_b64: str
    active: bool
    created_at: str


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    algorithms = []
    status = "ok"

    if _OQS_AVAILABLE:
        kem_ok = "Kyber768" in _oqs.get_enabled_kem_mechanisms()
        sig_ok = "Dilithium3" in _oqs.get_enabled_sig_mechanisms()

        if kem_ok:
            algorithms.append("Kyber768")
        if sig_ok:
            algorithms.append("Dilithium3")

        if not kem_ok or not sig_ok:
            status = "degraded"
    else:
        status = "degraded"

    return {"status": status, "algorithms": algorithms}


# ---------------------------------------------------------------------------
# Kyber routes
# ---------------------------------------------------------------------------

@app.post("/kyber/keypair", response_model=KyberKeypairResponse)
async def kyber_generate_keypair(
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
):
    """Generate a Kyber768 keypair.  Public key is stored in the DB; secret key
    is returned to the caller and NEVER persisted."""
    try:
        keypair = _kyber.generate_keypair()
    except ValueError as e:
        raise HTTPException(503, str(e))

    pool = _get_db()
    key_id = await _store_public_key(
        pool=pool,
        tenant_id=x_tenant_id,
        algorithm=keypair.algorithm,
        public_key=keypair.public_key,
        fingerprint=keypair.fingerprint,
    )

    return KyberKeypairResponse(
        key_id=key_id,
        public_key_b64=_b64_encode(keypair.public_key),
        secret_key_b64=_b64_encode(keypair.secret_key),
        fingerprint_b64=_b64_encode(keypair.fingerprint),
        algorithm=keypair.algorithm,
    )


@app.post("/kyber/encapsulate", response_model=KyberEncapsulateResponse)
async def kyber_encapsulate(
    body: KyberEncapsulateRequest,
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
):
    """Encapsulate a shared secret with the provided public key."""
    public_key = _b64_decode(body.public_key_b64, "public_key_b64")

    try:
        result = _kyber.encapsulate(public_key)
    except ValueError as e:
        raise HTTPException(503, str(e))

    return KyberEncapsulateResponse(
        ciphertext_b64=_b64_encode(result.ciphertext),
        shared_secret_b64=_b64_encode(result.shared_secret),
    )


@app.post("/kyber/decapsulate", response_model=KyberDecapsulateResponse)
async def kyber_decapsulate(
    body: KyberDecapsulateRequest,
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
):
    """Recover the shared secret from a ciphertext using the caller's secret key."""
    ciphertext = _b64_decode(body.ciphertext_b64, "ciphertext_b64")
    secret_key = _b64_decode(body.secret_key_b64, "secret_key_b64")

    try:
        shared_secret = _kyber.decapsulate(ciphertext, secret_key)
    except ValueError as e:
        raise HTTPException(503, str(e))

    return KyberDecapsulateResponse(shared_secret_b64=_b64_encode(shared_secret))


# ---------------------------------------------------------------------------
# Dilithium routes
# ---------------------------------------------------------------------------

@app.post("/dilithium/keypair", response_model=DilithiumKeypairResponse)
async def dilithium_generate_keypair(
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
):
    """Generate a Dilithium3 keypair.  Public key is stored in the DB; secret key
    is returned to the caller and NEVER persisted."""
    try:
        keypair = _dilithium.generate_keypair()
    except ValueError as e:
        raise HTTPException(503, str(e))

    pool = _get_db()
    key_id = await _store_public_key(
        pool=pool,
        tenant_id=x_tenant_id,
        algorithm=keypair.algorithm,
        public_key=keypair.public_key,
        fingerprint=keypair.fingerprint,
    )

    return DilithiumKeypairResponse(
        key_id=key_id,
        public_key_b64=_b64_encode(keypair.public_key),
        secret_key_b64=_b64_encode(keypair.secret_key),
        fingerprint_b64=_b64_encode(keypair.fingerprint),
        algorithm=keypair.algorithm,
    )


@app.post("/dilithium/sign", response_model=DilithiumSignResponse)
async def dilithium_sign(
    body: DilithiumSignRequest,
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
):
    """Sign a message with the provided secret key."""
    message = _b64_decode(body.message_b64, "message_b64")
    secret_key = _b64_decode(body.secret_key_b64, "secret_key_b64")

    try:
        signature = _dilithium.sign(message, secret_key)
    except ValueError as e:
        raise HTTPException(503, str(e))

    return DilithiumSignResponse(signature_b64=_b64_encode(signature))


@app.post("/dilithium/verify", response_model=DilithiumVerifyResponse)
async def dilithium_verify(
    body: DilithiumVerifyRequest,
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
):
    """Verify a Dilithium3 signature.  Returns {valid: bool}."""
    message = _b64_decode(body.message_b64, "message_b64")
    signature = _b64_decode(body.signature_b64, "signature_b64")
    public_key = _b64_decode(body.public_key_b64, "public_key_b64")

    valid = _dilithium.verify(message, signature, public_key)
    return DilithiumVerifyResponse(valid=valid)


# ---------------------------------------------------------------------------
# Key listing
# ---------------------------------------------------------------------------

@app.get("/keys/{tenant_id}", response_model=List[PublicKeyRecord])
async def list_keys(
    tenant_id: str,
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
):
    """List active PQ public keys for a tenant.

    The path tenant_id must match the header tenant_id — prevents one tenant
    from enumerating another tenant's keys at the API layer (RLS enforces it
    at the DB layer too).
    """
    if tenant_id != x_tenant_id:
        raise HTTPException(403, "tenant_id in path does not match X-Tenant-ID header")

    pool = _get_db()
    async with pool.acquire() as conn, conn.transaction():
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant_id)
            rows = await conn.fetch(
                """
                SELECT
                    key_id::text,
                    algorithm,
                    fingerprint,
                    active,
                    created_at
                FROM pq_public_keys
                WHERE tenant_id = $1::uuid AND active = TRUE
                ORDER BY created_at DESC
                """,
                tenant_id,
            )

    return [
        PublicKeyRecord(
            key_id=row["key_id"],
            algorithm=row["algorithm"],
            fingerprint_b64=_b64_encode(row["fingerprint"]),
            active=row["active"],
            created_at=row["created_at"].isoformat(),
        )
        for row in rows
    ]
