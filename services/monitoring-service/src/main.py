"""
Monitoring Service — FastAPI application (port 3016)

Routes:
  POST /analyze/payroll
  POST /analyze/invoices
  POST /analyze/card-spend
  POST /analyze/sod
  POST /analyze/cloud-config

  GET  /findings
  GET  /findings/summary
  GET  /findings/trend
  GET  /findings/{finding_id}

  GET  /rules
  GET  /rules/{rule_key}
  GET  /config
  POST /config/{rule_key}

  GET  /sod/rules
  GET  /sod/violations
  GET  /sod/violations/summary

  GET  /cloud/snapshots
  GET  /cloud/snapshots/summary

  GET  /runs
  GET  /runs/{run_id}

  GET  /health
"""

import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import asyncpg
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from minio import Minio
from pydantic import BaseModel

from .card_spend_analyzer import CardSpendAnalyzer
from .cloud_config_checker import CloudConfigChecker
from .config import settings
from .db import close_pool, get_pool
from .finding_manager import FindingManager
from .invoice_analyzer import InvoiceAnalyzer
from .models import (
    CardTransaction,
    CloudResourceConfig,
    InvoiceRecord,
    MonitoringFinding,
    PayrollRecord,
    UserAccessRecord,
)
from .payroll_analyzer import PayrollAnalyzer
from .scheduler import MonitoringScheduler
from .sod_engine import SoDEngine

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ---------------------------------------------------------------------------
# Module-level singletons
# ---------------------------------------------------------------------------
_pool: asyncpg.Pool | None = None
_minio_client: Minio | None = None
_scheduler: MonitoringScheduler | None = None
_finding_manager = FindingManager()
_payroll_analyzer = PayrollAnalyzer(settings)
_invoice_analyzer = InvoiceAnalyzer(settings)
_card_analyzer = CardSpendAnalyzer()
_sod_engine = SoDEngine()
_cloud_checker = CloudConfigChecker()


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool, _minio_client, _scheduler

    _pool = await get_pool()
    logger.info("DB pool created")

    # MinIO client + bucket creation
    try:
        _minio_client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=False,
        )
        if not _minio_client.bucket_exists(settings.minio_bucket_monitoring):
            _minio_client.make_bucket(settings.minio_bucket_monitoring)
            logger.info("Created MinIO bucket: %s", settings.minio_bucket_monitoring)
    except Exception as exc:
        logger.warning("MinIO unavailable: %s", exc)

    # APScheduler
    _scheduler = MonitoringScheduler(settings)
    _scheduler.start(_pool)

    yield

    if _scheduler:
        _scheduler.stop()
    await close_pool()
    logger.info("monitoring-service shut down")


