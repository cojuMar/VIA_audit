from __future__ import annotations

import asyncio
import asyncpg
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from passlib.context import CryptContext
from typing import Optional
import logging

from .auth import create_access_token, decode_access_token

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Environment / config ──────────────────────────────────────────────────────

ENV = os.getenv("ENV", "dev").lower()
IS_PROD = ENV in ("prod", "production")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://aegis_app:aegis_app_dev_pw@postgres:5432/aegis"
)

# JWT_SECRET: fail-closed in non-dev. No committed default outside dev mode.
_JWT_SECRET_ENV = os.getenv("JWT_SECRET")
if IS_PROD and not _JWT_SECRET_ENV:
    logger.critical("JWT_SECRET must be set in production. Refusing to start.")
    sys.exit(1)
JWT_SECRET = _JWT_SECRET_ENV or "aegis_dev_jwt_secret_change_in_prod"

# CORS: explicit allow-list. Wildcard is forbidden with credentials.
_DEFAULT_DEV_ORIGINS = (
    "http://localhost:5173,http://localhost:5174,http://localhost:5175,"
    "http://localhost:5176,http://localhost:5177,http://localhost:5178,"
    "http://localhost:5179,http://localhost:5180,http://localhost:5181,"
    "http://localhost:5182,http://localhost:5183,http://localhost:5184,"
    "http://localhost:5185"
)
_cors_env = os.getenv("CORS_ORIGINS", "").strip() or _DEFAULT_DEV_ORIGINS
CORS_ORIGINS = [o.strip() for o in _cors_env.split(",") if o.strip()]
if IS_PROD and any(o == "*" for o in CORS_ORIGINS):
    logger.critical("CORS wildcard ('*') is not allowed in production.")
    sys.exit(1)

# =============================================================================
# DEMO_TENANT_ID — well-known UUID for the dev-only seeded tenant.
#
# Pattern (Sprint 30):
#   - In dev (ENV != prod) the seeder writes demo users + notifications under
#     this tenant so `curl … /auth/login` works out of the box.
#   - In prod (ENV == prod) Sprint 25's compose overlay sets
#     SEED_DEMO_DATA=false, so this tenant has no rows. The /auth/login
#     fallback to this tenant is also disabled in prod (see below) — a
#     prod client must always supply `tenant_id` explicitly.
#   - This UUID is fixed and intentionally non-secret. Treat it as a
#     well-known marker, not a credential.
# =============================================================================
DEMO_TENANT_ID = "00000000-0000-0000-0000-000000000001"
SEED_DEMO_DATA = os.getenv("SEED_DEMO_DATA", "true" if not IS_PROD else "false").lower() == "true"

# Optional: allow public self-registration only when a tenant is explicitly whitelisted.
SELF_REGISTRATION_TENANT = os.getenv("SELF_REGISTRATION_TENANT")

pwd_context   = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)

pool: Optional[asyncpg.Pool] = None


# ── Tenant-scoped connection helper ───────────────────────────────────────────

@asynccontextmanager
async def tenant_conn(tenant_id: str):
    """
    Acquire a connection, open a transaction, and scope `app.tenant_id`
    to that transaction using `set_config(..., true)`. This is safe under
    PgBouncer transaction pooling and immune to SQL injection (parameterised).
    """
    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id required")
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.tenant_id', $1, true)", tenant_id
            )
            yield conn


# ── Startup / shutdown ────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    if SEED_DEMO_DATA:
        asyncio.create_task(_seed_with_retry())
    else:
        logger.info("SEED_DEMO_DATA=false — skipping demo user/notification seed.")
    yield
    await pool.close()


