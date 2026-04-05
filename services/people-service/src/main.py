from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import date
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from minio import Minio
from minio.error import S3Error

from .background_check_manager import BackgroundCheckManager
from .compliance_scorer import ComplianceScorer
from .config import settings
from .db import close_pool, get_pool, init_pool
from .employee_manager import EmployeeManager
from .escalation_engine import EscalationEngine
from .models import (
    AcknowledgmentRecord,
    BackgroundCheckCreate,
    EmployeeCreate,
    PolicyCreate,
    TrainingAssignmentCreate,
    TrainingCompletion,
    TrainingCourseCreate,
)
from .policy_manager import PolicyManager
from .training_manager import TrainingManager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Singleton managers
# ---------------------------------------------------------------------------
employee_mgr = EmployeeManager()
policy_mgr = PolicyManager()
training_mgr = TrainingManager()
bgcheck_mgr = BackgroundCheckManager()
compliance_scorer = ComplianceScorer()
escalation_engine = EscalationEngine(settings)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start-up
    pool = await init_pool(settings.database_url)

    # Ensure MinIO bucket exists
    try:
        minio_client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=False,
        )
        if not minio_client.bucket_exists(settings.minio_bucket_people):
            minio_client.make_bucket(settings.minio_bucket_people)
    except S3Error as exc:
        logger.warning("MinIO bucket init error: %s", exc)

    escalation_engine.start(pool)

    yield

    # Shutdown
    escalation_engine.stop()
    await close_pool()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="people-service",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

def get_db():
    return get_pool()


def get_tenant_id(x_tenant_id: str = Header(...)) -> str:
    return x_tenant_id


def get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok", "service": "people-service"}


# ===========================================================================
# Employees
# ===========================================================================

