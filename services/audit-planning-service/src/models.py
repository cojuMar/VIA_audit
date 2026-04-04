from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator


class EntityCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    description: str | None = None
    entity_type_id: str | None = None
    owner_name: str | None = None
    owner_email: str | None = None
    department: str | None = None
    risk_score: float = 5.0
    audit_frequency_months: int = 12
    tags: list[str] = []
    metadata: dict = {}


class PlanCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    plan_year: int
    title: str
    description: str | None = None
    total_budget_hours: float = 0


class PlanItemCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    plan_id: str
    audit_entity_id: str | None = None
    title: str
    audit_type: str = "internal"
    priority: str = "medium"
    planned_start_date: str | None = None
    planned_end_date: str | None = None
    budget_hours: float = 0
    assigned_lead: str | None = None
    rationale: str | None = None


class EngagementCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    plan_item_id: str | None = None
    title: str
    engagement_code: str | None = None
    audit_type: str = "internal"
    scope: str | None = None
    objectives: str | None = None
    planned_start_date: str | None = None
    planned_end_date: str | None = None
    budget_hours: float = 0
    lead_auditor: str | None = None
    team_members: list[str] = []
    engagement_manager: str | None = None


class TimeEntryCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    engagement_id: str
    auditor_name: str
    auditor_email: str | None = None
    entry_date: str | None = None  # defaults to today
    hours: float
    activity_type: str = "fieldwork"
    description: str | None = None
    is_billable: bool = True

    @field_validator("hours")
    @classmethod
    def hours_must_be_positive_and_max_24(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("hours must be greater than 0")
        if v > 24:
            raise ValueError("hours cannot exceed 24 in a single entry")
        return v


class MilestoneCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    engagement_id: str
    title: str
    milestone_type: str = "deliverable"
    due_date: str
    owner: str | None = None
    notes: str | None = None


class ResourceAssignmentCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    engagement_id: str
    auditor_name: str
    auditor_email: str
    role: str = "staff"
    allocated_hours: float = 0
    start_date: str | None = None
    end_date: str | None = None