async def _seed_with_retry(retries: int = 20, delay: float = 5.0):
    for attempt in range(1, retries + 1):
        try:
            await _seed_demo_users()
            await _seed_demo_notifications()
            logger.info("Demo users and notifications ready.")
            return
        except asyncpg.UndefinedTableError as e:
            logger.info(f"Tables not ready yet (attempt {attempt}/{retries}): {e}")
            await asyncio.sleep(delay)
        except Exception as exc:
            logger.warning(f"Seed attempt {attempt} failed: {exc}")
            await asyncio.sleep(delay)
    logger.error("Could not seed demo data after all retries.")


async def _seed_demo_users():
    demo_users = [
        ("admin@via.com",   "admin123",   "Platform Administrator", "super_admin"),
        ("auditor@via.com", "auditor123", "Senior Auditor",         "admin"),
        ("user@via.com",    "user123",    "Audit Analyst",          "end_user"),
    ]
    async with tenant_conn(DEMO_TENANT_ID) as conn:
        for email, password, full_name, role in demo_users:
            existing = await conn.fetchval(
                "SELECT id FROM via_users WHERE email=$1 AND tenant_id=$2",
                email, DEMO_TENANT_ID,
            )
            if not existing:
                hashed = pwd_context.hash(password)
                await conn.execute(
                    """INSERT INTO via_users (tenant_id, email, password_hash, full_name, role)
                       VALUES ($1,$2,$3,$4,$5) ON CONFLICT DO NOTHING""",
                    DEMO_TENANT_ID, email, hashed, full_name, role,
                )
                logger.info(f"Seeded: {email} ({role})")


async def _seed_demo_notifications():
    now = datetime.now(timezone.utc)
    demo_notifications: list[tuple] = [
        ("admin@via.com",   "workpaper_assigned",    "Workpaper Assigned",
         "SOC 2 Type II Access Control workpaper has been assigned to you for review.",
         "workpaper", "wp-001", "info", 2, False),
        ("admin@via.com",   "pbc_overdue",           "PBC Request Overdue",
         "3 PBC requests in engagement ENG-2024-001 are now overdue.",
         "pbc_list", "pbc-001", "critical", 6, False),
        ("admin@via.com",   "monitoring_finding",    "Critical Monitoring Finding",
         "High-severity finding detected in Production IAM controls.",
         "monitoring", "mon-001", "critical", 1, False),
        ("admin@via.com",   "risk_treatment_due",    "Risk Treatment Due",
         "Risk treatment plan for RK-2024-089 is due in 48 hours.",
         "risk", "risk-089", "warning", 12, False),
        ("admin@via.com",   "engagement_assigned",   "New Engagement Assigned",
         "You have been assigned as lead auditor for Q4 2024 Financial Controls Review.",
         "engagement", "eng-002", "info", 24, True),
        ("auditor@via.com", "workpaper_approved",    "Workpaper Approved",
         "Your workpaper IT General Controls Q3 2024 has been approved.",
         "workpaper", "wp-002", "info", 3, False),
        ("auditor@via.com", "pbc_due",               "PBC Request Due Tomorrow",
         "PBC request Q4 Bank Statements is due tomorrow.",
         "pbc_list", "pbc-002", "warning", 8, False),
        ("auditor@via.com", "milestone_missed",      "Audit Milestone Missed",
         "Fieldwork completion milestone for ENG-2024-003 was missed.",
         "engagement", "eng-003", "warning", 5, False),
        ("auditor@via.com", "vendor_assessment_due", "Vendor Assessment Due",
         "Annual security assessment for Salesforce TPRM-V-042 is due in 7 days.",
         "vendor", "v-042", "warning", 18, True),
        ("user@via.com",    "workpaper_assigned",    "Workpaper Assigned to You",
         "Revenue Recognition Testing workpaper has been assigned. Due Friday.",
         "workpaper", "wp-003", "info", 1, False),
        ("user@via.com",    "pbc_due",               "Evidence Request Due Soon",
         "Please submit the requested GL export for the Q4 revenue sample.",
         "pbc_list", "pbc-003", "warning", 4, False),
        ("user@via.com",    "workpaper_rejected",    "Workpaper Needs Revision",
         "Your workpaper Payroll Controls was returned for revision.",
         "workpaper", "wp-004", "warning", 10, False),
    ]

    async with tenant_conn(DEMO_TENANT_ID) as conn:
        existing_count = await conn.fetchval(
            "SELECT COUNT(*) FROM notifications WHERE tenant_id=$1", DEMO_TENANT_ID,
        )
        if existing_count and existing_count > 0:
            logger.info(f"Notifications already seeded ({existing_count} rows).")
            return
        for (email, ntype, title, body, entity_type, entity_id, severity, hours_ago, read) in demo_notifications:
            user_id = await conn.fetchval(
                "SELECT id FROM via_users WHERE email=$1 AND tenant_id=$2",
                email, DEMO_TENANT_ID,
            )
            if not user_id:
                continue
            created = now - timedelta(hours=hours_ago)
            await conn.execute(
                """INSERT INTO notifications
                   (tenant_id, user_id, type, title, body, entity_type, entity_id, severity, read, created_at)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)""",
                DEMO_TENANT_ID, user_id, ntype, title, body,
                entity_type, entity_id, severity, read, created,
            )
        logger.info("Demo notifications seeded.")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="VIA Auth Service", version="1.1.0", lifespan=lifespan)