app = FastAPI(
    title="Aegis Monitoring Service",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

def get_db() -> asyncpg.Pool:
    if _pool is None:
        raise HTTPException(503, "DB pool not ready")
    return _pool


async def get_tenant_id(x_tenant_id: str = Header(..., alias="X-Tenant-ID")) -> str:
    try:
        uuid.UUID(x_tenant_id)
    except ValueError:
        raise HTTPException(400, "X-Tenant-ID must be a valid UUID")
    return x_tenant_id


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


# ---------------------------------------------------------------------------
# Helper: create a monitoring_run record (INSERT, immutable)
# ---------------------------------------------------------------------------

async def _insert_run(
    pool: asyncpg.Pool,
    tenant_id: str,
    rule_key: str,
    status: str,
    triggered_by: str,
    findings_count: int | None = None,
    records_processed: int | None = None,
    completed_at: datetime | None = None,
    run_id: str | None = None,
) -> str:
    rid = run_id or str(uuid.uuid4())
    await pool.execute(
        """
        INSERT INTO monitoring_runs
            (id, tenant_id, rule_key, status, triggered_by,
             findings_count, records_processed, completed_at, created_at)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,NOW())
        """,
        rid,
        tenant_id,
        rule_key,
        status,
        triggered_by,
        findings_count,
        records_processed,
        completed_at,
    )
    return rid


# ---------------------------------------------------------------------------
# Request/response bodies
# ---------------------------------------------------------------------------

class AnalyzePayrollRequest(BaseModel):
    records: list[PayrollRecord]
    save_results: bool = True


class AnalyzeInvoicesRequest(BaseModel):
    records: list[InvoiceRecord]
    save_results: bool = True


class AnalyzeCardSpendRequest(BaseModel):
    records: list[CardTransaction]
    save_results: bool = True


class AnalyzeSoDRequest(BaseModel):
    users: list[UserAccessRecord]
    save_results: bool = True


class AnalyzeCloudConfigRequest(BaseModel):
    resources: list[CloudResourceConfig]
    save_results: bool = True


class ConfigUpdateRequest(BaseModel):
    is_enabled: bool | None = None
    schedule_interval: str | None = None
    config_overrides: dict | None = None


# ---------------------------------------------------------------------------
# Shared analysis helper
# ---------------------------------------------------------------------------

async def _run_analysis(
    pool: asyncpg.Pool,
    tenant_id: str,
    rule_key: str,
    findings: list[MonitoringFinding],
    records_processed: int,
    save_results: bool,
    triggered_by: str = "api",
) -> dict:
    completed_at = datetime.now(timezone.utc)

    run_id = await _insert_run(
        pool,
        tenant_id=tenant_id,
        rule_key=rule_key,
        status="completed",
        triggered_by=triggered_by,
        findings_count=len(findings),
        records_processed=records_processed,
        completed_at=completed_at,
    )

    if save_results and findings:
        await _finding_manager.save_findings(pool, tenant_id, run_id, None, findings)

    return {
        "run_id": run_id,
        "findings_count": len(findings),
        "records_processed": records_processed,
        "findings": [f.model_dump() for f in findings],
    }


# ---------------------------------------------------------------------------
# Analysis endpoints
# ---------------------------------------------------------------------------

@app.post("/analyze/payroll")
async def analyze_payroll(
    body: AnalyzePayrollRequest,
    pool: asyncpg.Pool = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    findings = _payroll_analyzer.analyze(body.records)
    return await _run_analysis(
        pool, tenant_id, "payroll_analysis", findings, len(body.records), body.save_results
    )


@app.post("/analyze/invoices")
async def analyze_invoices(
    body: AnalyzeInvoicesRequest,
    pool: asyncpg.Pool = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    findings = _invoice_analyzer.analyze(body.records)
    return await _run_analysis(
        pool, tenant_id, "invoice_analysis", findings, len(body.records), body.save_results
    )


@app.post("/analyze/card-spend")
async def analyze_card_spend(
    body: AnalyzeCardSpendRequest,
    pool: asyncpg.Pool = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    findings = _card_analyzer.analyze(body.records)
    return await _run_analysis(
        pool, tenant_id, "card_spend_analysis", findings, len(body.records), body.save_results
    )


@app.post("/analyze/sod")
async def analyze_sod(
    body: AnalyzeSoDRequest,
    pool: asyncpg.Pool = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    violations = await _sod_engine.analyze(pool, tenant_id, body.users)
    findings = _sod_engine.violations_to_findings(violations)

    completed_at = datetime.now(timezone.utc)
    run_id = await _insert_run(
        pool,
        tenant_id=tenant_id,
        rule_key="sod_analysis",
        status="completed",
        triggered_by="api",
        findings_count=len(findings),
        records_processed=len(body.users),
        completed_at=completed_at,
    )

    if body.save_results and findings:
        await _finding_manager.save_findings(pool, tenant_id, run_id, None, findings)

    return {
        "run_id": run_id,
        "findings_count": len(findings),
        "records_processed": len(body.users),
        "violations": violations,
        "findings": [f.model_dump() for f in findings],
    }


@app.post("/analyze/cloud-config")
async def analyze_cloud_config(
    body: AnalyzeCloudConfigRequest,
    pool: asyncpg.Pool = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    findings = _cloud_checker.check_resources(body.resources)

    completed_at = datetime.now(timezone.utc)
    run_id = await _insert_run(
        pool,
        tenant_id=tenant_id,
        rule_key="cloud_config_analysis",
        status="completed",
        triggered_by="api",
        findings_count=len(findings),
        records_processed=len(body.resources),
        completed_at=completed_at,
    )

    if body.save_results and findings:
        await _finding_manager.save_findings(pool, tenant_id, run_id, None, findings)

    # Persist snapshot
    if _minio_client:
        try:
            import io, json
            snapshot_data = json.dumps(
                [r.model_dump() for r in body.resources], default=str
            ).encode()
            object_name = f"{tenant_id}/cloud-snapshots/{run_id}.json"
            _minio_client.put_object(
                settings.minio_bucket_monitoring,
                object_name,
                io.BytesIO(snapshot_data),
                len(snapshot_data),
                content_type="application/json",
            )
        except Exception as exc:
            logger.warning("Failed to store cloud snapshot: %s", exc)

        # Record snapshot metadata in DB
        try:
            providers = list({r.provider for r in body.resources})
            await pool.execute(
                """
                INSERT INTO cloud_config_snapshots
                    (id, tenant_id, run_id, providers, resource_count,
                     findings_count, created_at)
                VALUES ($1,$2,$3,$4,$5,$6,NOW())
                """,
                str(uuid.uuid4()),
                tenant_id,
                run_id,
                providers,
                len(body.resources),
                len(findings),
            )
        except Exception as exc:
            logger.warning("Failed to insert cloud snapshot record: %s", exc)

    return {
        "run_id": run_id,
        "findings_count": len(findings),
        "records_processed": len(body.resources),
        "findings": [f.model_dump() for f in findings],
    }


# ---------------------------------------------------------------------------
# Findings endpoints
# ---------------------------------------------------------------------------

@app.get("/findings")
async def list_findings(
    severity: str | None = Query(None),
    finding_type: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    pool: asyncpg.Pool = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    rows = await _finding_manager.get_findings(
        pool, tenant_id, severity=severity, finding_type=finding_type, status=status, limit=limit
    )
    return {"findings": rows, "count": len(rows)}


@app.get("/findings/summary")
async def findings_summary(
    pool: asyncpg.Pool = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    return await _finding_manager.get_findings_summary(pool, tenant_id)


@app.get("/findings/trend")
async def findings_trend(
    days: int = Query(30, ge=1, le=365),
    pool: asyncpg.Pool = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    return {"trend": await _finding_manager.get_trend_data(pool, tenant_id, days)}


@app.get("/findings/{finding_id}")
async def get_finding(
    finding_id: str,
    pool: asyncpg.Pool = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    row = await _finding_manager.get_finding_by_id(pool, tenant_id, finding_id)
    if not row:
        raise HTTPException(404, "Finding not found")
    return row


# ---------------------------------------------------------------------------
# Rules and configuration endpoints
# ---------------------------------------------------------------------------

@app.get("/rules")
async def list_rules(pool: asyncpg.Pool = Depends(get_db)):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, rule_key, rule_name, description, category, is_active, created_at
            FROM monitoring_rules
            ORDER BY category, rule_key
            """
        )
    return {"rules": [dict(r) for r in rows]}


@app.get("/rules/{rule_key}")
async def get_rule(rule_key: str, pool: asyncpg.Pool = Depends(get_db)):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM monitoring_rules WHERE rule_key = $1", rule_key
        )
    if not row:
        raise HTTPException(404, "Rule not found")
    return dict(row)


@app.get("/config")
async def get_config(
    pool: asyncpg.Pool = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT tmc.rule_key, tmc.is_enabled, tmc.schedule_interval,
                   tmc.config_overrides, tmc.last_run_at,
                   mr.rule_name, mr.description, mr.category
            FROM tenant_monitoring_configs tmc
            LEFT JOIN monitoring_rules mr ON mr.rule_key = tmc.rule_key
            WHERE tmc.tenant_id = $1
            ORDER BY mr.category, tmc.rule_key
            """,
            tenant_id,
        )
    return {"config": [dict(r) for r in rows]}


@app.post("/config/{rule_key}")
async def update_config(
    rule_key: str,
    body: ConfigUpdateRequest,
    pool: asyncpg.Pool = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    async with pool.acquire() as conn:
        existing = await conn.fetchrow(
            "SELECT id FROM tenant_monitoring_configs WHERE tenant_id = $1 AND rule_key = $2",
            tenant_id,
            rule_key,
        )
        if existing:
            # Build dynamic update — only set provided fields
            sets: list[str] = []
            params: list[Any] = []
            idx = 1
            if body.is_enabled is not None:
                sets.append(f"is_enabled = ${idx}")
                params.append(body.is_enabled)
                idx += 1
            if body.schedule_interval is not None:
                sets.append(f"schedule_interval = ${idx}")
                params.append(body.schedule_interval)
                idx += 1
            if body.config_overrides is not None:
                sets.append(f"config_overrides = ${idx}")
                params.append(body.config_overrides)
                idx += 1
            if not sets:
                return {"message": "No changes"}
            sets.append(f"updated_at = NOW()")
            params += [tenant_id, rule_key]
            await conn.execute(
                f"UPDATE tenant_monitoring_configs SET {', '.join(sets)} "
                f"WHERE tenant_id = ${idx} AND rule_key = ${idx + 1}",
                *params,
            )
        else:
            # Upsert
            await conn.execute(
                """
                INSERT INTO tenant_monitoring_configs
                    (tenant_id, rule_key, is_enabled, schedule_interval, config_overrides, created_at)
                VALUES ($1,$2,$3,$4,$5,NOW())
                """,
                tenant_id,
                rule_key,
                body.is_enabled if body.is_enabled is not None else True,
                body.schedule_interval or "daily",
                body.config_overrides or {},
            )
    return {"message": "Configuration updated", "rule_key": rule_key}


# ---------------------------------------------------------------------------
# SoD endpoints
# ---------------------------------------------------------------------------

@app.get("/sod/rules")
async def list_sod_rules(pool: asyncpg.Pool = Depends(get_db)):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, rule_key, role_a, role_b, description, severity, is_active, created_at
            FROM sod_rules
            WHERE is_active = TRUE
            ORDER BY severity DESC, rule_key
            """
        )
    return {"rules": [dict(r) for r in rows]}


@app.get("/sod/violations")
async def list_sod_violations(
    limit: int = Query(100, ge=1, le=1000),
    pool: asyncpg.Pool = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, user_id, user_name, user_email, department,
                   rule_key, role_a, role_b, severity, risk_score,
                   description, created_at
            FROM sod_violations
            WHERE tenant_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            tenant_id,
            limit,
        )
    return {"violations": [dict(r) for r in rows], "count": len(rows)}


@app.get("/sod/violations/summary")
async def sod_violations_summary(
    pool: asyncpg.Pool = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    async with pool.acquire() as conn:
        total_row = await conn.fetchrow(
            "SELECT COUNT(*) AS total FROM sod_violations WHERE tenant_id = $1", tenant_id
        )
        severity_rows = await conn.fetch(
            """
            SELECT severity, COUNT(*) AS cnt
            FROM sod_violations WHERE tenant_id = $1 GROUP BY severity
            """,
            tenant_id,
        )
        users_row = await conn.fetchrow(
            """
            SELECT COUNT(DISTINCT user_id) AS unique_users
            FROM sod_violations WHERE tenant_id = $1
            """,
            tenant_id,
        )

    by_severity = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for row in severity_rows:
        if row["severity"] in by_severity:
            by_severity[row["severity"]] = row["cnt"]

    return {
        "total": total_row["total"] if total_row else 0,
        "by_severity": by_severity,
        "unique_users_affected": users_row["unique_users"] if users_row else 0,
    }


# ---------------------------------------------------------------------------
# Cloud config endpoints
# ---------------------------------------------------------------------------

@app.get("/cloud/snapshots")
async def list_cloud_snapshots(
    limit: int = Query(20, ge=1, le=100),
    pool: asyncpg.Pool = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, run_id, providers, resource_count, findings_count, created_at
                FROM cloud_config_snapshots
                WHERE tenant_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                tenant_id,
                limit,
            )
        return {"snapshots": [dict(r) for r in rows]}
    except Exception as exc:
        logger.warning("cloud_config_snapshots query failed: %s", exc)
        return {"snapshots": []}


@app.get("/cloud/snapshots/summary")
async def cloud_snapshots_summary(
    pool: asyncpg.Pool = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    try:
        async with pool.acquire() as conn:
            total_row = await conn.fetchrow(
                "SELECT COUNT(*) AS total, SUM(findings_count) AS total_issues FROM cloud_config_snapshots WHERE tenant_id = $1",
                tenant_id,
            )
    except Exception:
        total_row = None

    # Summarise critical findings for cloud types from monitoring_findings
    async with pool.acquire() as conn:
        critical_row = await conn.fetchrow(
            """
            SELECT COUNT(*) AS cnt FROM monitoring_findings
            WHERE tenant_id = $1 AND severity = 'critical'
              AND finding_type LIKE 'cloud_%'
            """,
            tenant_id,
        )
        provider_rows = await conn.fetch(
            """
            SELECT evidence->>'provider' AS provider, COUNT(*) AS cnt
            FROM monitoring_findings
            WHERE tenant_id = $1 AND finding_type LIKE 'cloud_%'
              AND evidence->>'provider' IS NOT NULL
            GROUP BY evidence->>'provider'
            """,
            tenant_id,
        )

    providers = {row["provider"]: row["cnt"] for row in provider_rows}

    return {
        "total_snapshots": total_row["total"] if total_row else 0,
        "total_issues": total_row["total_issues"] if total_row and total_row["total_issues"] else 0,
        "critical_count": critical_row["cnt"] if critical_row else 0,
        "providers": providers,
    }


# ---------------------------------------------------------------------------
# Monitoring runs endpoints
# ---------------------------------------------------------------------------

@app.get("/runs")
async def list_runs(
    rule_key: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    pool: asyncpg.Pool = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    conditions = ["tenant_id = $1"]
    params: list[Any] = [tenant_id]
    idx = 2
    if rule_key:
        conditions.append(f"rule_key = ${idx}")
        params.append(rule_key)
        idx += 1
    params.append(limit)

    query = (
        f"SELECT id, rule_key, status, triggered_by, findings_count, "
        f"records_processed, completed_at, created_at "
        f"FROM monitoring_runs WHERE {' AND '.join(conditions)} "
        f"ORDER BY created_at DESC LIMIT ${idx}"
    )
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
    return {"runs": [dict(r) for r in rows]}


@app.get("/runs/{run_id}")
async def get_run(
    run_id: str,
    pool: asyncpg.Pool = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    async with pool.acquire() as conn:
        run_row = await conn.fetchrow(
            """
            SELECT id, rule_key, status, triggered_by, findings_count,
                   records_processed, completed_at, created_at
            FROM monitoring_runs
            WHERE tenant_id = $1 AND id = $2
            """,
            tenant_id,
            run_id,
        )
        if not run_row:
            raise HTTPException(404, "Run not found")

        findings_rows = await conn.fetch(
            """
            SELECT id, finding_type, severity, title, description,
                   entity_type, entity_id, entity_name,
                   evidence, risk_score, status, created_at
            FROM monitoring_findings
            WHERE tenant_id = $1 AND run_id = $2
            ORDER BY risk_score DESC NULLS LAST
            """,
            tenant_id,
            run_id,
        )

    run = dict(run_row)
    run["findings"] = [dict(r) for r in findings_rows]
    return run


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok", "service": "monitoring-service"}
