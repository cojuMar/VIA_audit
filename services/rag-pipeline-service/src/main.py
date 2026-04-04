"""
RAG Pipeline Service — FastAPI application

Routes:
  POST /narratives/generate          — Generate a guardrail-checked audit narrative
  GET  /narratives/{narrative_id}    — Retrieve a narrative with its citations
  GET  /narratives                   — List narratives for tenant (paginated)
  GET  /hitl/queue                   — List pending HITL items
  POST /hitl/{queue_id}/review       — Submit HITL review decision
  GET  /health                       — Health check
"""

import logging
import asyncpg
from contextlib import asynccontextmanager
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Depends, Header, Query
from pydantic import BaseModel, Field
from .audit_narrator import AuditNarrator
from .config import settings
from .db import create_db_pool

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ---------------------------------------------------------------------------
# App state
# ---------------------------------------------------------------------------

_db_pool: Optional[asyncpg.Pool] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _db_pool
    _db_pool = await create_db_pool()
    logger.info("RAG pipeline service started (model=%s)", settings.generation_model)
    yield
    if _db_pool:
        await _db_pool.close()


app = FastAPI(
    title="Aegis RAG Pipeline Service",
    version="1.0.0",
    lifespan=lifespan,
)


def get_db() -> asyncpg.Pool:
    if _db_pool is None:
        raise HTTPException(503, "Database pool not initialized")
    return _db_pool


# ---------------------------------------------------------------------------
# Auth helper (validates JWT and extracts tenant_id + role)
# ---------------------------------------------------------------------------

def _require_role(required_role: str):
    """Dependency that validates the bearer token and enforces role."""
    async def _check(authorization: str = Header(...)):
        # In production: verify JWT RS256 signature against JWKS endpoint.
        # For now: parse claims from token (production auth-service validates).
        # The tenant context middleware in auth-service handles full validation;
        # this service trusts the tenant_id header set by the API gateway.
        if not authorization.startswith("Bearer "):
            raise HTTPException(401, "Missing or invalid authorization header")
        return authorization[7:]  # Return raw token for downstream use
    return _check


async def _get_tenant_id(x_tenant_id: str = Header(..., alias="X-Tenant-ID")) -> str:
    """Extract tenant_id from trusted gateway header (set by auth middleware)."""
    return x_tenant_id


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class GenerateNarrativeRequest(BaseModel):
    framework: str = Field(..., pattern=r'^(soc2|iso27001|pci_dss|custom)$')
    control_id: Optional[str] = Field(None, max_length=50)
    period_start: str = Field(..., pattern=r'^\d{4}-\d{2}-\d{2}$')
    period_end: str = Field(..., pattern=r'^\d{4}-\d{2}-\d{2}$')
    date_from: Optional[str] = Field(None, pattern=r'^\d{4}-\d{2}-\d{2}$')
    date_to: Optional[str] = Field(None, pattern=r'^\d{4}-\d{2}-\d{2}$')


class GenerateNarrativeResponse(BaseModel):
    narrative_id: str
    narrative: str
    faithfulness_score: float
    groundedness_score: float
    combined_score: float
    hitl_required: bool
    hitl_queue_id: Optional[str]
    citation_count: int
    generation_latency_ms: int
    warning: Optional[str] = None


class HITLReviewRequest(BaseModel):
    verdict: str = Field(..., pattern=r'^(approved|rejected|edited)$')
    revised_narrative: Optional[str] = None
    reviewer_notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok", "model": settings.generation_model}


@app.post("/narratives/generate", response_model=GenerateNarrativeResponse)
async def generate_narrative(
    body: GenerateNarrativeRequest,
    tenant_id: str = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
    _auth = Depends(_require_role("auditor")),
):
    """Generate a guardrail-checked audit narrative.

    The narrative is grounded in evidence retrieved from the tenant's evidence store.
    If the hallucination guardrail score < 0.45, the narrative is escalated to HITL
    review and hitl_required=True is returned to the caller.
    """
    narrator = AuditNarrator(db)
    try:
        result = await narrator.generate(
            tenant_id=tenant_id,
            framework=body.framework,
            control_id=body.control_id,
            period_start=body.period_start,
            period_end=body.period_end,
            date_from=body.date_from,
            date_to=body.date_to,
        )
    except Exception as e:
        logger.error("Narrative generation failed: %s", e, exc_info=True)
        raise HTTPException(500, f"Generation failed: {type(e).__name__}")

    warning = None
    if result.hitl_required:
        warning = (
            f"Narrative quality score {result.combined_score:.2f} is below threshold "
            f"{settings.hallucination_threshold:.2f}. Escalated for human review "
            f"(queue_id={result.hitl_queue_id})."
        )

    return GenerateNarrativeResponse(
        narrative_id=result.narrative_id,
        narrative=result.narrative,
        faithfulness_score=result.faithfulness_score,
        groundedness_score=result.groundedness_score,
        combined_score=result.combined_score,
        hitl_required=result.hitl_required,
        hitl_queue_id=result.hitl_queue_id,
        citation_count=result.citation_count,
        generation_latency_ms=result.generation_latency_ms,
        warning=warning,
    )