# Sprint 29 — bind tenant_id + request_id into the structured logger for
# the duration of every request. Imported lazily so a developer running
# the service without `audit_common` on PYTHONPATH still gets a clear
# error rather than a confusing import-time failure.
try:
    from audit_common.middleware import RequestContextMiddleware

    app.add_middleware(RequestContextMiddleware)
except ImportError:  # pragma: no cover — surfaced loudly in CI
    logger.warning(
        "audit_common.middleware unavailable — request logs will be missing "
        "tenant_id / request_id correlation. Install services/_shared/audit_common."
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Tenant-ID", "X-Request-ID"],
)


# ── Models ────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    """
    Login body.

    `tenant_id` is a ROUTING HINT only — used to scope the user lookup under
    RLS. It does NOT determine the JWT's tenant claim, which always comes from
    the matched user row. Supplying a wrong tenant_id fails the lookup; it
    cannot grant access to a different tenant.
    """
    email: str
    password: str
    tenant_id: Optional[str] = None

class RegisterRequest(BaseModel):
    """
    Public self-registration. Role is always forced to 'end_user'.
    Tenant is taken from SELF_REGISTRATION_TENANT env, never from the client.
    Elevated roles must use /auth/admin/invite-user.
    """
    email: str
    password: str = Field(min_length=8)
    full_name: str

class AdminInviteRequest(BaseModel):
    """Admin-only. Creates a user in the caller's tenant with any role."""
    email: str
    password: str = Field(min_length=8)
    full_name: str
    role: str = "end_user"

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict

class UserOut(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    tenant_id: str

class NotificationCreate(BaseModel):
    """tenant_id and issuing context are derived from the JWT, not body."""
    user_id: str
    type: str
    title: str
    body: str = ""
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    severity: str = "info"

class SearchRequest(BaseModel):
    """tenant_id removed — derived from the caller's JWT."""
    query: str
    limit: int = 8


# ── Auth helpers ──────────────────────────────────────────────────────────────

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
):
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_access_token(credentials.credentials, JWT_SECRET)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if not payload.get("tenant_id") or not payload.get("sub"):
        raise HTTPException(status_code=401, detail="Malformed token")
    return payload


async def require_admin(user=Depends(get_current_user)):
    if user.get("role") not in ("super_admin", "admin"):
        raise HTTPException(status_code=403, detail="Admin role required")
    return user


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "auth-service"}


