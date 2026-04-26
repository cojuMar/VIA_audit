from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Optional

import asyncpg
import httpx
import structlog
from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from .access_policy import AccessPolicy
from .audit_logger import AuditLogger
from .config import settings
from .db import close_pool, create_pool
from .models import (
    AccessRequestCreate,
    AccessRequestResponse,
    PAMAuditEntry,
    RequestStatus,
    ResourceType,
    TokenClaims,
)
from .vault_client import VaultClient

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# App state container
# ---------------------------------------------------------------------------

class _AppState:
    db_pool: asyncpg.Pool
    vault_client: VaultClient
    audit_logger: AuditLogger
    jwks_cache: dict
    jwks_fetched_at: float = 0.0


_state = _AppState()
_policy = AccessPolicy()

# In-memory pending break-glass requests: request_id -> {requester_id, approvers: list, data: dict}
_pending_break_glass: dict[str, dict] = {}

# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    _state.db_pool = await create_pool()
    _state.vault_client = VaultClient(
        vault_addr=settings.vault_addr, vault_token=settings.vault_token
    )
    _state.audit_logger = AuditLogger(_state.db_pool)
    _state.jwks_cache = {}
    logger.info("pam_broker_started")
    yield
    await close_pool(_state.db_pool)
    logger.info("pam_broker_stopped")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="PAM Broker", version="1.0.0", lifespan=lifespan)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=True)

# ---------------------------------------------------------------------------
# JWKS / JWT helpers
# ---------------------------------------------------------------------------

JWKS_CACHE_TTL_SECONDS = 3600  # 1 hour


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
        # Decode header to get kid
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")

        # Find matching key
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
        claims = TokenClaims(**payload)
        return claims
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
    return _json_error(400, str(exc))


@app.exception_handler(PermissionError)
async def permission_error_handler(request: Request, exc: PermissionError):
    return _json_error(403, str(exc))


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception):
    logger.error("unhandled_exception", exc=str(exc))
    return _json_error(500, "An internal error occurred")


def _json_error(status_code: int, detail: str):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=status_code, content={"detail": detail})


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.post(
    "/access/request",
    response_model=AccessRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_access_request(
    body: AccessRequestCreate,
    request: Request,
    claims: TokenClaims = Depends(get_current_user),
):
    request_id = str(uuid.uuid4())
    ip_address = request.client.host if request.client else None

    # 1. Validate role permission and cap TTL
    approved_ttl = _policy.validate_and_cap_ttl(
        body.resource_type, body.requested_duration_seconds, claims.role
    )

    # 2. Break-glass path
    if body.resource_type == ResourceType.BREAK_GLASS:
        if not _policy.is_break_glass_permitted(claims.role):
            raise PermissionError("Only 'admin' or 'firm_partner' may initiate break-glass")

        _pending_break_glass[request_id] = {
            "requester_id": claims.sub,
            "requester_role": claims.role,
            "tenant_id": claims.tenant_id,
            "approvers": [],
            "ttl_seconds": approved_ttl,
            "resource_type": body.resource_type,
            "justification": body.justification,
            "itsm_ticket_id": body.itsm_ticket_id,
        }

        await _state.audit_logger.log(
            PAMAuditEntry(
                request_id=request_id,
                actor_user_id=claims.sub,
                actor_role=claims.role,
                action="break_glass_initiated",
                resource=body.resource_type.value,
                ip_address=ip_address,
            )
        )

        return AccessRequestResponse(
            request_id=request_id,
            status=RequestStatus.PENDING,
        )

    # 3. Normal path — issue Vault credentials
    db_vault_role, pki_role = _policy.get_vault_roles(body.resource_type)
    credential: dict = {}
    vault_lease_id: Optional[str] = None

    if db_vault_role is not None:
        if body.resource_type == ResourceType.DATABASE_INFRA:
            db_cred = await _state.vault_client.issue_infra_credential(
                claims.tenant_id, claims.sub, approved_ttl
            )
        else:
            db_cred = await _state.vault_client.issue_auditor_credential(
                claims.tenant_id, claims.sub, approved_ttl
            )
        credential["db"] = db_cred
        vault_lease_id = db_cred.get("lease_id")

    if pki_role is not None:
        if body.resource_type == ResourceType.DATABASE_INFRA:
            cert = await _state.vault_client.issue_infra_certificate(
                f"svc-{claims.sub}", approved_ttl
            )
        else:
            cert = await _state.vault_client.issue_auditor_certificate(
                claims.sub, approved_ttl
            )
        credential["cert"] = cert

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=approved_ttl)

    await _state.audit_logger.log(
        PAMAuditEntry(
            request_id=request_id,
            actor_user_id=claims.sub,
            actor_role=claims.role,
            action="access_granted",
            resource=body.resource_type.value,
            ip_address=ip_address,
        )
    )

    return AccessRequestResponse(
        request_id=request_id,
        status=RequestStatus.APPROVED,
        approved_duration_seconds=approved_ttl,
        expires_at=expires_at,
        credential=credential if credential else None,
        vault_lease_id=vault_lease_id,
    )


