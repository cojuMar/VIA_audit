from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class EngagementCreate(BaseModel):
    """
    Canonical shape matches audit_engagements (V021 + V028).
    Legacy field names (engagement_name / engagement_type / period_start /
    period_end / description) are accepted as aliases for backward compat
    with older callers; internally we normalise to the canonical names.
    """

    title: str
    audit_type: str
    planned_start_date: date | None = None
    planned_end_date: date | None = None
    lead_auditor: str | None = None
    scope: str | None = None
    engagement_code: str | None = None
    objectives: str | None = None
    budget_hours: float | None = None
    engagement_manager: str | None = None

    # Legacy aliases — accepted on input, mapped into canonical fields by the
    # validator below. Not exposed on output.
    class Config:
        populate_by_name = True

    @classmethod
    def model_validate(cls, value, *args, **kwargs):  # type: ignore[override]
        if isinstance(value, dict):
            value = dict(value)
            _remap = {
                "engagement_name": "title",
                "engagement_type": "audit_type",
                "period_start": "planned_start_date",
                "period_end": "planned_end_date",
                "description": "scope",
            }
            for legacy, canonical in _remap.items():
                if legacy in value and canonical not in value:
                    value[canonical] = value.pop(legacy)
                elif legacy in value:
                    value.pop(legacy)  # canonical wins, drop alias
        return super().model_validate(value, *args, **kwargs)


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
