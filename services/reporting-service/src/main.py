"""
Reporting Service — FastAPI application

Routes:
  POST /reports/generate          — Queue a report generation job
  GET  /reports/{export_id}       — Get report status and metadata
  GET  /reports/{export_id}/download — Download generated report
  GET  /reports                   — List reports for tenant
  GET  /health
"""

import asyncio
import hashlib
import logging
from contextlib import asynccontextmanager
from datetime import date
from typing import Optional, List
import asyncpg
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Header, Query
from pydantic import BaseModel, Field
from .config import settings
from .db import create_db_pool
from .models import ReportRequest
from .report_builder import ReportBuilder
from .xbrl_generator import XBRLGenerator, IXBRLGenerator
from .saft_generator import SAFTGenerator
from .gifi_generator import GIFIGenerator
from .pdf_generator import PDFA3Generator
from .pades_signer import PAdESSigner
from .storage import ReportStorage

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

_db_pool: Optional[asyncpg.Pool] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _db_pool
    _db_pool = await create_db_pool()
    logger.info("Reporting service started")
    yield
    if _db_pool:
        await _db_pool.close()


app = FastAPI(title="Aegis Reporting Service", version="1.0.0", lifespan=lifespan)


def get_db() -> asyncpg.Pool:
    if _db_pool is None:
        raise HTTPException(503, "DB pool not ready")
    return _db_pool


async def _get_tenant_id(x_tenant_id: str = Header(..., alias="X-Tenant-ID")) -> str:
    return x_tenant_id


