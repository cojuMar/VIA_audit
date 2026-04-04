from __future__ import annotations

import uuid
from datetime import datetime, timezone

import httpx
import asyncpg

from .config import settings
from .db import tenant_conn
from .models import PackageCreate


class PackageManager:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    # ------------------------------------------------------------------
    # Core CRUD (board_packages & board_package_items are immutable)
    # ------------------------------------------------------------------

    async def create_package(
        self, tenant_id: str, data: PackageCreate
    ) -> dict:
        package_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        async with tenant_conn(self.pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO board_packages (
                    id, tenant_id, meeting_id, title, package_type,
                    reporting_period, prepared_by, recipient_list,
                    executive_summary, status, created_at
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, 'draft', $10
                )
                RETURNING *
                """,
                package_id,
                tenant_id,
                data.meeting_id,
                data.title,
                data.package_type,
                data.reporting_period,
                data.prepared_by,
                data.recipient_list,
                data.executive_summary,
                now,
            )
        return dict(row)

    async def add_package_item(
        self,
        tenant_id: str,
        package_id: str,
        sequence_number: int,
        section_title: str,
        content_type: str,
        content_data: dict,
        source_service: str | None = None,
        is_confidential: bool = False,
    ) -> dict:
        item_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        async with tenant_conn(self.pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO board_package_items (
                    id, tenant_id, package_id, sequence_number, section_title,
                    content_type, content_data, source_service,
                    is_confidential, created_at
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9, $10
                )
                RETURNING *
                """,
                item_id,
                tenant_id,
                package_id,
                sequence_number,
                section_title,
                content_type,
                content_data,
                source_service,
                is_confidential,
                now,
            )
        return dict(row)

    async def get_package(self, tenant_id: str, package_id: str) -> dict:
        async with tenant_conn(self.pool, tenant_id) as conn:
            package_row = await conn.fetchrow(
                "SELECT * FROM board_packages WHERE id = $1",
                package_id,
            )
            if package_row is None:
                raise ValueError(f"Package {package_id} not found")
            item_rows = await conn.fetch(
                """
                SELECT * FROM board_package_items
                WHERE package_id = $1
                ORDER BY sequence_number
                """,
                package_id,
            )
        result = dict(package_row)
        result["items"] = [dict(r) for r in item_rows]
        return result

    async def list_packages(
        self,
        tenant_id: str,
        package_type: str | None = None,
        meeting_id: str | None = None,
    ) -> list[dict]:
        conditions: list[str] = []
        params: list = []
        idx = 1

        if package_type:
            conditions.append(f"p.package_type = ${idx}")
            params.append(package_type)
            idx += 1
        if meeting_id:
            conditions.append(f"p.meeting_id = ${idx}")
            params.append(meeting_id)
            idx += 1

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        query = f"""
            SELECT
                p.*,
                COUNT(pi.id) AS item_count
            FROM board_packages p
            LEFT JOIN board_package_items pi ON pi.package_id = p.id
            {where}
            GROUP BY p.id
            ORDER BY p.created_at DESC
        """
        async with tenant_conn(self.pool, tenant_id) as conn:
            rows = await conn.fetch(query, *params)
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Auto-build helpers
    # ------------------------------------------------------------------

    async def _fetch_risks(self, tenant_id: str) -> list[dict]:
        """Fetch top 5 risks from the risk-service."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{settings.risk_service_url}/risks",
                    params={"limit": 5, "sort": "risk_score_desc"},
                    headers={"X-Tenant-ID": tenant_id},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    # Accept list or {items: [...]} envelope
                    return data if isinstance(data, list) else data.get("items", data)
        except Exception:
            pass
        return []

    async def _fetch_monitoring_findings(self, tenant_id: str) -> list[dict]:
        """Fetch recent monitoring findings from the monitoring-service."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{settings.monitoring_service_url}/findings",
                    params={"limit": 10, "sort": "created_at_desc"},
                    headers={"X-Tenant-ID": tenant_id},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data if isinstance(data, list) else data.get("items", data)
        except Exception:
            pass
        return []

    async def _fetch_audit_engagements(self, tenant_id: str) -> list[dict]:
        """Fetch recent audit engagements from the audit-planning-service."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{settings.audit_planning_service_url}/engagements",
                    params={"limit": 10, "sort": "created_at_desc"},
                    headers={"X-Tenant-ID": tenant_id},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data if isinstance(data, list) else data.get("items", data)
        except Exception:
            pass
        return []

    async def _fetch_red_risk_indicators(self, tenant_id: str) -> list[dict]:
        """Fetch risk indicators in red status from the risk-service."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{settings.risk_service_url}/indicators",
                    params={"status": "red"},
                    headers={"X-Tenant-ID": tenant_id},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data if isinstance(data, list) else data.get("items", data)
        except Exception:
            pass
        return []

    async def _update_package_summary(
        self, tenant_id: str, package_id: str, executive_summary: str
    ) -> None:
        """Update the executive_summary on an existing (mutable) package header."""
        # board_packages itself allows executive_summary updates (only items are strictly immutable)
        async with tenant_conn(self.pool, tenant_id) as conn:
            await conn.execute(
                "UPDATE board_packages SET executive_summary = $1 WHERE id = $2",
                executive_summary,
                package_id,
            )

    async def build_esg_package(
        self,
        tenant_id: str,
        reporting_period: str,
        meeting_id: str | None = None,
        ai_advisor=None,
    ) -> dict:
        # 1. Create package
        from .models import PackageCreate

        package_data = PackageCreate(
            meeting_id=meeting_id,
            title=f"ESG Board Package — {reporting_period}",
            package_type="esg_report",
            reporting_period=reporting_period,
        )
        package = await self.create_package(tenant_id, package_data)
        package_id = package["id"]

        # 2. ESG scorecard
        from .esg_manager import ESGManager

        esg_mgr = ESGManager(self.pool)
        scorecard = await esg_mgr.get_esg_scorecard(tenant_id, reporting_period)
        await self.add_package_item(
            tenant_id=tenant_id,
            package_id=package_id,
            sequence_number=1,
            section_title="ESG Scorecard",
            content_type="esg_scorecard",
            content_data=scorecard,
            source_service="esg-board-service",
        )

        # 3. Target progress
        target_progress = await esg_mgr.get_target_progress(
            tenant_id, int(reporting_period[:4])
        )
        await self.add_package_item(
            tenant_id=tenant_id,
            package_id=package_id,
            sequence_number=2,
            section_title="ESG Target Progress",
            content_type="metrics_table",
            content_data={"targets": target_progress},
            source_service="esg-board-service",
        )

        # 4. Top 5 risks
        risks = await self._fetch_risks(tenant_id)
        await self.add_package_item(
            tenant_id=tenant_id,
            package_id=package_id,
            sequence_number=3,
            section_title="Top Risks",
            content_type="risk_heatmap",
            content_data={"risks": risks},
            source_service="risk-service",
        )

        # 5. Recent monitoring findings
        findings = await self._fetch_monitoring_findings(tenant_id)
        await self.add_package_item(
            tenant_id=tenant_id,
            package_id=package_id,
            sequence_number=4,
            section_title="Monitoring Findings",
            content_type="audit_findings",
            content_data={"findings": findings},
            source_service="monitoring-service",
        )

        # 6. AI executive summary
        executive_summary: str
        if ai_advisor is not None:
            targets = await esg_mgr.get_targets(tenant_id)
            executive_summary = await ai_advisor.generate_esg_narrative(
                scorecard=scorecard,
                targets=targets,
                reporting_period=reporting_period,
            )
        else:
            executive_summary = (
                f"## ESG Board Package — {reporting_period}\n\n"
                "This package summarises ESG performance, target progress, "
                "key risks and recent monitoring findings for the reporting period."
            )

        await self._update_package_summary(tenant_id, package_id, executive_summary)

        return await self.get_package(tenant_id, package_id)

    async def build_audit_committee_package(
        self,
        tenant_id: str,
        reporting_period: str,
        meeting_id: str | None = None,
        ai_advisor=None,
    ) -> dict:
        from .models import PackageCreate

        # 1. Create package
        package_data = PackageCreate(
            meeting_id=meeting_id,
            title=f"Audit Committee Package — {reporting_period}",
            package_type="audit_report",
            reporting_period=reporting_period,
        )
        package = await self.create_package(tenant_id, package_data)
        package_id = package["id"]

        # 2. Recent audit engagements summary
        engagements = await self._fetch_audit_engagements(tenant_id)
        await self.add_package_item(
            tenant_id=tenant_id,
            package_id=package_id,
            sequence_number=1,
            section_title="Audit Engagements Summary",
            content_type="engagements_summary",
            content_data={"engagements": engagements},
            source_service="audit-planning-service",
        )

        # 3. Open issues / findings
        findings = await self._fetch_monitoring_findings(tenant_id)
        open_findings = [
            f for f in findings if f.get("status") not in ("closed", "resolved")
        ]
        await self.add_package_item(
            tenant_id=tenant_id,
            package_id=package_id,
            sequence_number=2,
            section_title="Open Issues & Findings",
            content_type="audit_findings",
            content_data={"findings": open_findings},
            source_service="monitoring-service",
        )

        # 4. Red risk indicators
        red_indicators = await self._fetch_red_risk_indicators(tenant_id)
        await self.add_package_item(
            tenant_id=tenant_id,
            package_id=package_id,
            sequence_number=3,
            section_title="Risk Indicators — Red Status",
            content_type="risk_indicators",
            content_data={"indicators": red_indicators},
            source_service="risk-service",
        )

        # 5. AI executive summary
        all_items = [
            {"section": "Audit Engagements", "data": engagements},
            {"section": "Open Findings", "data": open_findings},
            {"section": "Red Risk Indicators", "data": red_indicators},
        ]
        if ai_advisor is not None:
            executive_summary = await ai_advisor.generate_board_pack_summary(
                package_items=all_items,
                package_type="audit_report",
            )
        else:
            executive_summary = (
                f"## Audit Committee Package — {reporting_period}\n\n"
                "This package covers recent audit engagement activity, open issues "
                "and findings, and risk indicators currently rated red."
            )

        await self._update_package_summary(tenant_id, package_id, executive_summary)

        return await self.get_package(tenant_id, package_id)
