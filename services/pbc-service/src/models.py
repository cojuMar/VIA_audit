from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class EngagementCreate(BaseModel):
    engagement_name: str
    engagement_type: str
    fiscal_year: int | None = None
    period_start: date | None = None
    period_end: date | None = None
    lead_auditor: str | None = None
    description: str | None = None


class PBCListCreate(BaseModel):
    engagement_id: str
    list_name: str
    description: str | None = None
    due_date: date | None = None


class PBCRequestCreate(BaseModel):
    list_id: str
    title: str
    description: str
    category: str | None = None
    priority: str = "medium"
    assigned_to: str | None = None
    due_date: date | None = None
    framework_control_ref: str | None = None


class PBCFulfillmentCreate(BaseModel):
    request_id: str
    submitted_by: str
    response_text: str | None = None
    submission_notes: str | None = None


class IssueCreate(BaseModel):
    engagement_id: str
    title: str
    description: str
    finding_type: str
    severity: str
    control_reference: str | None = None
    framework_references: list[str] = []
    root_cause: str | None = None
    management_owner: str | None = None
    target_remediation_date: date | None = None


class IssueResponseCreate(BaseModel):
    issue_id: str
    response_type: str
    response_text: str
    submitted_by: str
    new_status: str | None = None


class WorkpaperCreate(BaseModel):
    engagement_id: str
    template_id: str | None = None
    title: str
    wp_reference: str | None = None
    workpaper_type: str
    preparer: str | None = None


class SectionUpdate(BaseModel):
    content: dict
    is_complete: bool = False