@app.get("/employees/summary")
async def get_employee_summary(
    pool=Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    return await employee_mgr.get_summary(pool, tenant_id)


@app.get("/employees")
async def list_employees(
    department: str | None = None,
    job_role: str | None = None,
    status: str | None = None,
    pool=Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    if status and status != "active":
        # For non-active we do a broader query
        from .db import tenant_conn

        conditions = ["tenant_id=$1"]
        params: list = [tenant_id]
        idx = 2
        if department:
            conditions.append(f"department=${idx}")
            params.append(department)
            idx += 1
        if job_role:
            conditions.append(f"job_role=${idx}")
            params.append(job_role)
            idx += 1
        if status:
            conditions.append(f"employment_status=${idx}")
            params.append(status)
            idx += 1
        query = (
            f"SELECT * FROM employees WHERE {' AND '.join(conditions)} ORDER BY full_name"
        )
        async with tenant_conn(pool, tenant_id) as conn:
            rows = await conn.fetch(query, *params)
            return [dict(r) for r in rows]
    return await employee_mgr.list_active(pool, tenant_id, department=department, job_role=job_role)


@app.post("/employees", status_code=201)
async def create_employee(
    data: EmployeeCreate,
    pool=Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    return await employee_mgr.create(pool, tenant_id, data)


@app.post("/employees/bulk", status_code=201)
async def bulk_upsert_employees(
    employees: list[EmployeeCreate],
    pool=Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    return await employee_mgr.bulk_upsert(pool, tenant_id, employees)


@app.get("/employees/{employee_id}")
async def get_employee(
    employee_id: str,
    pool=Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    emp = await employee_mgr.get(pool, tenant_id, employee_id)
    if emp is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    # Attach a lightweight compliance summary
    try:
        score = await compliance_scorer.score_employee(pool, tenant_id, emp)
        emp["compliance_summary"] = {
            "overall_score": score.overall_score,
            "status": score.status,
            "open_items": score.open_items,
        }
    except Exception as exc:
        logger.warning("Could not compute compliance for %s: %s", employee_id, exc)
        emp["compliance_summary"] = None
    return emp


@app.get("/employees/{employee_id}/compliance")
async def get_employee_compliance(
    employee_id: str,
    pool=Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    emp = await employee_mgr.get(pool, tenant_id, employee_id)
    if emp is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    return await compliance_scorer.score_employee(pool, tenant_id, emp)


@app.put("/employees/{employee_id}/status")
async def update_employee_status(
    employee_id: str,
    body: dict[str, Any],
    pool=Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    status = body.get("status")
    if not status:
        raise HTTPException(status_code=422, detail="'status' field required")
    try:
        return await employee_mgr.update_status(pool, tenant_id, employee_id, status)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ===========================================================================
# Policies
# ===========================================================================

@app.get("/policies/compliance-rate")
async def get_policy_compliance_rate(
    pool=Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    return await policy_mgr.get_policy_compliance_rate(pool, tenant_id)


@app.get("/policies/overdue")
async def get_overdue_acknowledgments(
    pool=Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    return await policy_mgr.get_overdue_acknowledgments(pool, tenant_id)


@app.get("/policies")
async def list_policies(
    category: str | None = None,
    pool=Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    return await policy_mgr.list_policies(pool, tenant_id, category=category)


@app.post("/policies", status_code=201)
async def create_policy(
    data: PolicyCreate,
    pool=Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    return await policy_mgr.create_policy(pool, tenant_id, data)


@app.put("/policies/{policy_id}")
async def update_policy(
    policy_id: str,
    body: dict[str, Any],
    pool=Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    change_summary = body.pop("change_summary", "Policy updated")
    try:
        return await policy_mgr.update_policy(pool, tenant_id, policy_id, body, change_summary)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/policies/{policy_id}/acknowledge", status_code=201)
async def acknowledge_policy(
    policy_id: str,
    data: AcknowledgmentRecord,
    request: Request,
    pool=Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    # Override policy_id from path
    data.policy_id = policy_id
    ip = get_client_ip(request)
    user_agent = request.headers.get("User-Agent", "")
    return await policy_mgr.record_acknowledgment(pool, tenant_id, data, ip, user_agent)


# ===========================================================================
# Training
# ===========================================================================

@app.get("/training/courses")
async def list_training_courses(
    category: str | None = None,
    pool=Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    return await training_mgr.list_courses(pool, tenant_id, category=category)


@app.post("/training/courses", status_code=201)
async def create_training_course(
    data: TrainingCourseCreate,
    pool=Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    return await training_mgr.create_course(pool, tenant_id, data)


@app.post("/training/assign", status_code=201)
async def assign_training(
    data: TrainingAssignmentCreate,
    pool=Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    try:
        return await training_mgr.assign_course(pool, tenant_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.post("/training/bulk-assign", status_code=201)
async def bulk_assign_training(
    body: dict[str, Any],
    pool=Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    course_id = body.get("course_id")
    employee_ids = body.get("employee_ids", [])
    due_date_raw = body.get("due_date")
    if not course_id:
        raise HTTPException(status_code=422, detail="'course_id' required")
    due_date = date.fromisoformat(due_date_raw) if due_date_raw else None
    return await training_mgr.bulk_assign(pool, tenant_id, course_id, employee_ids, due_date)


@app.post("/training/complete", status_code=201)
async def record_training_completion(
    data: TrainingCompletion,
    pool=Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    return await training_mgr.record_completion(pool, tenant_id, data)


@app.get("/training/assignments/{employee_id}")
async def get_employee_training(
    employee_id: str,
    pool=Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    return await training_mgr.get_employee_training_status(pool, tenant_id, employee_id)


@app.get("/training/overdue")
async def get_overdue_training(
    pool=Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    return await training_mgr.get_overdue_assignments(pool, tenant_id)


@app.get("/training/compliance-rate")
async def get_training_compliance_rate(
    pool=Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    return await training_mgr.get_training_compliance_rate(pool, tenant_id)


# ===========================================================================
# Background Checks
# ===========================================================================

@app.get("/background-checks/summary")
async def get_bgcheck_summary(
    pool=Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    return await bgcheck_mgr.get_summary(pool, tenant_id)


@app.get("/background-checks/expiring")
async def get_expiring_checks(
    pool=Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    return await bgcheck_mgr.get_expired_or_expiring(
        pool, tenant_id, settings.background_check_expiry_warning_days
    )


@app.get("/background-checks")
async def list_background_checks(
    employee_id: str | None = None,
    status: str | None = None,
    pool=Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    from .db import tenant_conn

    conditions = ["tenant_id=$1"]
    params: list = [tenant_id]
    idx = 2
    if employee_id:
        conditions.append(f"employee_id=${idx}")
        params.append(employee_id)
        idx += 1
    if status:
        conditions.append(f"status=${idx}")
        params.append(status)
        idx += 1

    query = (
        f"SELECT * FROM background_checks WHERE {' AND '.join(conditions)} "
        f"ORDER BY created_at DESC"
    )
    async with tenant_conn(pool, tenant_id) as conn:
        rows = await conn.fetch(query, *params)
        return [dict(r) for r in rows]


@app.post("/background-checks", status_code=201)
async def initiate_background_check(
    data: BackgroundCheckCreate,
    pool=Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    return await bgcheck_mgr.initiate(pool, tenant_id, data)


@app.put("/background-checks/{check_id}")
async def update_background_check(
    check_id: str,
    body: dict[str, Any],
    pool=Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    status = body.get("status")
    if not status:
        raise HTTPException(status_code=422, detail="'status' field required")
    completed_at_raw = body.get("completed_at")
    completed_at = date.fromisoformat(completed_at_raw) if completed_at_raw else None
    try:
        return await bgcheck_mgr.update_status(
            pool,
            tenant_id,
            check_id,
            status=status,
            result_summary=body.get("result_summary"),
            adjudication=body.get("adjudication"),
            completed_at=completed_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ===========================================================================
# Compliance Scoring
# ===========================================================================

@app.get("/compliance/scores")
async def get_all_compliance_scores(
    pool=Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    scores = await compliance_scorer.score_all_employees(pool, tenant_id)
    return [s.model_dump() for s in scores]


@app.get("/compliance/summary")
async def get_compliance_summary(
    pool=Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    return await compliance_scorer.get_org_compliance_summary(pool, tenant_id)


@app.get("/compliance/scores/{employee_id}")
async def get_employee_compliance_score(
    employee_id: str,
    pool=Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    emp = await employee_mgr.get(pool, tenant_id, employee_id)
    if emp is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    score = await compliance_scorer.score_employee(pool, tenant_id, emp)
    return score.model_dump()


# ===========================================================================
# Escalations
# ===========================================================================

@app.get("/escalations/summary")
async def get_escalation_summary(
    pool=Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    from .db import tenant_conn

    async with tenant_conn(pool, tenant_id) as conn:
        total_row = await conn.fetchrow(
            "SELECT COUNT(*) AS total FROM compliance_escalations WHERE tenant_id=$1",
            tenant_id,
        )
        type_rows = await conn.fetch(
            """
            SELECT escalation_type, COUNT(*) AS cnt
            FROM compliance_escalations
            WHERE tenant_id=$1
            GROUP BY escalation_type
            """,
            tenant_id,
        )
        open_row = await conn.fetchrow(
            "SELECT COUNT(*) AS cnt FROM compliance_escalations WHERE tenant_id=$1 AND resolved=FALSE",
            tenant_id,
        )
    return {
        "total": total_row["total"],
        "by_type": {r["escalation_type"]: r["cnt"] for r in type_rows},
        "open_count": open_row["cnt"],
    }


@app.get("/escalations")
async def list_escalations(
    type: str | None = None,
    employee_id: str | None = None,
    resolved: bool | None = None,
    pool=Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    from .db import tenant_conn

    conditions = ["tenant_id=$1"]
    params: list = [tenant_id]
    idx = 2
    if type:
        conditions.append(f"escalation_type=${idx}")
        params.append(type)
        idx += 1
    if employee_id:
        conditions.append(f"employee_id=${idx}")
        params.append(employee_id)
        idx += 1
    if resolved is not None:
        conditions.append(f"resolved=${idx}")
        params.append(resolved)
        idx += 1

    query = (
        f"SELECT * FROM compliance_escalations WHERE {' AND '.join(conditions)} "
        f"ORDER BY escalated_at DESC"
    )
    async with tenant_conn(pool, tenant_id) as conn:
        rows = await conn.fetch(query, *params)
        return [dict(r) for r in rows]


@app.post("/escalations/run")
async def run_escalation_check(
    pool=Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    return await escalation_engine.run_all(pool)