@app.post(
    "/access/request/{request_id}/approve",
    response_model=AccessRequestResponse,
)
async def approve_break_glass(
    request_id: str,
    request: Request,
    claims: TokenClaims = Depends(require_roles("admin")),
):
    pending = _pending_break_glass.get(request_id)
    if pending is None:
        raise HTTPException(status_code=404, detail="Request not found or already processed")

    if claims.sub == pending["requester_id"]:
        raise PermissionError("Approver cannot be the same as the requester")

    if claims.sub in pending["approvers"]:
        raise HTTPException(status_code=409, detail="Already approved by this user")

    pending["approvers"].append(claims.sub)

    ip_address = request.client.host if request.client else None

    await _state.audit_logger.log(
        PAMAuditEntry(
            request_id=request_id,
            actor_user_id=claims.sub,
            actor_role=claims.role,
            action="break_glass_approval",
            resource=ResourceType.BREAK_GLASS.value,
            ip_address=ip_address,
        )
    )

    required = settings.break_glass_required_approvers
    if len(pending["approvers"]) < required:
        return AccessRequestResponse(
            request_id=request_id,
            status=RequestStatus.PENDING,
        )

    # Dual approval satisfied — issue credentials
    ttl = pending["ttl_seconds"]
    db_cred = await _state.vault_client.issue_infra_credential(
        pending["tenant_id"], pending["requester_id"], ttl
    )
    cert = await _state.vault_client.issue_infra_certificate(
        f"bg-{pending['requester_id']}", ttl
    )

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)

    await _state.audit_logger.log(
        PAMAuditEntry(
            request_id=request_id,
            actor_user_id=claims.sub,
            actor_role=claims.role,
            action="break_glass_approved_issued",
            resource=ResourceType.BREAK_GLASS.value,
            ip_address=ip_address,
        )
    )

    del _pending_break_glass[request_id]

    return AccessRequestResponse(
        request_id=request_id,
        status=RequestStatus.APPROVED,
        approved_duration_seconds=ttl,
        expires_at=expires_at,
        credential={"db": db_cred, "cert": cert},
        vault_lease_id=db_cred.get("lease_id"),
    )


@app.post(
    "/access/request/{request_id}/revoke",
    response_model=AccessRequestResponse,
)
async def revoke_access(
    request_id: str,
    request: Request,
    vault_lease_id: str = Query(..., description="Vault lease ID to revoke"),
    claims: TokenClaims = Depends(require_roles("admin")),
):
    ip_address = request.client.host if request.client else None

    await _state.vault_client.revoke_lease(vault_lease_id)

    await _state.audit_logger.log(
        PAMAuditEntry(
            request_id=request_id,
            actor_user_id=claims.sub,
            actor_role=claims.role,
            action="access_revoked",
            resource=vault_lease_id,
            ip_address=ip_address,
        )
    )

    return AccessRequestResponse(
        request_id=request_id,
        status=RequestStatus.REVOKED,
        vault_lease_id=vault_lease_id,
    )


@app.get("/access/requests", response_model=list[AccessRequestResponse])
async def list_access_requests(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    claims: TokenClaims = Depends(get_current_user),
):
    """
    Returns the caller's own access requests, or all tenant requests for admins.
    Backed by pam_audit_log for the audit trail; returns a shaped response.
    """
    async with _state.db_pool.acquire() as conn:
        if claims.role == "admin":
            rows = await conn.fetch(
                """
                SELECT DISTINCT ON (request_id)
                    request_id, action, recorded_at
                FROM pam_audit_log
                ORDER BY request_id, chain_sequence DESC
                LIMIT $1 OFFSET $2
                """,
                limit,
                offset,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT DISTINCT ON (request_id)
                    request_id, action, recorded_at
                FROM pam_audit_log
                WHERE actor_user_id = $1
                ORDER BY request_id, chain_sequence DESC
                LIMIT $2 OFFSET $3
                """,
                claims.sub,
                limit,
                offset,
            )

    def _status_from_action(action: str) -> RequestStatus:
        mapping = {
            "access_granted": RequestStatus.APPROVED,
            "access_revoked": RequestStatus.REVOKED,
            "break_glass_initiated": RequestStatus.PENDING,
            "break_glass_approved_issued": RequestStatus.APPROVED,
        }
        return mapping.get(action, RequestStatus.PENDING)

    return [
        AccessRequestResponse(
            request_id=row["request_id"],
            status=_status_from_action(row["action"]),
        )
        for row in rows
    ]


@app.get("/access/audit-log", response_model=list[PAMAuditEntry])
async def get_audit_log(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    claims: TokenClaims = Depends(require_roles("admin")),
):
    async with _state.db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT request_id, actor_user_id, actor_role, action,
                   resource, duration_ms, status_code, ip_address
            FROM pam_audit_log
            ORDER BY chain_sequence DESC
            LIMIT $1 OFFSET $2
            """,
            limit,
            offset,
        )

    return [
        PAMAuditEntry(
            request_id=row["request_id"],
            actor_user_id=row["actor_user_id"],
            actor_role=row["actor_role"],
            action=row["action"],
            resource=row["resource"],
            query_text=None,  # Always redacted in API response
            duration_ms=row["duration_ms"],
            status_code=row["status_code"],
            ip_address=row["ip_address"],
        )
        for row in rows
    ]


@app.get("/health")
async def health():
    vault_ok = await _state.vault_client.check_health()

    db_ok = False
    try:
        async with _state.db_pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        db_ok = True
    except Exception as exc:
        # Health endpoint must not propagate — but we still log so the
        # operator can see *why* the probe is reporting "degraded".
        logger.warning("health_db_probe_failed", error=str(exc), exc_info=True)

    overall = "healthy" if vault_ok and db_ok else "degraded"
    return {
        "status": overall,
        "vault": "ok" if vault_ok else "unreachable",
        "database": "ok" if db_ok else "unreachable",
    }