@app.post("/auth/login", response_model=TokenResponse)
async def login(req: LoginRequest):
    """
    Email-based login. The JWT's tenant claim always comes from the matched
    user row, never from the request. Supplying a wrong tenant_id hint just
    fails the lookup.
    """
    email = req.email.lower().strip()
    # Hint used for RLS scoping only. Falls back to the demo tenant in dev
    # so `curl ... /auth/login` keeps working out of the box. In prod
    # (Sprint 30) we refuse the fallback — clients must supply tenant_id
    # explicitly so a misconfigured client can't accidentally probe the
    # demo tenant.
    if req.tenant_id:
        tenant_hint = req.tenant_id
    elif IS_PROD:
        raise HTTPException(
            status_code=400,
            detail="tenant_id is required in production",
        )
    else:
        tenant_hint = DEMO_TENANT_ID
    try:
        async with tenant_conn(tenant_hint) as conn:
            row = await conn.fetchrow(
                """SELECT id, email, password_hash, full_name, role, tenant_id
                   FROM via_users
                   WHERE email = $1 AND tenant_id = $2 AND is_active = true""",
                email, tenant_hint,
            )
    except asyncpg.UndefinedTableError:
        raise HTTPException(
            status_code=503,
            detail="Auth database not ready — migrations may still be running.",
        )

    if not row:
        # Constant-time rejection: run bcrypt verify on a dummy hash.
        pwd_context.verify(req.password, pwd_context.hash("x"))
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if not pwd_context.verify(req.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    token_data = {
        "sub":       str(row["id"]),
        "email":     row["email"],
        "full_name": row["full_name"],
        "role":      row["role"],
        "tenant_id": str(row["tenant_id"]),
    }
    token = create_access_token(token_data, JWT_SECRET)
    return TokenResponse(access_token=token, user=token_data | {"id": token_data["sub"]})


@app.post("/auth/register", response_model=TokenResponse)
async def register(req: RegisterRequest):
    """
    Public self-registration.
    - role is always forced to 'end_user'.
    - tenant comes from SELF_REGISTRATION_TENANT env; if unset, endpoint is disabled.
    """
    if not SELF_REGISTRATION_TENANT:
        raise HTTPException(
            status_code=403,
            detail="Public registration is disabled. Contact your administrator.",
        )

    tenant_id = SELF_REGISTRATION_TENANT
    role = "end_user"  # forced — never taken from the body
    hashed = pwd_context.hash(req.password)

    async with tenant_conn(tenant_id) as conn:
        try:
            row = await conn.fetchrow(
                """INSERT INTO via_users (tenant_id, email, password_hash, full_name, role)
                   VALUES ($1,$2,$3,$4,$5)
                   RETURNING id, email, full_name, role, tenant_id""",
                tenant_id,
                req.email.lower().strip(),
                hashed,
                req.full_name,
                role,
            )
        except asyncpg.UniqueViolationError:
            raise HTTPException(409, "Email already registered")

    token_data = {
        "sub":       str(row["id"]),
        "email":     row["email"],
        "full_name": row["full_name"],
        "role":      row["role"],
        "tenant_id": str(row["tenant_id"]),
    }
    token = create_access_token(token_data, JWT_SECRET)
    return TokenResponse(access_token=token, user=token_data | {"id": token_data["sub"]})


@app.post("/auth/admin/invite-user", response_model=UserOut)
async def admin_invite_user(
    req: AdminInviteRequest,
    admin=Depends(require_admin),
):
    """
    Admin-only. Creates a user in the caller's tenant with any role.
    super_admin role can only be granted by an existing super_admin.
    """
    if req.role not in ("super_admin", "admin", "end_user"):
        raise HTTPException(400, "Invalid role")
    if req.role == "super_admin" and admin.get("role") != "super_admin":
        raise HTTPException(403, "Only super_admin can grant super_admin")

    tenant_id = admin["tenant_id"]
    hashed = pwd_context.hash(req.password)

    async with tenant_conn(tenant_id) as conn:
        try:
            row = await conn.fetchrow(
                """INSERT INTO via_users (tenant_id, email, password_hash, full_name, role)
                   VALUES ($1,$2,$3,$4,$5)
                   RETURNING id, email, full_name, role, tenant_id""",
                tenant_id,
                req.email.lower().strip(),
                hashed,
                req.full_name,
                req.role,
            )
        except asyncpg.UniqueViolationError:
            raise HTTPException(409, "Email already registered")

    return UserOut(
        id=str(row["id"]),
        email=row["email"],
        full_name=row["full_name"],
        role=row["role"],
        tenant_id=str(row["tenant_id"]),
    )


@app.get("/auth/me", response_model=UserOut)
async def me(user=Depends(get_current_user)):
    return UserOut(
        id=user["sub"],
        email=user["email"],
        full_name=user["full_name"],
        role=user["role"],
        tenant_id=user["tenant_id"],
    )


@app.post("/auth/logout")
async def logout(user=Depends(get_current_user)):
    return {"message": "Logged out successfully"}


# ── Notification helpers ──────────────────────────────────────────────────────

def _row_to_dict(row) -> dict:
    d = dict(row)
    for k, v in d.items():
        if hasattr(v, "isoformat"):
            d[k] = v.isoformat()
        elif hasattr(v, "hex") and hasattr(v, "int"):
            d[k] = str(v)
    return d


# ── Notification routes (ALL authenticated; tenant_id/user_id from JWT) ────────

@app.get("/auth/notifications")
async def list_notifications(
    limit: int = Query(default=50, le=200),
    unread_only: bool = Query(default=False),
    user=Depends(get_current_user),
):
    tenant_id = user["tenant_id"]
    user_id = user["sub"]
    try:
        async with tenant_conn(tenant_id) as conn:
            if unread_only:
                rows = await conn.fetch(
                    """SELECT id, type, title, body, entity_type, entity_id, severity, read, created_at
                       FROM notifications
                       WHERE tenant_id=$1 AND user_id=$2 AND read=false AND deleted=false
                       ORDER BY created_at DESC LIMIT $3""",
                    tenant_id, user_id, limit,
                )
            else:
                rows = await conn.fetch(
                    """SELECT id, type, title, body, entity_type, entity_id, severity, read, created_at
                       FROM notifications
                       WHERE tenant_id=$1 AND user_id=$2 AND deleted=false
                       ORDER BY created_at DESC LIMIT $3""",
                    tenant_id, user_id, limit,
                )
            return [_row_to_dict(r) for r in rows]
    except asyncpg.UndefinedTableError:
        return []


@app.get("/auth/notifications/unread-count")
async def unread_count(user=Depends(get_current_user)):
    tenant_id = user["tenant_id"]
    user_id = user["sub"]
    try:
        async with tenant_conn(tenant_id) as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM notifications WHERE tenant_id=$1 AND user_id=$2 AND read=false AND deleted=false",
                tenant_id, user_id,
            )
            return {"count": int(count or 0)}
    except asyncpg.UndefinedTableError:
        return {"count": 0}


