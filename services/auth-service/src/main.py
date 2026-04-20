from __future__ import annotations

import asyncio
import asyncpg
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, HTTPException, Depends, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from passlib.context import CryptContext
from typing import Optional, List
import logging

from .auth import create_access_token, decode_access_token

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://aegis_app:aegis_app_dev_pw@postgres:5432/aegis"
)
JWT_SECRET    = os.getenv("JWT_SECRET", "aegis_dev_jwt_secret_change_in_prod")
DEMO_TENANT_ID = "00000000-0000-0000-0000-000000000001"

pwd_context   = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)

pool: Optional[asyncpg.Pool] = None


# ── Startup / shutdown ────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    # Seed in background — tables may not exist yet if migrations haven't run
    asyncio.create_task(_seed_with_retry())
    yield
    await pool.close()


async def _seed_with_retry(retries: int = 20, delay: float = 5.0):
    """Retry seeding until via_users exists (migrations may still be running)."""
    for attempt in range(1, retries + 1):
        try:
            await _seed_demo_users()
            await _seed_demo_notifications()
            logger.info("Demo users and notifications ready.")
            return
        except asyncpg.UndefinedTableError as e:
            logger.info(f"Tables not ready yet (attempt {attempt}/{retries}), retrying in {delay}s: {e}")
            await asyncio.sleep(delay)
        except Exception as exc:
            logger.warning(f"Seed attempt {attempt} failed: {exc}")
            await asyncio.sleep(delay)
    logger.error("Could not seed demo data after all retries. Run migrations and restart auth-service.")


async def _seed_demo_users():
    demo_users = [
        ("admin@via.com",   "admin123",   "Platform Administrator", "super_admin"),
        ("auditor@via.com", "auditor123", "Senior Auditor",         "admin"),
        ("user@via.com",    "user123",    "Audit Analyst",          "end_user"),
    ]
    async with pool.acquire() as conn:
        # Set tenant context so RLS policy can evaluate correctly (session-level)
        await conn.execute(f"SET app.tenant_id = '{DEMO_TENANT_ID}'")
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
    """Seed realistic demo notifications for each user. Idempotent — skips if already present."""
    now = datetime.now(timezone.utc)

    demo_notifications: list[tuple] = [
        # (email, type, title, body, entity_type, entity_id, severity, hours_ago, read)
        ("admin@via.com",   "workpaper_assigned",    "Workpaper Assigned",
         "SOC 2 Type II — Access Control workpaper has been assigned to you for review.",
         "workpaper", "wp-001", "info", 2, False),
        ("admin@via.com",   "pbc_overdue",           "PBC Request Overdue",
         "3 PBC requests in engagement ENG-2024-001 are now overdue. Immediate action required.",
         "pbc_list", "pbc-001", "critical", 6, False),
        ("admin@via.com",   "monitoring_finding",    "Critical Monitoring Finding",
         "High-severity finding detected in Production IAM controls. Review within 24 hours.",
         "monitoring", "mon-001", "critical", 1, False),
        ("admin@via.com",   "risk_treatment_due",    "Risk Treatment Due",
         "Risk treatment plan for RK-2024-089 is due in 48 hours.",
         "risk", "risk-089", "warning", 12, False),
        ("admin@via.com",   "engagement_assigned",   "New Engagement Assigned",
         "You have been assigned as lead auditor for Q4 2024 Financial Controls Review.",
         "engagement", "eng-002", "info", 24, True),

        ("auditor@via.com", "workpaper_approved",    "Workpaper Approved",
         "Your workpaper 'IT General Controls — Q3 2024' has been approved by the audit manager.",
         "workpaper", "wp-002", "info", 3, False),
        ("auditor@via.com", "pbc_due",               "PBC Request Due Tomorrow",
         "PBC request 'Q4 Bank Statements' is due tomorrow. Please follow up with the client.",
         "pbc_list", "pbc-002", "warning", 8, False),
        ("auditor@via.com", "milestone_missed",      "Audit Milestone Missed",
         "Fieldwork completion milestone for ENG-2024-003 was missed. Update the engagement status.",
         "engagement", "eng-003", "warning", 5, False),
        ("auditor@via.com", "vendor_assessment_due", "Vendor Assessment Due",
         "Annual security assessment for Salesforce (TPRM-V-042) is due in 7 days.",
         "vendor", "v-042", "warning", 18, True),

        ("user@via.com",    "workpaper_assigned",    "Workpaper Assigned to You",
         "Revenue Recognition Testing workpaper has been assigned. Due date: Friday.",
         "workpaper", "wp-003", "info", 1, False),
        ("user@via.com",    "pbc_due",               "Evidence Request Due Soon",
         "Please submit the requested GL export for the Q4 revenue sample by end of week.",
         "pbc_list", "pbc-003", "warning", 4, False),
        ("user@via.com",    "workpaper_rejected",    "Workpaper Needs Revision",
         "Your workpaper 'Payroll Controls' was returned for revision. See review comments.",
         "workpaper", "wp-004", "warning", 10, False),
    ]

    async with pool.acquire() as conn:
        await conn.execute(f"SET app.tenant_id = '{DEMO_TENANT_ID}'")

        # Check if already seeded
        existing_count = await conn.fetchval(
            "SELECT COUNT(*) FROM notifications WHERE tenant_id=$1",
            DEMO_TENANT_ID,
        )
        if existing_count and existing_count > 0:
            logger.info(f"Notifications already seeded ({existing_count} rows), skipping.")
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

