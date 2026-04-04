from __future__ import annotations

import datetime
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query

from .ai_esg_advisor import AIESGAdvisor
from .board_manager import BoardManager
from .config import settings
from .db import get_pool, init_pool
from .esg_manager import ESGManager
from .models import (
    AgendaItemCreate,
    CommitteeCreate,
    DisclosureCreate,
    MeetingCreate,
    PackageCreate,
    TargetCreate,
)
from .package_manager import PackageManager


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = await init_pool(settings.database_url)
    yield
    await pool.close()


app = FastAPI(
    title="ESG Board Service",
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


def _advisor() -> AIESGAdvisor:
    return AIESGAdvisor(api_key=settings.anthropic_api_key)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "esg-board-service"}


# ---------------------------------------------------------------------------
# ESG Framework / Metrics routes (platform data — no tenant required)
# ---------------------------------------------------------------------------

@app.get("/esg/frameworks")
async def list_frameworks(
    category: str | None = Query(default=None),
    x_tenant_id: str | None = Header(default=None),
) -> list[dict]:
    mgr = ESGManager(get_pool())
    return await mgr.get_frameworks(category=category)


@app.get("/esg/metric-definitions")
async def list_metric_definitions(
    category: str | None = Query(default=None),
    framework_id: str | None = Query(default=None),
    x_tenant_id: str | None = Header(default=None),
) -> list[dict]:
    mgr = ESGManager(get_pool())
    return await mgr.get_metric_definitions(
        category=category, framework_id=framework_id
    )


# ---------------------------------------------------------------------------
# ESG Disclosures
# ---------------------------------------------------------------------------

