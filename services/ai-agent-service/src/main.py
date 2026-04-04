import json
import logging
from contextlib import asynccontextmanager
from uuid import UUID

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query

from .agent_engine import AgentEngine
from .config import settings
from .conversation_manager import ConversationManager
from .db import close_pool, get_pool, init_pool, tenant_conn
from .models import (
    ChatRequest,
    ChatResponse,
    ConversationTitleUpdate,
    FeedbackCreate,
    ReportRequest,
    ScheduledQueryCreate,
    ScheduledQueryUpdate,
)
from .report_manager import ReportManager
from .scheduler import AgentScheduler
from .tool_definitions import AEGIS_TOOLS
from .tool_executor import ToolExecutor

logger = logging.getLogger(__name__)

# Global service instances
http_client: httpx.AsyncClient | None = None
tool_executor: ToolExecutor | None = None
agent_engine: AgentEngine | None = None
scheduler: AgentScheduler | None = None
conversation_manager = ConversationManager()
report_manager = ReportManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client, tool_executor, agent_engine, scheduler

    # Startup
    pool = await init_pool(settings.database_url)
    http_client = httpx.AsyncClient(timeout=15.0)
    tool_executor = ToolExecutor(settings, http_client)
    agent_engine = AgentEngine(settings, tool_executor)
    scheduler = AgentScheduler(settings)
    scheduler.start(pool, agent_engine)

    logger.info("ai-agent-service started on port 3020 (model=%s)", settings.agent_model)
    yield

    # Shutdown
    scheduler.stop()
    await http_client.aclose()
    await close_pool()
    logger.info("ai-agent-service shut down")


app = FastAPI(
    title="Aegis AI Agent Service",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------

def require_tenant(x_tenant_id: str = Header(..., alias="X-Tenant-ID")) -> str:
    """Validate and return the tenant ID from the request header."""
    try:
        UUID(x_tenant_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="X-Tenant-ID must be a valid UUID")
    return x_tenant_id


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "ai-agent-service",
        "model": settings.agent_model,
        "tools_count": len(AEGIS_TOOLS),
    }


# ---------------------------------------------------------------------------
# Tools catalog
# ---------------------------------------------------------------------------

@app.get("/tools")
async def list_tools():
    """Return all available tool definitions with names and descriptions."""
    return [
        {"name": t["name"], "description": t["description"], "input_schema": t["input_schema"]}
        for t in AEGIS_TOOLS
    ]


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

