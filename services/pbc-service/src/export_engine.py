from __future__ import annotations

from datetime import datetime, timezone

import asyncpg

from .config import settings
from .db import tenant_conn


class ExportEngine:

    # ------------------------------------------------------------------
    # Export PBC list
    # ------------------------------------------------------------------

    async def export_pbc_list(
        self, pool: asyncpg.Pool, tenant_id: str, list_id: str
    ) -> dict:
        async with tenant_conn(pool, tenant_id) as conn:
            list_row = await conn.fetchrow(
                """
                SELECT l.*, e.engagement_name
                FROM pbc_lists l
                JOIN engagements e
                    ON e.engagement_id = l.engagement_id
                WHERE l.list_id = $1 AND l.tenant_id = $2
                """,
                list_id,
                tenant_id,
            )
            if list_row is None:
                raise ValueError(f"PBC list {list_id} not found")

            request_rows = await conn.fetch(
                """
                SELECT * FROM pbc_requests
                WHERE list_id = $1 AND tenant_id = $2
                ORDER BY request_number ASC
                """,
                list_id,
                tenant_id,
            )

            fulfillment_rows = await conn.fetch(
                """
                SELECT request_id, submitted_by, response_text, file_name, submitted_at
                FROM pbc_fulfillments
                WHERE list_id = $1 AND tenant_id = $2
                ORDER BY submitted_at ASC
                """,
                list_id,
                tenant_id,
            )

        # Group fulfillments by request_id
        ful_map: dict[str, list[dict]] = {}
        for f in fulfillment_rows:
            rid = str(f["request_id"])
            ful_map.setdefault(rid, []).append(
                {
                    "submitted_by": f["submitted_by"],
                    "response_text": f["response_text"],
                    "file_name": f["file_name"],
                    "submitted_at": f["submitted_at"].isoformat()
                    if f["submitted_at"]
                    else None,
                }
            )

        total = len(request_rows)
        fulfilled = sum(1 for r in request_rows if r["status"] == "fulfilled")
        not_applicable = sum(1 for r in request_rows if r["status"] == "not_applicable")
        completed = fulfilled + not_applicable

        requests = []
        for req in request_rows:
            rid = str(req["request_id"])
            requests.append(
                {
                    "request_number": req["request_number"],
                    "title": req["title"],
                    "description": req["description"],
                    "category": req["category"],
                    "priority": req["priority"],
                    "assigned_to": req["assigned_to"],
                    "due_date": req["due_date"].isoformat() if req["due_date"] else None,
                    "status": req["status"],
                    "framework_control_ref": req["framework_control_ref"],
                    "fulfillments": ful_map.get(rid, []),
                }
            )

        return {
            "list": {
                "list_name": list_row["list_name"],
                "engagement_name": list_row["engagement_name"],
                "due_date": list_row["due_date"].isoformat()
                if list_row["due_date"]
                else None,
                "status": list_row["status"],
            },
            "summary": {
                "total": total,
                "fulfilled": fulfilled,
                "completion_pct": round(completed / total * 100, 1) if total else 0.0,
            },
            "requests": requests,
            "exported_at": datetime.now(tz=timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------
    # Export issue register
    # ------------------------------------------------------------------

    async def export_issue_register(
        self, pool: asyncpg.Pool, tenant_id: str, engagement_id: str
    ) -> dict:
        async with tenant_conn(pool, tenant_id) as conn:
            eng_row = await conn.fetchrow(
                """
                SELECT engagement_name, engagement_type,
                       period_start, period_end, lead_auditor
                FROM engagements
                WHERE engagement_id = $1 AND tenant_id = $2
                """,
                engagement_id,
                tenant_id,
            )
            if eng_row is None:
                raise ValueError(f"Engagement {engagement_id} not found")

            issue_rows = await conn.fetch(
                """
                SELECT * FROM audit_issues
                WHERE engagement_id = $1 AND tenant_id = $2
                ORDER BY issue_number ASC
                """,
                engagement_id,
                tenant_id,
            )

            issue_ids = [str(r["issue_id"]) for r in issue_rows]
            resp_rows = await conn.fetch(
                """
                SELECT issue_id, response_type, response_text,
                       submitted_by, new_status, responded_at
                FROM issue_responses
                WHERE tenant_id = $1 AND issue_id::text = ANY($2)
                ORDER BY responded_at ASC
                """,
                tenant_id,
                issue_ids,
            ) if issue_ids else []

        # Group responses by issue_id
        resp_map: dict[str, list[dict]] = {}
        for r in resp_rows:
            iid = str(r["issue_id"])
            resp_map.setdefault(iid, []).append(
                {
                    "response_type": r["response_type"],
                    "response_text": r["response_text"],
                    "submitted_by": r["submitted_by"],
                    "new_status": r["new_status"],
                    "responded_at": r["responded_at"].isoformat()
                    if r["responded_at"]
                    else None,
                }
            )

        total = len(issue_rows)
        open_count = sum(
            1
            for r in issue_rows
            if r["status"] not in ("resolved", "closed", "risk_accepted")
        )
        critical_count = sum(
            1 for r in issue_rows if (r["severity"] or "").lower() == "critical"
        )
        high_count = sum(
            1 for r in issue_rows if (r["severity"] or "").lower() == "high"
        )

        issues = []
        for issue in issue_rows:
            iid = str(issue["issue_id"])
            issues.append(
                {
                    "issue_number": issue["issue_number"],
                    "title": issue["title"],
                    "description": issue["description"],
                    "finding_type": issue["finding_type"],
                    "severity": issue["severity"],
                    "status": issue["status"],
                    "control_reference": issue["control_reference"],
                    "framework_references": issue["framework_references"],
                    "root_cause": issue["root_cause"],
                    "management_owner": issue["management_owner"],
                    "target_remediation_date": issue["target_remediation_date"].isoformat()
                    if issue["target_remediation_date"]
                    else None,
                    "actual_remediation_date": issue["actual_remediation_date"].isoformat()
                    if issue.get("actual_remediation_date")
                    else None,
                    "responses": resp_map.get(iid, []),
                }
            )

        return {
            "engagement": {
                "name": eng_row["engagement_name"],
                "type": eng_row["engagement_type"],
                "period_start": eng_row["period_start"].isoformat()
                if eng_row["period_start"]
                else None,
                "period_end": eng_row["period_end"].isoformat()
                if eng_row["period_end"]
                else None,
                "lead_auditor": eng_row["lead_auditor"],
            },
            "metrics": {
                "total": total,
                "open": open_count,
                "critical_count": critical_count,
                "high_count": high_count,
            },
            "issues": issues,
            "exported_at": datetime.now(tz=timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------
    # Export workpaper
    # ------------------------------------------------------------------

    async def export_workpaper(
        self, pool: asyncpg.Pool, tenant_id: str, workpaper_id: str
    ) -> dict:
        async with tenant_conn(pool, tenant_id) as conn:
            wp_row = await conn.fetchrow(
                "SELECT * FROM workpapers WHERE workpaper_id = $1 AND tenant_id = $2",
                workpaper_id,
                tenant_id,
            )
            if wp_row is None:
                raise ValueError(f"Workpaper {workpaper_id} not found")
            section_rows = await conn.fetch(
                """
                SELECT * FROM workpaper_sections
                WHERE workpaper_id = $1 AND tenant_id = $2
                ORDER BY sort_order ASC
                """,
                workpaper_id,
                tenant_id,
            )

        sections = [
            {
                "section_key": r["section_key"],
                "title": r["title"],
                "content": r["content"],
                "is_complete": r["is_complete"],
                "sort_order": r["sort_order"],
                "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
            }
            for r in section_rows
        ]

        return {
            "workpaper": {
                "workpaper_id": str(wp_row["workpaper_id"]),
                "title": wp_row["title"],
                "wp_reference": wp_row["wp_reference"],
                "workpaper_type": wp_row["workpaper_type"],
                "preparer": wp_row["preparer"],
                "reviewer": wp_row.get("reviewer"),
                "review_notes": wp_row.get("review_notes"),
                "status": wp_row["status"],
                "finalized_at": wp_row["finalized_at"].isoformat()
                if wp_row.get("finalized_at")
                else None,
                "created_at": wp_row["created_at"].isoformat()
                if wp_row["created_at"]
                else None,
            },
            "sections": sections,
            "exported_at": datetime.now(tz=timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------
    # AI finding summary
    # ------------------------------------------------------------------

    async def generate_ai_finding_summary(
        self, pool: asyncpg.Pool, tenant_id: str, engagement_id: str
    ) -> str:
        async with tenant_conn(pool, tenant_id) as conn:
            issue_rows = await conn.fetch(
                """
                SELECT title, description, finding_type, severity, status,
                       control_reference, root_cause
                FROM audit_issues
                WHERE engagement_id = $1 AND tenant_id = $2
                ORDER BY severity DESC, issue_number ASC
                """,
                engagement_id,
                tenant_id,
            )

        issues = [dict(r) for r in issue_rows]
        total = len(issues)

        # Try Claude first
        if settings.anthropic_api_key:
            try:
                import anthropic

                client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

                issues_text = "\n".join(
                    f"- [{i['severity'].upper()}] {i['title']}: {i['description']}"
                    f" (Finding type: {i['finding_type']}, Status: {i['status']})"
                    for i in issues
                )

                message = client.messages.create(
                    model="claude-haiku-4-5",
                    max_tokens=1024,
                    system=(
                        "You are an audit report writer. Generate a concise executive "
                        "summary of audit findings. Be professional and factual."
                    ),
                    messages=[
                        {
                            "role": "user",
                            "content": (
                                f"Please write a 3-paragraph executive summary of the "
                                f"following audit findings ({total} total):\n\n"
                                f"{issues_text}"
                            ),
                        }
                    ],
                )
                return message.content[0].text
            except Exception:
                pass  # Fall through to template summary

        # Template-based fallback
        by_severity: dict[str, int] = {}
        by_status: dict[str, int] = {}
        for issue in issues:
            sev = (issue.get("severity") or "low").lower()
            by_severity[sev] = by_severity.get(sev, 0) + 1
            st = (issue.get("status") or "open").lower()
            by_status[st] = by_status.get(st, 0) + 1

        open_count = sum(
            v for k, v in by_status.items()
            if k not in ("resolved", "closed", "risk_accepted")
        )
        critical = by_severity.get("critical", 0)
        high = by_severity.get("high", 0)

        para1 = (
            f"This engagement identified a total of {total} audit finding(s) across "
            f"multiple risk and control areas. The findings reflect areas where "
            f"controls require strengthening or where process improvements are warranted."
        )
        para2 = (
            f"Of the {total} finding(s), {critical} were rated Critical and {high} were "
            f"rated High severity, requiring prompt management attention. "
            f"Currently {open_count} finding(s) remain open and are pending remediation "
            f"or management response."
        )
        para3 = (
            "Management is encouraged to review each finding, assign ownership, and "
            "establish remediation timelines. Progress should be tracked through the "
            "issue register and validated by the audit team upon completion."
        )

        return f"{para1}\n\n{para2}\n\n{para3}"