app = FastAPI(title="VIA Auth Service", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Models ────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str
    password: str
    tenant_id: Optional[str] = DEMO_TENANT_ID

class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str
    role: str = "end_user"
    tenant_id: Optional[str] = DEMO_TENANT_ID

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
    user_id: str
    type: str
    title: str
    body: str = ""
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    severity: str = "info"
    tenant_id: Optional[str] = None

class SearchRequest(BaseModel):
    query: str
    tenant_id: Optional[str] = None
    limit: int = 8


# ── Auth helper ───────────────────────────────────────────────────────────────

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
):
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_access_token(credentials.credentials, JWT_SECRET)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "auth-service"}


@app.post("/auth/login", response_model=TokenResponse)
async def login(req: LoginRequest):
    tenant_id = req.tenant_id or DEMO_TENANT_ID
    try:
        async with pool.acquire() as conn:
            # Set tenant context so RLS policy evaluates correctly (session-level)
            await conn.execute(f"SET app.tenant_id = '{tenant_id}'")
            row = await conn.fetchrow(
                """SELECT id, email, password_hash, full_name, role, tenant_id
                   FROM via_users
                   WHERE email = $1 AND tenant_id = $2 AND is_active = true""",
                req.email.lower().strip(),
                tenant_id,
            )
    except asyncpg.UndefinedTableError:
        raise HTTPException(
            status_code=503,
            detail="Auth database not ready — migrations may still be running. Please wait a moment and try again.",
        )

    if not row or not pwd_context.verify(req.password, row["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    token_data = {
        "sub":       str(row["id"]),
        "email":     row["email"],
        "full_name": row["full_name"],
        "role":      row["role"],
        "tenant_id": str(row["tenant_id"]),
    }
    token = create_access_token(token_data, JWT_SECRET)
    return TokenResponse(
        access_token=token,
        user={
            "id":        str(row["id"]),
            "email":     row["email"],
            "full_name": row["full_name"],
            "role":      row["role"],
            "tenant_id": str(row["tenant_id"]),
        },
    )


@app.post("/auth/register", response_model=TokenResponse)
async def register(req: RegisterRequest):
    if req.role not in ("super_admin", "admin", "end_user"):
        raise HTTPException(400, "Invalid role")
    hashed = pwd_context.hash(req.password)
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                """INSERT INTO via_users (tenant_id, email, password_hash, full_name, role)
                   VALUES ($1,$2,$3,$4,$5)
                   RETURNING id, email, full_name, role, tenant_id""",
                req.tenant_id or DEMO_TENANT_ID,
                req.email.lower().strip(),
                hashed,
                req.full_name,
                req.role,
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
    return TokenResponse(
        access_token=token,
        user={
            "id":        str(row["id"]),
            "email":     row["email"],
            "full_name": row["full_name"],
            "role":      row["role"],
            "tenant_id": str(row["tenant_id"]),
        },
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
async def logout():
    return {"message": "Logged out successfully"}


# ── Notification helpers ──────────────────────────────────────────────────────

def _row_to_dict(row) -> dict:
    """Convert asyncpg Record to JSON-safe dict."""
    d = dict(row)
    for k, v in d.items():
        if hasattr(v, "isoformat"):       # datetime / date
            d[k] = v.isoformat()
        elif hasattr(v, "hex") and hasattr(v, "int"):  # UUID
            d[k] = str(v)
    return d


# ── Notification routes ───────────────────────────────────────────────────────

@app.get("/auth/notifications")
async def list_notifications(
    user_id: str = Query(...),
    tenant_id: str = Query(default=DEMO_TENANT_ID),
    limit: int = Query(default=50, le=200),
    unread_only: bool = Query(default=False),
):
    try:
        async with pool.acquire() as conn:
            await conn.execute(f"SET app.tenant_id = '{tenant_id}'")
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
async def unread_count(
    user_id: str = Query(...),
    tenant_id: str = Query(default=DEMO_TENANT_ID),
):
    try:
        async with pool.acquire() as conn:
            await conn.execute(f"SET app.tenant_id = '{tenant_id}'")
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM notifications WHERE tenant_id=$1 AND user_id=$2 AND read=false AND deleted=false",
                tenant_id, user_id,
            )
            return {"count": int(count or 0)}
    except asyncpg.UndefinedTableError:
        return {"count": 0}


@app.patch("/auth/notifications/read-all")
async def mark_all_read(
    user_id: str = Query(...),
    tenant_id: str = Query(default=DEMO_TENANT_ID),
):
    try:
        async with pool.acquire() as conn:
            await conn.execute(f"SET app.tenant_id = '{tenant_id}'")
            await conn.execute(
                "UPDATE notifications SET read=true WHERE tenant_id=$1 AND user_id=$2 AND read=false AND deleted=false",
                tenant_id, user_id,
            )
        return {"ok": True}
    except asyncpg.UndefinedTableError:
        return {"ok": True}


@app.patch("/auth/notifications/{notification_id}/read")
async def mark_read(
    notification_id: str,
    tenant_id: str = Query(default=DEMO_TENANT_ID),
):
    try:
        async with pool.acquire() as conn:
            await conn.execute(f"SET app.tenant_id = '{tenant_id}'")
            await conn.execute(
                "UPDATE notifications SET read=true WHERE id=$1 AND tenant_id=$2 AND deleted=false",
                notification_id, tenant_id,
            )
        return {"ok": True}
    except asyncpg.UndefinedTableError:
        return {"ok": True}


@app.delete("/auth/notifications/{notification_id}")
async def delete_notification(
    notification_id: str,
    tenant_id: str = Query(default=DEMO_TENANT_ID),
):
    """Soft-delete: flags deleted=true, never removes the row."""
    try:
        async with pool.acquire() as conn:
            await conn.execute(f"SET app.tenant_id = '{tenant_id}'")
            await conn.execute(
                "UPDATE notifications SET deleted=true, deleted_at=NOW() WHERE id=$1 AND tenant_id=$2",
                notification_id, tenant_id,
            )
        return {"ok": True}
    except asyncpg.UndefinedTableError:
        return {"ok": True}


@app.post("/auth/notifications", status_code=201)
async def create_notification(data: NotificationCreate):
    tid = data.tenant_id or DEMO_TENANT_ID
    try:
        async with pool.acquire() as conn:
            await conn.execute(f"SET app.tenant_id = '{tid}'")
            row = await conn.fetchrow(
                """INSERT INTO notifications
                   (tenant_id, user_id, type, title, body, entity_type, entity_id, severity)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                   RETURNING id, type, title, body, entity_type, entity_id, severity, read, created_at""",
                tid, data.user_id, data.type, data.title, data.body,
                data.entity_type, data.entity_id, data.severity,
            )
            return _row_to_dict(row)
    except asyncpg.UndefinedTableError:
        raise HTTPException(status_code=503, detail="Notifications table not ready — run migrations.")


# ── Global Search helpers ─────────────────────────────────────────────────────

async def _search_entity(pool, tenant_id: str, sql: str, pattern: str, limit: int,
                          mapper) -> list[dict]:
    """Run one ILIKE search on a single connection; return [] on any error."""
    try:
        async with pool.acquire() as conn:
            await conn.execute(f"SET app.tenant_id = '{tenant_id}'")
            rows = await conn.fetch(sql, tenant_id, pattern, limit)
            return [mapper(r) for r in rows]
    except Exception:
        return []


def _sid(v) -> str:
    """Safe UUID→str."""
    return str(v) if v is not None else ""


# ── Global Search endpoint ────────────────────────────────────────────────────

@app.post("/auth/search")
async def global_search(req: SearchRequest):
    query = req.query.strip()
    tenant_id = req.tenant_id or DEMO_TENANT_ID
    limit = max(1, min(req.limit, 20))

    if len(query) < 2:
        return {"results": [], "total": 0}

    pattern = f"%{query}%"

    # Six parallel ILIKE searches — each on its own connection from the pool
    searches = await asyncio.gather(
        # 1. Audit Engagements
        _search_entity(pool, tenant_id,
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

        # 2. Audit Issues
        _search_entity(pool, tenant_id,
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

        # 3. Risks
        _search_entity(pool, tenant_id,
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

        # 4. Workpapers
        _search_entity(pool, tenant_id,
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

        # 5. PBC Requests
        _search_entity(pool, tenant_id,
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

        # 6. Platform Users
        _search_entity(pool, tenant_id,
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