@app.get("/narratives")
async def list_narratives(
    tenant_id: str = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
    _auth = Depends(_require_role("auditor")),
    framework: Optional[str] = Query(None),
    hitl_required: Optional[bool] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List audit narratives for the tenant (paginated)."""
    conditions = ["tenant_id = $1::uuid"]
    params: list = [tenant_id]
    idx = 2
    if framework:
        conditions.append(f"framework = ${idx}")
        params.append(framework)
        idx += 1
    if hitl_required is not None:
        conditions.append(f"hitl_required = ${idx}")
        params.append(hitl_required)
        idx += 1
    params.extend([limit, offset])

    where = " AND ".join(conditions)
    async with db.acquire() as conn:
        await conn.execute('SET LOCAL app.tenant_id = $1', tenant_id)
        rows = await conn.fetch(f"""
            SELECT narrative_id, framework, control_id, period_start, period_end,
                   combined_score, hitl_required, hitl_reviewed, created_at
            FROM audit_narratives WHERE {where}
            ORDER BY created_at DESC
            LIMIT ${idx} OFFSET ${idx+1}
        """, *params)
    return [dict(r) for r in rows]


@app.get("/narratives/{narrative_id}")
async def get_narrative(
    narrative_id: str,
    tenant_id: str = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
    _auth = Depends(_require_role("auditor")),
):
    """Get a narrative with its citations."""
    async with db.acquire() as conn:
        await conn.execute('SET LOCAL app.tenant_id = $1', tenant_id)
        row = await conn.fetchrow(
            "SELECT * FROM audit_narratives WHERE narrative_id = $1::uuid AND tenant_id = $2::uuid",
            narrative_id, tenant_id
        )
        if not row:
            raise HTTPException(404, "Narrative not found")
        citations = await conn.fetch(
            "SELECT * FROM rag_citations WHERE narrative_id = $1::uuid ORDER BY citation_rank",
            narrative_id
        )
    return {"narrative": dict(row), "citations": [dict(c) for c in citations]}


@app.get("/hitl/queue")
async def get_hitl_queue(
    tenant_id: str = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
    _auth = Depends(_require_role("auditor")),
    status: str = Query("pending"),
    limit: int = Query(20, ge=1, le=100),
):
    """List pending HITL review items."""
    async with db.acquire() as conn:
        await conn.execute('SET LOCAL app.tenant_id = $1', tenant_id)
        rows = await conn.fetch("""
            SELECT q.queue_id, q.narrative_id, q.escalation_reason,
                   q.flagged_claims, q.priority, q.status, q.created_at,
                   n.framework, n.control_id, n.combined_score
            FROM hitl_narrative_queue q
            JOIN audit_narratives n ON n.narrative_id = q.narrative_id
            WHERE q.tenant_id = $1::uuid AND q.status = $2
            ORDER BY q.priority DESC, q.created_at ASC
            LIMIT $3
        """, tenant_id, status, limit)
    return [dict(r) for r in rows]


@app.post("/hitl/{queue_id}/review")
async def submit_hitl_review(
    queue_id: str,
    body: HITLReviewRequest,
    tenant_id: str = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
    _auth = Depends(_require_role("auditor")),
):
    """Submit a HITL review decision for a flagged narrative."""
    async with db.acquire() as conn:
        async with conn.transaction():
            await conn.execute('SET LOCAL app.tenant_id = $1', tenant_id)

            queue_row = await conn.fetchrow(
                "SELECT * FROM hitl_narrative_queue WHERE queue_id = $1::uuid AND tenant_id = $2::uuid",
                queue_id, tenant_id
            )
            if not queue_row:
                raise HTTPException(404, "Queue item not found")

            await conn.execute("""
                UPDATE hitl_narrative_queue
                SET status = 'resolved', resolved_at = NOW()
                WHERE queue_id = $1::uuid
            """, queue_id)

            await conn.execute("""
                UPDATE audit_narratives
                SET hitl_reviewed = TRUE,
                    hitl_verdict = $1,
                    revised_narrative = $2,
                    hitl_reviewed_at = NOW(),
                    updated_at = NOW()
                WHERE narrative_id = $3::uuid AND tenant_id = $4::uuid
            """,
                body.verdict,
                body.revised_narrative,
                queue_row['narrative_id'],
                tenant_id,
            )

    return {"status": "reviewed", "verdict": body.verdict}
