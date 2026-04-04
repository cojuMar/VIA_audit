from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import Optional

import asyncpg
import httpx
import structlog
from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from .config import settings
from .db import close_pool, create_pool
from .models import FirmClientLink, TenantCreate, TenantResponse, TenantTier
from .provisioner import TenantProvisioner

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# App state
# ---------------------------------------------------------------------------

class _AppState:
    db_pool: asyncpg.Pool
    provisioner: TenantProvisioner
    jwks_cache: dict
    jwks_fetched_at: float = 0.0


_state = _AppState()

JWKS_CACHE_TTL_SECONDS = 3600


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    _state.db_pool = await create_pool()
    _state.provisioner = TenantProvisioner(_state.db_pool)
    _state.jwks_cache = {}
    logger.info("tenant_registry_started")
    yield
    await close_pool(_state.db_pool)
    logger.info("tenant_registry_stopped")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="Tenant Registry", version="1.0.0", lifespan=lifespan)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=True)


# ---------------------------------------------------------------------------
# JWKS / JWT helpers — identical pattern to pam-broker
# ---------------------------------------------------------------------------

class TokenClaims:
    def __init__(self, sub: str, tenant_id: str, role: str, **_):
        self.sub = sub
        self.tenant_id = tenant_id
        self.role = role


async def _get_jwks() -> dict:
    now = time.monotonic()
    if _state.jwks_cache and (now - _state.jwks_fetched_at) < JWKS_CACHE_TTL_SECONDS:
        return _state.jwks_cache

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(settings.auth_service_jwks_url)
        resp.raise_for_status()
        _state.jwks_cache = resp.json()
        _state.jwks_fetched_at = now
        return _state.jwks_cache


async def get_current_user(token: str = Depends(oauth2_scheme)) -> TokenClaims:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        jwks = await _get_jwks()
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")

        signing_key = None
        for key in jwks.get("keys", []):
            if key.get("kid") == kid or kid is None:
                signing_key = key
                break

        if signing_key is None:
            raise credentials_exception

        payload = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            options={"verify_exp": True},
        )
        return TokenClaims(**payload)
    except (JWTError, KeyError, TypeError, ValueError):
        raise credentials_exception


def require_roles(*roles: str):
    async def _check(claims: TokenClaims = Depends(get_current_user)) -> TokenClaims:
        if claims.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{claims.role}' is not permitted for this operation",
            )
        return claims
    return _check


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------

@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(PermissionError)
async def permission_error_handler(request: Request, exc: PermissionError):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=403, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception):
    from fastapi.responses import JSONResponse
    logger.error("unhandled_exception", exc=str(exc))
    return JSONResponse(status_code=500, content={"detail": "An internal error occurred"})


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.post(
    "/tenants",
    response_model=TenantResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_tenant(
    body: TenantCreate,
    claims: TokenClaims = Depends(require_roles("admin")),
):
    tenant = await _state.provisioner.provision_tenant(body)
    return tenant


@app.get("/tenants/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: str,
    claims: TokenClaims = Depends(get_current_user),
):
    # Admins can see any tenant; others can only see their own
    if claims.role != "admin" and claims.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this tenant",
        )

    tenant = await _state.provisioner.get_tenant(tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


@app.get("/tenants", response_model=list[TenantResponse])
async def list_tenants(
    tier: Optional[TenantTier] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    claims: TokenClaims = Depends(require_roles("admin")),
):
    return await _state.provisioner.list_tenants(tier=tier, limit=limit, offset=offset)


@app.delete("/tenants/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tenant(
    tenant_id: str,
    claims: TokenClaims = Depends(require_roles("admin")),
):
    existing = await _state.provisioner.get_tenant(tenant_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    await _state.provisioner.deprovision_tenant(tenant_id)


@app.post("/tenants/firm-bridge")
async def create_firm_bridge(
    body: FirmClientLink,
    claims: TokenClaims = Depends(require_roles("firm_partner")),
):
    # Ensure firm_tenant_id matches the caller's own tenant
    if claims.tenant_id != body.firm_tenant_id and claims.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="firm_tenant_id must match caller's tenant",
        )

    await _state.provisioner.create_firm_bridge_view(
        body.firm_tenant_id, body.client_tenant_ids
    )

    view_schema = f"firm_bridge_{body.firm_tenant_id.replace('-', '_')}"
    return {
        "view_schema": view_schema,
        "message": (
            f"Firm bridge view created for firm '{body.firm_tenant_id}' "
            f"linking {len(body.client_tenant_ids)} client tenant(s)"
        ),
    }


@app.get("/health")
async def health():
    db_ok = False
    try:
        async with _state.db_pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        db_ok = True
    except Exception:
        pass

    return {
        "status": "healthy" if db_ok else "degraded",
        "database": "ok" if db_ok else "unreachable",
    }