@app.patch("/auth/notifications/read-all")
async def mark_all_read(user=Depends(get_current_user)):
    tenant_id = user["tenant_id"]
    user_id = user["sub"]
    try:
        async with tenant_conn(tenant_id) as conn:
            await conn.execute(
                "UPDATE notifications SET read=true WHERE tenant_id=$1 AND user_id=$2 AND read=false AND deleted=false",
                tenant_id, user_id,
            )
        return {"ok": True}
    except asyncpg.UndefinedTableError:
        return {"ok": True}


@app.patch("/auth/notifications/{notification_id}/read")
async def mark_read(notification_id: str, user=Depends(get_current_user)):
    tenant_id = user["tenant_id"]
    user_id = user["sub"]
    try:
        async with tenant_conn(tenant_id) as conn:
            # Only allow marking notifications owned by this user.
            await conn.execute(
                "UPDATE notifications SET read=true WHERE id=$1 AND tenant_id=$2 AND user_id=$3 AND deleted=false",
                notification_id, tenant_id, user_id,
            )
        return {"ok": True}
    except asyncpg.UndefinedTableError:
        return {"ok": True}


@app.delete("/auth/notifications/{notification_id}")
async def delete_notification(notification_id: str, user=Depends(get_current_user)):
    tenant_id = user["tenant_id"]
    user_id = user["sub"]
    try:
        async with tenant_conn(tenant_id) as conn:
            await conn.execute(
                "UPDATE notifications SET deleted=true, deleted_at=NOW() WHERE id=$1 AND tenant_id=$2 AND user_id=$3",
                notification_id, tenant_id, user_id,
            )
        return {"ok": True}
    except asyncpg.UndefinedTableError:
        return {"ok": True}


