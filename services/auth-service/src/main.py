from __future__ import annotations

import asyncio
import asyncpg
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from passlib.context import CryptContext
from typing import Optional
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
    # Seed in background — table may not exist yet if migrations haven't run
    asyncio.create_task(_seed_with_retry())
    yield
    await pool.close()


async def _seed_with_retry(retries: int = 20, delay: float = 5.0):
    """Retry seeding until via_users exists (migrations may still be running)."""
    for attempt in range(1, retries + 1):
        try:
            await _seed_demo_users()
            logger.info("Demo users ready.")
            return
        except asyncpg.UndefinedTableError:
            logger.info(f"via_users not ready yet (attempt {attempt}/{retries}), retrying in {delay}s…")
            await asyncio.sleep(delay)
        except Exception as exc:
            logger.warning(f"Seed attempt {attempt} failed: {exc}")
            await asyncio.sleep(delay)
    logger.error("Could not seed demo users after all retries. Run migrations and restart auth-service.")


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
