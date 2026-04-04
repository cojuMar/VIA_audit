from __future__ import annotations

import datetime
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query

from .ai_audit_advisor import AIAuditAdvisor
from .config import settings
from .db import get_pool, init_pool
from .engagement_manager import EngagementManager
from .milestone_manager import MilestoneManager
from .models import (
    EngagementCreate,
    EntityCreate,
    MilestoneCreate,
    PlanCreate,
    PlanItemCreate,
    ResourceAssignmentCreate,
    TimeEntryCreate,
)
from .plan_manager import PlanManager
from .resource_manager import ResourceManager
from .time_tracker import TimeTracker
from .universe_manager import UniverseManager


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = await init_pool(settings.database_url)
    yield
    await pool.close()


app = FastAPI(
    title="Audit Planning Service",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _tenant(x_tenant_id: str | None) -> str:
    if not x_tenant_id:
        raise HTTPException(status_code=400, detail="X-Tenant-ID header is required")
    return x_tenant_id


def _current_year() -> int:
    return datetime.date.today().year


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "audit-planning-service"}


# ---------------------------------------------------------------------------
# Entity / Universe routes
# ---------------------------------------------------------------------------
@app.get("/entity-types")
async def list_entity_types(
    x_tenant_id: str | None = Header(default=None),
) -> list[dict]:
    mgr = UniverseManager(get_pool())
    return await mgr.get_entity_types()