@app.post("/esg/disclosures", status_code=201)
async def submit_disclosure(
    data: DisclosureCreate,
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    mgr = ESGManager(get_pool())
    try:
        return await mgr.submit_disclosure(tenant_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.get("/esg/disclosures")
async def list_disclosures(
    reporting_period: str | None = Query(default=None),
    category: str | None = Query(default=None),
    metric_id: str | None = Query(default=None),
    x_tenant_id: str | None = Header(default=None),
) -> list[dict]:
    tenant_id = _tenant(x_tenant_id)
    mgr = ESGManager(get_pool())
    return await mgr.get_disclosures(
        tenant_id,
        reporting_period=reporting_period,
        category=category,
        metric_id=metric_id,
    )


# NOTE: static sub-paths before parameterised ones

@app.get("/esg/scorecard")
async def get_esg_scorecard(
    reporting_period: str = Query(...),
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    mgr = ESGManager(get_pool())
    return await mgr.get_esg_scorecard(tenant_id, reporting_period)


@app.get("/esg/trend")
async def get_trend_data(
    metric_id: str = Query(...),
    periods: int = Query(default=8),
    x_tenant_id: str | None = Header(default=None),
) -> list[dict]:
    tenant_id = _tenant(x_tenant_id)
    mgr = ESGManager(get_pool())
    return await mgr.get_trend_data(tenant_id, metric_id, periods)


# ---------------------------------------------------------------------------
# ESG Targets
# ---------------------------------------------------------------------------

@app.post("/esg/targets", status_code=201)
async def upsert_target(
    data: TargetCreate,
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    mgr = ESGManager(get_pool())
    return await mgr.upsert_target(tenant_id, data)


@app.get("/esg/targets/progress")
async def get_target_progress(
    target_year: int = Query(...),
    x_tenant_id: str | None = Header(default=None),
) -> list[dict]:
    tenant_id = _tenant(x_tenant_id)
    mgr = ESGManager(get_pool())
    return await mgr.get_target_progress(tenant_id, target_year)


@app.get("/esg/targets")
async def list_targets(
    metric_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    x_tenant_id: str | None = Header(default=None),
) -> list[dict]:
    tenant_id = _tenant(x_tenant_id)
    mgr = ESGManager(get_pool())
    return await mgr.get_targets(tenant_id, metric_id=metric_id, status=status)


# ---------------------------------------------------------------------------
# Board Committees
# ---------------------------------------------------------------------------

@app.post("/board/committees", status_code=201)
async def create_committee(
    data: CommitteeCreate,
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    mgr = BoardManager(get_pool())
    return await mgr.create_committee(tenant_id, data)


@app.get("/board/committees")
async def list_committees(
    active_only: bool = Query(default=True),
    x_tenant_id: str | None = Header(default=None),
) -> list[dict]:
    tenant_id = _tenant(x_tenant_id)
    mgr = BoardManager(get_pool())
    return await mgr.list_committees(tenant_id, active_only=active_only)


@app.put("/board/committees/{committee_id}")
async def update_committee(
    committee_id: str,
    updates: dict[str, Any],
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    mgr = BoardManager(get_pool())
    try:
        return await mgr.update_committee(tenant_id, committee_id, updates)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ---------------------------------------------------------------------------
# Board Meetings
# ---------------------------------------------------------------------------

@app.post("/board/meetings", status_code=201)
async def create_meeting(
    data: MeetingCreate,
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    mgr = BoardManager(get_pool())
    return await mgr.create_meeting(tenant_id, data)


@app.get("/board/meetings")
async def list_meetings(
    status: str | None = Query(default=None),
    committee_id: str | None = Query(default=None),
    upcoming_only: bool = Query(default=False),
    x_tenant_id: str | None = Header(default=None),
) -> list[dict]:
    tenant_id = _tenant(x_tenant_id)
    mgr = BoardManager(get_pool())
    return await mgr.list_meetings(
        tenant_id,
        status=status,
        committee_id=committee_id,
        upcoming_only=upcoming_only,
    )


# Static sub-paths before /{meeting_id}

@app.get("/board/calendar")
async def get_board_calendar(
    year: int = Query(default=None),
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    mgr = BoardManager(get_pool())
    return await mgr.get_board_calendar(tenant_id, year or _current_year())


@app.get("/board/meetings/{meeting_id}")
async def get_meeting(
    meeting_id: str,
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    mgr = BoardManager(get_pool())
    try:
        return await mgr.get_meeting(tenant_id, meeting_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.put("/board/meetings/{meeting_id}")
async def update_meeting(
    meeting_id: str,
    updates: dict[str, Any],
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    mgr = BoardManager(get_pool())
    try:
        return await mgr.update_meeting(tenant_id, meeting_id, updates)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/board/meetings/{meeting_id}/complete")
async def complete_meeting(
    meeting_id: str,
    body: dict[str, Any],
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    minutes_text: str = body.get("minutes_text", "")
    attendees: list[str] = body.get("attendees", [])
    quorum_met: bool = body.get("quorum_met", False)
    mgr = BoardManager(get_pool())
    try:
        return await mgr.complete_meeting(
            tenant_id, meeting_id, minutes_text, attendees, quorum_met
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/board/meetings/{meeting_id}/approve-minutes")
async def approve_minutes(
    meeting_id: str,
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    mgr = BoardManager(get_pool())
    try:
        return await mgr.approve_minutes(tenant_id, meeting_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ---------------------------------------------------------------------------
# Agenda Items
# ---------------------------------------------------------------------------

@app.post("/board/agenda-items", status_code=201)
async def add_agenda_item(
    data: AgendaItemCreate,
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    mgr = BoardManager(get_pool())
    return await mgr.add_agenda_item(tenant_id, data)


@app.put("/board/agenda-items/{item_id}")
async def update_agenda_item(
    item_id: str,
    updates: dict[str, Any],
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    mgr = BoardManager(get_pool())
    try:
        return await mgr.update_agenda_item(tenant_id, item_id, updates)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ---------------------------------------------------------------------------
# Board Packages
# NOTE: static /build/* paths MUST be declared before /{package_id}
# ---------------------------------------------------------------------------

@app.post("/board/packages/build/esg", status_code=201)
async def build_esg_package(
    body: dict[str, Any],
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    reporting_period: str = body.get("reporting_period", "")
    if not reporting_period:
        raise HTTPException(
            status_code=422, detail="reporting_period is required"
        )
    meeting_id: str | None = body.get("meeting_id")
    mgr = PackageManager(get_pool())
    return await mgr.build_esg_package(
        tenant_id,
        reporting_period=reporting_period,
        meeting_id=meeting_id,
        ai_advisor=_advisor(),
    )


@app.post("/board/packages/build/audit-committee", status_code=201)
async def build_audit_committee_package(
    body: dict[str, Any],
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    reporting_period: str = body.get("reporting_period", "")
    if not reporting_period:
        raise HTTPException(
            status_code=422, detail="reporting_period is required"
        )
    meeting_id: str | None = body.get("meeting_id")
    mgr = PackageManager(get_pool())
    return await mgr.build_audit_committee_package(
        tenant_id,
        reporting_period=reporting_period,
        meeting_id=meeting_id,
        ai_advisor=_advisor(),
    )


@app.post("/board/packages", status_code=201)
async def create_package(
    data: PackageCreate,
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    mgr = PackageManager(get_pool())
    return await mgr.create_package(tenant_id, data)


@app.get("/board/packages")
async def list_packages(
    package_type: str | None = Query(default=None),
    meeting_id: str | None = Query(default=None),
    x_tenant_id: str | None = Header(default=None),
) -> list[dict]:
    tenant_id = _tenant(x_tenant_id)
    mgr = PackageManager(get_pool())
    return await mgr.list_packages(
        tenant_id, package_type=package_type, meeting_id=meeting_id
    )


@app.get("/board/packages/{package_id}")
async def get_package(
    package_id: str,
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    mgr = PackageManager(get_pool())
    try:
        return await mgr.get_package(tenant_id, package_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/board/packages/{package_id}/items", status_code=201)
async def add_package_item(
    package_id: str,
    body: dict[str, Any],
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    mgr = PackageManager(get_pool())
    return await mgr.add_package_item(
        tenant_id=tenant_id,
        package_id=package_id,
        sequence_number=body.get("sequence_number", 1),
        section_title=body.get("section_title", ""),
        content_type=body.get("content_type", "generic"),
        content_data=body.get("content_data", {}),
        source_service=body.get("source_service"),
        is_confidential=body.get("is_confidential", False),
    )


# ---------------------------------------------------------------------------
# AI routes
# ---------------------------------------------------------------------------

@app.post("/ai/esg-narrative")
async def ai_esg_narrative(
    body: dict[str, Any],
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    reporting_period: str = body.get("reporting_period", "")
    if not reporting_period:
        raise HTTPException(
            status_code=422, detail="reporting_period is required"
        )
    esg_mgr = ESGManager(get_pool())
    scorecard = await esg_mgr.get_esg_scorecard(tenant_id, reporting_period)
    targets = await esg_mgr.get_targets(tenant_id)
    narrative = await _advisor().generate_esg_narrative(
        scorecard=scorecard, targets=targets, reporting_period=reporting_period
    )
    return {"reporting_period": reporting_period, "narrative": narrative}


@app.post("/ai/board-pack-summary")
async def ai_board_pack_summary(
    body: dict[str, Any],
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    package_id: str = body.get("package_id", "")
    if not package_id:
        raise HTTPException(status_code=422, detail="package_id is required")
    pkg_mgr = PackageManager(get_pool())
    try:
        package = await pkg_mgr.get_package(tenant_id, package_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    summary = await _advisor().generate_board_pack_summary(
        package_items=package.get("items", []),
        package_type=package.get("package_type", "board_pack"),
    )
    return {"package_id": package_id, "summary": summary}


@app.post("/ai/materiality-assessment")
async def ai_materiality_assessment(
    body: dict[str, Any],
    x_tenant_id: str | None = Header(default=None),
) -> dict:
    tenant_id = _tenant(x_tenant_id)
    entity_type: str = body.get("entity_type", "")
    industry: str = body.get("industry", "")
    esg_mgr = ESGManager(get_pool())
    metrics = await esg_mgr.get_metric_definitions()
    result = await _advisor().assess_esg_materiality(
        entity_type=entity_type, industry=industry, metrics=metrics
    )
    return result


@app.post("/ai/suggest-targets")
async def ai_suggest_targets(
    body: dict[str, Any],
    x_tenant_id: str | None = Header(default=None),
) -> list[dict]:
    tenant_id = _tenant(x_tenant_id)
    reporting_period: str = body.get("reporting_period", "")
    esg_mgr = ESGManager(get_pool())
    disclosures = await esg_mgr.get_disclosures(
        tenant_id, reporting_period=reporting_period or None
    )
    suggestions = await _advisor().suggest_esg_targets(
        current_disclosures=disclosures,
        peer_benchmarks=body.get("peer_benchmarks"),
    )
    return suggestions