async def _require_bearer(authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing Bearer token")
    return authorization[7:]


class GenerateReportRequest(BaseModel):
    format: str = Field(..., pattern=r'^(xbrl|ixbrl|saft|gifi|pdf_a)$')
    framework: str = Field(..., pattern=r'^(soc2|iso27001|pci_dss|tax|custom)$')
    period_start: str = Field(..., pattern=r'^\d{4}-\d{2}-\d{2}$')
    period_end: str = Field(..., pattern=r'^\d{4}-\d{2}-\d{2}$')
    narrative_ids: Optional[List[str]] = None
    sign_pdf: bool = True  # Apply PAdES signature (only for pdf_a format)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/reports/generate", status_code=202)
async def generate_report(
    body: GenerateReportRequest,
    background_tasks: BackgroundTasks,
    tenant_id: str = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
    _auth = Depends(_require_bearer),
):
    """Queue a report generation job. Returns export_id immediately; generation runs async."""
    period_start = date.fromisoformat(body.period_start)
    period_end = date.fromisoformat(body.period_end)

    async with db.acquire() as conn:
        await conn.execute('SET LOCAL app.tenant_id = $1', tenant_id)
        export_id = await conn.fetchval("""
            INSERT INTO report_exports (tenant_id, format, framework, period_start, period_end, status)
            VALUES ($1::uuid, $2, $3, $4::date, $5::date, 'pending')
            RETURNING export_id::text
        """, tenant_id, body.format, body.framework, period_start, period_end)

    background_tasks.add_task(
        _generate_report_async,
        export_id=export_id,
        tenant_id=tenant_id,
        body=body,
        period_start=period_start,
        period_end=period_end,
    )

    return {"export_id": export_id, "status": "pending"}


async def _generate_report_async(
    export_id: str,
    tenant_id: str,
    body: GenerateReportRequest,
    period_start: date,
    period_end: date,
):
    """Background task: generate report, sign if needed, upload to MinIO, update DB."""
    db = _db_pool
    if db is None:
        return

    try:
        async with db.acquire() as conn:
            await conn.execute('SET LOCAL app.tenant_id = $1', tenant_id)
            await conn.execute(
                "UPDATE report_exports SET status='generating' WHERE export_id=$1::uuid",
                export_id
            )

        # Build report data
        builder = ReportBuilder(db)
        request = await builder.build(
            tenant_id=tenant_id,
            framework=body.framework,
            period_start=period_start,
            period_end=period_end,
            narrative_ids=body.narrative_ids,
        )

        # Generate in the appropriate format
        storage = ReportStorage()
        checksum = None

        if body.format == 'xbrl':
            gen = XBRLGenerator()
            report_bytes = gen.generate(request)
            checksum = hashlib.sha256(report_bytes).digest()

        elif body.format == 'ixbrl':
            gen = IXBRLGenerator()
            report_bytes = gen.generate(request)
            checksum = hashlib.sha256(report_bytes).digest()

        elif body.format == 'saft':
            gen = SAFTGenerator()
            report_bytes = gen.generate(request)
            checksum = hashlib.sha256(report_bytes).digest()

        elif body.format == 'gifi':
            gen = GIFIGenerator()
            report_bytes = gen.generate(request)
            checksum = hashlib.sha256(report_bytes).digest()

        elif body.format == 'pdf_a':
            # Generate XBRL for embedding
            xbrl_gen = XBRLGenerator()
            xbrl_bytes = xbrl_gen.generate(request) if request.facts else None

            # Generate PDF/A-3
            pdf_gen = PDFA3Generator()
            pdf_result = pdf_gen.generate(request, xbrl_bytes=xbrl_bytes)
            checksum = pdf_result.checksum_sha256

            # Apply PAdES signature if requested
            if body.sign_pdf:
                signer = PAdESSigner(
                    cert_path=settings.signing_cert_path,
                    key_path=settings.signing_key_path,
                    tsa_url=settings.tsa_url,
                )
                sig_result = signer.sign(pdf_result.pdf_bytes)
                report_bytes = sig_result.signed_pdf_bytes

                # Persist signature record
                if sig_result.is_signed:
                    async with db.acquire() as conn:
                        await conn.execute('SET LOCAL app.tenant_id = $1', tenant_id)
                        await conn.execute("""
                            INSERT INTO digital_signatures
                                (export_id, tenant_id, signer_cert_sha256, signer_dn,
                                 signing_time, signature_type)
                            VALUES ($1::uuid, $2::uuid, $3, $4, $5::timestamptz, $6)
                        """,
                            export_id, tenant_id,
                            bytes.fromhex('00' * 32),  # placeholder in dev
                            sig_result.signer_dn or "CN=Aegis Dev Signer",
                            sig_result.signing_time,
                            sig_result.signature_type,
                        )
            else:
                report_bytes = pdf_result.pdf_bytes

        else:
            raise ValueError(f"Unknown format: {body.format}")

        # Upload to MinIO
        object_path = storage.upload(
            export_id=export_id,
            tenant_id=tenant_id,
            report_format=body.format,
            data=report_bytes,
            checksum_sha256=checksum,
        )

        # Mark complete in DB
        async with db.acquire() as conn:
            await conn.execute('SET LOCAL app.tenant_id = $1', tenant_id)
            await conn.execute("""
                UPDATE report_exports
                SET status='completed', storage_path=$1, file_size_bytes=$2,
                    checksum_sha256=$3, completed_at=NOW(), evidence_count=$4
                WHERE export_id=$5::uuid
            """,
                object_path, len(report_bytes), checksum,
                len(request.evidence_records), export_id,
            )

        logger.info("Report %s generated: format=%s bytes=%d", export_id, body.format, len(report_bytes))

    except Exception as e:
        logger.error("Report generation failed for %s: %s", export_id, e, exc_info=True)
        try:
            async with db.acquire() as conn:
                await conn.execute('SET LOCAL app.tenant_id = $1', tenant_id)
                await conn.execute("""
                    UPDATE report_exports SET status='failed', generation_log=$1 WHERE export_id=$2::uuid
                """, str(e), export_id)
        except Exception:
            pass


@app.get("/reports/{export_id}")
async def get_report(
    export_id: str,
    tenant_id: str = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
    _auth = Depends(_require_bearer),
):
    async with db.acquire() as conn:
        await conn.execute('SET LOCAL app.tenant_id = $1', tenant_id)
        row = await conn.fetchrow(
            "SELECT * FROM report_exports WHERE export_id=$1::uuid AND tenant_id=$2::uuid",
            export_id, tenant_id
        )
    if not row:
        raise HTTPException(404, "Report not found")
    return dict(row)


@app.get("/reports/{export_id}/download")
async def download_report(
    export_id: str,
    tenant_id: str = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
    _auth = Depends(_require_bearer),
):
    """Get a presigned download URL for a completed report."""
    async with db.acquire() as conn:
        await conn.execute('SET LOCAL app.tenant_id = $1', tenant_id)
        row = await conn.fetchrow(
            "SELECT status, storage_path, format FROM report_exports WHERE export_id=$1::uuid AND tenant_id=$2::uuid",
            export_id, tenant_id
        )
    if not row:
        raise HTTPException(404, "Report not found")
    if row['status'] != 'completed':
        raise HTTPException(409, f"Report not ready: status={row['status']}")

    storage = ReportStorage()
    url = storage.get_presigned_url(row['storage_path'], expires_seconds=3600)
    return {"download_url": url, "expires_in": 3600}


@app.get("/reports")
async def list_reports(
    tenant_id: str = Depends(_get_tenant_id),
    db: asyncpg.Pool = Depends(get_db),
    _auth = Depends(_require_bearer),
    format: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    conditions = ["tenant_id = $1::uuid"]
    params: list = [tenant_id]
    idx = 2
    if format:
        conditions.append(f"format = ${idx}")
        params.append(format)
        idx += 1
    if status:
        conditions.append(f"status = ${idx}")
        params.append(status)
        idx += 1
    params.extend([limit, offset])

    where = " AND ".join(conditions)
    async with db.acquire() as conn:
        await conn.execute('SET LOCAL app.tenant_id = $1', tenant_id)
        rows = await conn.fetch(f"""
            SELECT export_id, format, framework, period_start, period_end,
                   status, file_size_bytes, created_at, completed_at
            FROM report_exports WHERE {where}
            ORDER BY created_at DESC
            LIMIT ${idx} OFFSET ${idx+1}
        """, *params)
    return [dict(r) for r in rows]