@app.post("/auth/notifications", status_code=201)
async def create_notification(
    data: NotificationCreate,
    admin=Depends(require_admin),
):
    """
    Creating notifications is an admin-only operation. tenant_id comes
    from the admin's JWT, never from the body.
    """
    tenant_id = admin["tenant_id"]
    try:
        async with tenant_conn(tenant_id) as conn:
            # Verify the target user belongs to this tenant.
            target = await conn.fetchval(
                "SELECT 1 FROM via_users WHERE id=$1 AND tenant_id=$2",
                data.user_id, tenant_id,
            )
            if not target:
                raise HTTPException(404, "Target user not found in tenant")
            row = await conn.fetchrow(
                """INSERT INTO notifications
                   (tenant_id, user_id, type, title, body, entity_type, entity_id, severity)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                   RETURNING id, type, title, body, entity_type, entity_id, severity, read, created_at""",
                tenant_id, data.user_id, data.type, data.title, data.body,
                data.entity_type, data.entity_id, data.severity,
            )
            return _row_to_dict(row)
    except asyncpg.UndefinedTableError:
        raise HTTPException(status_code=503, detail="Notifications table not ready — run migrations.")


# ── Global Search helpers ─────────────────────────────────────────────────────

async def _search_entity(tenant_id: str, sql: str, pattern: str, limit: int,
                          mapper) -> list[dict]:
    """One ILIKE search on a tenant-scoped transaction; [] on any error."""
    try:
        async with tenant_conn(tenant_id) as conn:
            rows = await conn.fetch(sql, tenant_id, pattern, limit)
            return [mapper(r) for r in rows]
    except Exception:
        return []


def _sid(v) -> str:
    return str(v) if v is not None else ""


# ── Global Search endpoint (authenticated) ────────────────────────────────────