@app.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    tenant_id: str = Depends(require_tenant),
):
    """Send a message and get an AI response with optional tool use."""
    pool = get_pool()
    try:
        return await agent_engine.chat(pool, tenant_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.exception("Error in /chat")
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------

@app.get("/conversations")
async def list_conversations(
    status: str = Query("active"),
    tenant_id: str = Depends(require_tenant),
):
    pool = get_pool()
    return await conversation_manager.list(pool, tenant_id, status=status)


@app.get("/conversations/stats")
async def conversation_stats(tenant_id: str = Depends(require_tenant)):
    pool = get_pool()
    return await conversation_manager.get_stats(pool, tenant_id)


@app.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    tenant_id: str = Depends(require_tenant),
):
    pool = get_pool()
    conv = await conversation_manager.get(pool, tenant_id, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = await conversation_manager.get_messages(pool, tenant_id, conversation_id)
    return {**conv, "messages": messages}


@app.delete("/conversations/{conversation_id}")
async def archive_conversation(
    conversation_id: str,
    tenant_id: str = Depends(require_tenant),
):
    pool = get_pool()
    try:
        return await conversation_manager.archive(pool, tenant_id, conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.put("/conversations/{conversation_id}/title")
async def update_conversation_title(
    conversation_id: str,
    body: ConversationTitleUpdate,
    tenant_id: str = Depends(require_tenant),
):
    pool = get_pool()
    try:
        return await conversation_manager.update_title(pool, tenant_id, conversation_id, body.title)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

@app.post("/reports/generate")
async def generate_report(
    request: ReportRequest,
    tenant_id: str = Depends(require_tenant),
):
    pool = get_pool()
    try:
        return await agent_engine.generate_report(pool, tenant_id, request)
    except Exception as exc:
        logger.exception("Error generating report")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/reports")
async def list_reports(
    report_type: str | None = Query(None),
    tenant_id: str = Depends(require_tenant),
):
    pool = get_pool()
    return await report_manager.list(pool, tenant_id, report_type=report_type)


@app.get("/reports/{report_id}")
async def get_report(
    report_id: str,
    tenant_id: str = Depends(require_tenant),
):
    pool = get_pool()
    report = await report_manager.get(pool, tenant_id, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


# ---------------------------------------------------------------------------
# Scheduled queries
# ---------------------------------------------------------------------------

@app.get("/scheduled")
async def list_scheduled_queries(tenant_id: str = Depends(require_tenant)):
    pool = get_pool()
    async with tenant_conn(pool, tenant_id) as conn:
        rows = await conn.fetch(
            """SELECT id, tenant_id, query_name, natural_language_query,
                      schedule_cron, delivery_config, is_active,
                      last_run_at, next_run_at, created_at, updated_at
               FROM agent_scheduled_queries
               WHERE tenant_id = $1
               ORDER BY created_at DESC""",
            UUID(tenant_id),
        )
    return [dict(r) for r in rows]


@app.post("/scheduled", status_code=201)
async def create_scheduled_query(
    body: ScheduledQueryCreate,
    tenant_id: str = Depends(require_tenant),
):
    pool = get_pool()
    async with tenant_conn(pool, tenant_id) as conn:
        row = await conn.fetchrow(
            """INSERT INTO agent_scheduled_queries
               (tenant_id, query_name, natural_language_query, schedule_cron, delivery_config)
               VALUES ($1, $2, $3, $4, $5)
               RETURNING id, tenant_id, query_name, natural_language_query,
                         schedule_cron, delivery_config, is_active, created_at""",
            UUID(tenant_id),
            body.query_name,
            body.natural_language_query,
            body.schedule_cron,
            json.dumps(body.delivery_config),
        )
    return dict(row)


@app.put("/scheduled/{query_id}")
async def update_scheduled_query(
    query_id: str,
    body: ScheduledQueryUpdate,
    tenant_id: str = Depends(require_tenant),
):
    pool = get_pool()
    # Build dynamic SET clause from non-None fields
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    set_clauses = []
    values = []
    idx = 1
    for field, value in updates.items():
        col = field
        if col == "delivery_config":
            set_clauses.append(f"{col} = ${idx}::jsonb")
            values.append(json.dumps(value))
        else:
            set_clauses.append(f"{col} = ${idx}")
            values.append(value)
        idx += 1

    set_clauses.append(f"updated_at = NOW()")
    values.extend([UUID(query_id), UUID(tenant_id)])

    async with tenant_conn(pool, tenant_id) as conn:
        row = await conn.fetchrow(
            f"""UPDATE agent_scheduled_queries
                SET {', '.join(set_clauses)}
                WHERE id = ${idx} AND tenant_id = ${idx + 1}
                RETURNING id, query_name, natural_language_query,
                          schedule_cron, is_active, updated_at""",
            *values,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Scheduled query not found")
    return dict(row)


@app.delete("/scheduled/{query_id}")
async def disable_scheduled_query(
    query_id: str,
    tenant_id: str = Depends(require_tenant),
):
    """Disable (soft-delete) a scheduled query by setting is_active=false."""
    pool = get_pool()
    async with tenant_conn(pool, tenant_id) as conn:
        row = await conn.fetchrow(
            """UPDATE agent_scheduled_queries
               SET is_active = false, updated_at = NOW()
               WHERE id = $1 AND tenant_id = $2
               RETURNING id, is_active, updated_at""",
            UUID(query_id), UUID(tenant_id),
        )
    if not row:
        raise HTTPException(status_code=404, detail="Scheduled query not found")
    return dict(row)


@app.post("/scheduled/{query_id}/run")
async def run_scheduled_query_now(
    query_id: str,
    tenant_id: str = Depends(require_tenant),
):
    """Run a scheduled query immediately on demand."""
    pool = get_pool()
    async with tenant_conn(pool, tenant_id) as conn:
        row = await conn.fetchrow(
            "SELECT * FROM agent_scheduled_queries WHERE id = $1 AND tenant_id = $2",
            UUID(query_id), UUID(tenant_id),
        )
    if not row:
        raise HTTPException(status_code=404, detail="Scheduled query not found")

    request = ChatRequest(
        message=row["natural_language_query"],
        user_identifier=f"scheduler:{row['query_name']}",
    )
    try:
        response = await agent_engine.chat(pool, tenant_id, request)
    except Exception as exc:
        logger.exception("Error running scheduled query on demand")
        raise HTTPException(status_code=500, detail=str(exc))

    # Update last_run_at
    async with tenant_conn(pool, tenant_id) as conn:
        await conn.execute(
            "UPDATE agent_scheduled_queries SET last_run_at = NOW() WHERE id = $1",
            UUID(query_id),
        )

    return {
        "query_id": query_id,
        "conversation_id": response.conversation_id,
        "message_id": response.message_id,
        "latency_ms": response.latency_ms,
    }


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------

@app.post("/feedback", status_code=201)
async def submit_feedback(
    body: FeedbackCreate,
    tenant_id: str = Depends(require_tenant),
):
    if body.rating < 1 or body.rating > 5:
        raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")
    pool = get_pool()
    async with tenant_conn(pool, tenant_id) as conn:
        row = await conn.fetchrow(
            """INSERT INTO agent_feedback
               (tenant_id, message_id, conversation_id, rating, feedback_type, comment)
               VALUES ($1, $2, $3, $4, $5, $6)
               RETURNING id, tenant_id, message_id, conversation_id, rating, feedback_type, comment, created_at""",
            UUID(tenant_id),
            UUID(body.message_id),
            UUID(body.conversation_id),
            body.rating,
            body.feedback_type,
            body.comment,
        )
    return dict(row)


@app.get("/feedback/summary")
async def feedback_summary(tenant_id: str = Depends(require_tenant)):
    """Return aggregated rating statistics for the tenant."""
    pool = get_pool()
    async with tenant_conn(pool, tenant_id) as conn:
        row = await conn.fetchrow(
            """SELECT
                   COUNT(*) AS total_feedback,
                   AVG(rating) AS avg_rating,
                   COUNT(*) FILTER (WHERE rating = 5) AS five_star,
                   COUNT(*) FILTER (WHERE rating = 4) AS four_star,
                   COUNT(*) FILTER (WHERE rating = 3) AS three_star,
                   COUNT(*) FILTER (WHERE rating = 2) AS two_star,
                   COUNT(*) FILTER (WHERE rating = 1) AS one_star
               FROM agent_feedback
               WHERE tenant_id = $1""",
            UUID(tenant_id),
        )
        type_rows = await conn.fetch(
            """SELECT feedback_type, COUNT(*) AS cnt
               FROM agent_feedback
               WHERE tenant_id = $1 AND feedback_type IS NOT NULL
               GROUP BY feedback_type
               ORDER BY cnt DESC""",
            UUID(tenant_id),
        )

    avg = float(row["avg_rating"]) if row and row["avg_rating"] else None
    return {
        "total_feedback": row["total_feedback"] if row else 0,
        "avg_rating": round(avg, 2) if avg is not None else None,
        "distribution": {
            "5": row["five_star"] if row else 0,
            "4": row["four_star"] if row else 0,
            "3": row["three_star"] if row else 0,
            "2": row["two_star"] if row else 0,
            "1": row["one_star"] if row else 0,
        },
        "by_type": [{"feedback_type": r["feedback_type"], "count": r["cnt"]} for r in type_rows],
    }