@app.post("/entities", status_code=201)
async def create_entity(
    data: EntityCreate,
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    mgr = UniverseManager(get_pool())
    return await mgr.create_entity(tenant_id, data)


@app.get("/entities")
async def list_entities(
    entity_type_id: str | None = Query(default=None),
    min_risk_score: float | None = Query(default=None),
    in_universe_only: bool = Query(default=True),
    x_tenant_id: str | None = Header(default=None),
) -> list[dict]:
    tenant_id = _tenant(x_tenant_id)
    mgr = UniverseManager(get_pool())
    return await mgr.list_entities(
        tenant_id,
        entity_type_id=entity_type_id,
        min_risk_score=min_risk_score,
        in_universe_only=in_universe_only,
    )


@app.get("/universe/coverage")
async def universe_coverage(
    plan_year: int = Query(default=None),
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    year = plan_year or _current_year()
    mgr = UniverseManager(get_pool())
    return await mgr.calculate_universe_coverage(tenant_id, year)


@app.get("/entities/{entity_id}")
async def get_entity(
    entity_id: str,
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    mgr = UniverseManager(get_pool())
    result = await mgr.get_entity(tenant_id, entity_id)
    if not result:
        raise HTTPException(status_code=404, detail="Entity not found")
    return result


@app.put("/entities/{entity_id}")
async def update_entity(
    entity_id: str,
    updates: dict[str, Any],
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    mgr = UniverseManager(get_pool())
    return await mgr.update_entity(tenant_id, entity_id, updates)


# ---------------------------------------------------------------------------
# Plan routes
# ---------------------------------------------------------------------------
@app.post("/plans", status_code=201)
async def create_plan(
    data: PlanCreate,
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    mgr = PlanManager(get_pool())
    return await mgr.create_plan(tenant_id, data)


@app.get("/plans")
async def list_plans(
    x_tenant_id: str | None = Header(default=None),
) -> list[dict]:
    tenant_id = _tenant(x_tenant_id)
    mgr = PlanManager(get_pool())
    return await mgr.list_plans(tenant_id)


@app.get("/plans/{plan_id}/summary")
async def get_plan_summary(
    plan_id: str,
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    mgr = PlanManager(get_pool())
    return await mgr.get_plan_summary(tenant_id, plan_id)


@app.post("/plans/{plan_id}/approve")
async def approve_plan(
    plan_id: str,
    body: dict[str, Any],
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    approved_by = body.get("approved_by", "")
    mgr = PlanManager(get_pool())
    return await mgr.approve_plan(tenant_id, plan_id, approved_by)


@app.post("/plans/{plan_id}/auto-populate")
async def auto_populate_plan(
    plan_id: str,
    body: dict[str, Any],
    x_tenant_id: str | None = Header(default=None),
) -> list[dict]:
    tenant_id = _tenant(x_tenant_id)
    risk_threshold = float(body.get("risk_threshold", 7.0))
    mgr = PlanManager(get_pool())
    return await mgr.auto_populate_from_universe(
        tenant_id, plan_id, risk_threshold=risk_threshold
    )


@app.get("/plans/{plan_id}/budget-status")
async def plan_budget_status(
    plan_id: str,
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    tracker = TimeTracker(get_pool())
    return await tracker.get_budget_status(tenant_id, plan_id)


@app.get("/plans/{plan_id}")
async def get_plan(
    plan_id: str,
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    mgr = PlanManager(get_pool())
    result = await mgr.get_plan(tenant_id, plan_id)
    if not result:
        raise HTTPException(status_code=404, detail="Plan not found")
    return result


# ---------------------------------------------------------------------------
# Plan item routes
# ---------------------------------------------------------------------------
@app.post("/plan-items", status_code=201)
async def create_plan_item(
    data: PlanItemCreate,
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    mgr = PlanManager(get_pool())
    return await mgr.add_item(tenant_id, data)


@app.put("/plan-items/{item_id}")
async def update_plan_item(
    item_id: str,
    updates: dict[str, Any],
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    mgr = PlanManager(get_pool())
    return await mgr.update_item(tenant_id, item_id, updates)


# ---------------------------------------------------------------------------
# Engagement routes
# ---------------------------------------------------------------------------
@app.post("/engagements", status_code=201)
async def create_engagement(
    data: EngagementCreate,
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    mgr = EngagementManager(get_pool())
    return await mgr.create_engagement(tenant_id, data)


@app.get("/engagements")
async def list_engagements(
    status: str | None = Query(default=None),
    lead_auditor: str | None = Query(default=None),
    x_tenant_id: str | None = Header(default=None),
) -> list[dict]:
    tenant_id = _tenant(x_tenant_id)
    mgr = EngagementManager(get_pool())
    return await mgr.list_engagements(
        tenant_id, status=status, lead_auditor=lead_auditor
    )


@app.get("/gantt")
async def gantt_data(
    plan_id: str | None = Query(default=None),
    x_tenant_id: str | None = Header(default=None),
) -> list[dict]:
    tenant_id = _tenant(x_tenant_id)
    mgr = EngagementManager(get_pool())
    return await mgr.get_gantt_data(tenant_id, plan_id=plan_id)


@app.get("/engagements/{eng_id}/hours")
async def engagement_hours(
    eng_id: str,
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    tracker = TimeTracker(get_pool())
    return await tracker.get_engagement_hours(tenant_id, eng_id)


@app.get("/engagements/{eng_id}/milestones")
async def list_engagement_milestones(
    eng_id: str,
    x_tenant_id: str | None = Header(default=None),
) -> list[dict]:
    tenant_id = _tenant(x_tenant_id)
    mgr = MilestoneManager(get_pool())
    return await mgr.get_engagement_milestones(tenant_id, eng_id)


@app.post("/engagements/{eng_id}/milestones/seed", status_code=201)
async def seed_milestones(
    eng_id: str,
    body: dict[str, Any],
    x_tenant_id: str | None = Header(default=None),
) -> list[dict]:
    tenant_id = _tenant(x_tenant_id)
    planned_start = body.get("planned_start")
    planned_end = body.get("planned_end")
    if not planned_start or not planned_end:
        raise HTTPException(
            status_code=400,
            detail="planned_start and planned_end are required",
        )
    mgr = MilestoneManager(get_pool())
    return await mgr.seed_default_milestones(
        tenant_id, eng_id, planned_start, planned_end
    )


@app.get("/engagements/{eng_id}/resources")
async def list_engagement_resources(
    eng_id: str,
    x_tenant_id: str | None = Header(default=None),
) -> list[dict]:
    tenant_id = _tenant(x_tenant_id)
    mgr = ResourceManager(get_pool())
    return await mgr.list_for_engagement(tenant_id, eng_id)


@app.post("/engagements/{eng_id}/transition")
async def transition_engagement(
    eng_id: str,
    body: dict[str, Any],
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    new_status = body.get("new_status")
    if not new_status:
        raise HTTPException(status_code=400, detail="new_status is required")
    notes = body.get("notes")
    mgr = EngagementManager(get_pool())
    try:
        return await mgr.transition_status(tenant_id, eng_id, new_status, notes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.put("/engagements/{eng_id}")
async def update_engagement(
    eng_id: str,
    updates: dict[str, Any],
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    mgr = EngagementManager(get_pool())
    return await mgr.update_engagement(tenant_id, eng_id, updates)


@app.get("/engagements/{eng_id}")
async def get_engagement(
    eng_id: str,
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    mgr = EngagementManager(get_pool())
    result = await mgr.get_engagement(tenant_id, eng_id)
    if not result:
        raise HTTPException(status_code=404, detail="Engagement not found")
    return result


# ---------------------------------------------------------------------------
# Time tracking routes
# ---------------------------------------------------------------------------
@app.post("/time-entries", status_code=201)
async def log_time(
    data: TimeEntryCreate,
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    tracker = TimeTracker(get_pool())
    return await tracker.log_hours(tenant_id, data)


@app.get("/time-entries")
async def get_time_entries(
    engagement_id: str | None = Query(default=None),
    auditor_email: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    x_tenant_id: str | None = Header(default=None),
) -> list[dict]:
    tenant_id = _tenant(x_tenant_id)
    tracker = TimeTracker(get_pool())
    return await tracker.get_time_report(
        tenant_id,
        engagement_id=engagement_id,
        auditor_email=auditor_email,
        start_date=start_date,
        end_date=end_date,
    )


@app.get("/utilization")
async def auditor_utilization(
    start_date: str = Query(...),
    end_date: str = Query(...),
    x_tenant_id: str | None = Header(default=None),
) -> list[dict]:
    tenant_id = _tenant(x_tenant_id)
    tracker = TimeTracker(get_pool())
    return await tracker.get_auditor_utilization(tenant_id, start_date, end_date)


# ---------------------------------------------------------------------------
# Milestone routes (static paths before parameterized)
# ---------------------------------------------------------------------------
@app.get("/milestones/overdue")
async def overdue_milestones(
    x_tenant_id: str | None = Header(default=None),
) -> list[dict]:
    tenant_id = _tenant(x_tenant_id)
    mgr = MilestoneManager(get_pool())
    return await mgr.check_overdue_milestones(tenant_id)


@app.post("/milestones", status_code=201)
async def create_milestone(
    data: MilestoneCreate,
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    mgr = MilestoneManager(get_pool())
    return await mgr.create_milestone(tenant_id, data)


@app.post("/milestones/{milestone_id}/complete")
async def complete_milestone(
    milestone_id: str,
    body: dict[str, Any],
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    completed_date = body.get("completed_date")
    mgr = MilestoneManager(get_pool())
    return await mgr.complete_milestone(tenant_id, milestone_id, completed_date)


# ---------------------------------------------------------------------------
# Resource routes (static paths before parameterized)
# ---------------------------------------------------------------------------
@app.get("/resources/schedule")
async def auditor_schedule(
    auditor_email: str = Query(...),
    start_date: str = Query(...),
    end_date: str = Query(...),
    x_tenant_id: str | None = Header(default=None),
) -> list[dict]:
    tenant_id = _tenant(x_tenant_id)
    mgr = ResourceManager(get_pool())
    return await mgr.get_auditor_schedule(
        tenant_id, auditor_email, start_date, end_date
    )


@app.get("/resources/availability")
async def team_availability(
    start_date: str = Query(...),
    end_date: str = Query(...),
    x_tenant_id: str | None = Header(default=None),
) -> list[dict]:
    tenant_id = _tenant(x_tenant_id)
    mgr = ResourceManager(get_pool())
    return await mgr.get_team_availability(tenant_id, start_date, end_date)


@app.post("/resources", status_code=201)
async def assign_resource(
    data: ResourceAssignmentCreate,
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    mgr = ResourceManager(get_pool())
    return await mgr.assign(tenant_id, data)


# ---------------------------------------------------------------------------
# AI routes
# ---------------------------------------------------------------------------
@app.post("/ai/suggest-scope")
async def ai_suggest_scope(
    body: dict[str, Any],
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    entity_id = body.get("entity_id")
    if not entity_id:
        raise HTTPException(status_code=400, detail="entity_id is required")

    include_risk_context = body.get("include_risk_context", False)
    universe_mgr = UniverseManager(get_pool())
    entity = await universe_mgr.get_entity(tenant_id, entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    risk_context: dict = {}
    if include_risk_context:
        # Fetch risk context from risk service if desired (best-effort)
        try:
            import httpx

            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{settings.risk_service_url}/risks",
                    headers={"X-Tenant-ID": tenant_id},
                    params={"entity_id": entity_id},
                )
                if resp.status_code == 200:
                    risk_context = {"risks": resp.json()}
        except Exception:
            pass

    advisor = AIAuditAdvisor(settings.anthropic_api_key)
    return await advisor.suggest_audit_scope(entity, risk_context)


@app.post("/ai/generate-program")
async def ai_generate_program(
    body: dict[str, Any],
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    engagement_id = body.get("engagement_id")
    if not engagement_id:
        raise HTTPException(status_code=400, detail="engagement_id is required")

    eng_mgr = EngagementManager(get_pool())
    engagement = await eng_mgr.get_engagement(tenant_id, engagement_id)
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")

    advisor = AIAuditAdvisor(settings.anthropic_api_key)
    program = await advisor.generate_audit_program(engagement)
    return {"engagement_id": engagement_id, "audit_program": program}


@app.post("/ai/prioritize-universe")
async def ai_prioritize_universe(
    body: dict[str, Any],
    x_tenant_id: str | None = Header(default=None),
) -> list[dict]:
    tenant_id = _tenant(x_tenant_id)
    limit = int(body.get("limit", 20))

    universe_mgr = UniverseManager(get_pool())
    entities = await universe_mgr.list_entities(tenant_id, in_universe_only=True)
    entities = entities[:limit]

    advisor = AIAuditAdvisor(settings.anthropic_api_key)
    return await advisor.prioritize_universe(entities)