@app.post("/auth/search")
async def global_search(req: SearchRequest, user=Depends(get_current_user)):
    query = req.query.strip()
    tenant_id = user["tenant_id"]
    limit = max(1, min(req.limit, 20))

    if len(query) < 2:
        return {"results": [], "total": 0}

    pattern = f"%{query}%"

    searches = await asyncio.gather(
        _search_entity(tenant_id,
            """SELECT id, title, lead_auditor, status, engagement_code
               FROM audit_engagements
               WHERE tenant_id = $1
                 AND (title ILIKE $2
                      OR COALESCE(lead_auditor,'') ILIKE $2
                      OR COALESCE(engagement_code,'') ILIKE $2
                      OR COALESCE(scope,'') ILIKE $2)
               ORDER BY created_at DESC LIMIT $3""",
            pattern, limit,
            lambda r: {
                "type": "engagement",
                "id": _sid(r["id"]),
                "title": r["title"] or "",
                "subtitle": f"Lead: {r['lead_auditor']}" if r["lead_auditor"] else "",
                "meta": (r["status"] or "").replace("_", " "),
                "module_port": 5183,
                "module_id": "audit-planning",
            }),
        _search_entity(tenant_id,
            """SELECT id, title, description, severity, status, management_owner
               FROM audit_issues
               WHERE tenant_id = $1
                 AND (title ILIKE $2
                      OR COALESCE(description,'') ILIKE $2
                      OR COALESCE(management_owner,'') ILIKE $2
                      OR COALESCE(finding_type,'') ILIKE $2)
               ORDER BY created_at DESC LIMIT $3""",
            pattern, limit,
            lambda r: {
                "type": "issue",
                "id": _sid(r["id"]),
                "title": r["title"] or "",
                "subtitle": f"Owner: {r['management_owner']}" if r["management_owner"] else (r["description"] or "")[:80],
                "meta": (r["severity"] or ""),
                "module_port": 5179,
                "module_id": "pbc",
            }),
        _search_entity(tenant_id,
            """SELECT id, title, description, owner, status, risk_id
               FROM risks
               WHERE tenant_id = $1
                 AND (title ILIKE $2
                      OR COALESCE(description,'') ILIKE $2
                      OR COALESCE(owner,'') ILIKE $2
                      OR COALESCE(risk_id,'') ILIKE $2)
               ORDER BY created_at DESC LIMIT $3""",
            pattern, limit,
            lambda r: {
                "type": "risk",
                "id": _sid(r["id"]),
                "title": r["title"] or "",
                "subtitle": f"Owner: {r['owner']}" if r["owner"] else f"ID: {r['risk_id'] or ''}",
                "meta": (r["status"] or "").replace("_", " "),
                "module_port": 5182,
                "module_id": "risk",
            }),
        _search_entity(tenant_id,
            """SELECT id, title, workpaper_type, status, preparer
               FROM workpapers
               WHERE tenant_id = $1
                 AND (title ILIKE $2
                      OR COALESCE(workpaper_type,'') ILIKE $2
                      OR COALESCE(preparer,'') ILIKE $2
                      OR COALESCE(wp_reference,'') ILIKE $2)
               ORDER BY created_at DESC LIMIT $3""",
            pattern, limit,
            lambda r: {
                "type": "workpaper",
                "id": _sid(r["id"]),
                "title": r["title"] or "",
                "subtitle": f"Preparer: {r['preparer']}" if r["preparer"] else (r["workpaper_type"] or "").replace("_", " "),
                "meta": (r["status"] or "").replace("_", " "),
                "module_port": 5179,
                "module_id": "pbc",
            }),
        _search_entity(tenant_id,
            """SELECT r.id, r.title, r.description, r.status, r.category, r.assigned_to
               FROM pbc_requests r
               JOIN pbc_request_lists l ON r.list_id = l.id
               WHERE l.tenant_id = $1
                 AND (r.title ILIKE $2
                      OR COALESCE(r.description,'') ILIKE $2
                      OR COALESCE(r.category,'') ILIKE $2
                      OR COALESCE(r.assigned_to,'') ILIKE $2)
               ORDER BY r.created_at DESC LIMIT $3""",
            pattern, limit,
            lambda r: {
                "type": "pbc_request",
                "id": _sid(r["id"]),
                "title": r["title"] or "",
                "subtitle": f"Assigned: {r['assigned_to']}" if r["assigned_to"] else (r["category"] or ""),
                "meta": (r["status"] or "").replace("_", " "),
                "module_port": 5179,
                "module_id": "pbc",
            }),
        _search_entity(tenant_id,
            """SELECT id, full_name, email, role
               FROM via_users
               WHERE tenant_id = $1
                 AND is_active = true
                 AND (full_name ILIKE $2 OR email ILIKE $2)
               ORDER BY full_name ASC LIMIT $3""",
            pattern, limit,
            lambda r: {
                "type": "user",
                "id": _sid(r["id"]),
                "title": r["full_name"] or r["email"] or "",
                "subtitle": r["email"] or "",
                "meta": (r["role"] or "").replace("_", " "),
                "module_port": 0,
                "module_id": "",
            }),
        return_exceptions=True,
    )

    results: list[dict] = []
    for group in searches:
        if isinstance(group, list):
            results.extend(group)

    return {"results": results, "total": len(results)}
