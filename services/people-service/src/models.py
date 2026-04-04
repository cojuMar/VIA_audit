from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel


class EmployeeCreate(BaseModel):
    employee_id: str
    full_name: str
    email: str
    department: str | None = None
    job_title: str | None = None
    job_role: str = "all"
    manager_id: str | None = None
    hire_date: date | None = None


class PolicyCreate(BaseModel):
    policy_key: str
    title: str
    description: str | None = None
    category: str
    applies_to_roles: list[str] = ["all"]
    applies_to_departments: list[str] = []
    acknowledgment_required: bool = True
    acknowledgment_frequency_days: int = 365


class AcknowledgmentRecord(BaseModel):
    policy_id: str
    employee_id: str
    policy_version: str
    acknowledgment_method: str = "portal"


class TrainingCourseCreate(BaseModel):
    course_key: str
    title: str
    description: str | None = None
    category: str
    applies_to_roles: list[str] = ["all"]
    duration_minutes: int | None = None
    passing_score_pct: int = 80
    recurrence_days: int | None = None
    provider: str = "internal"


class TrainingAssignmentCreate(BaseModel):
    course_id: str
    employee_id: str
    due_date: date | None = None


class TrainingCompletion(BaseModel):
    assignment_id: str
    employee_id: str
    course_id: str
    score_pct: int | None = None
    passed: bool = True
    completion_method: str = "portal"
    external_completion_id: str | None = None


class BackgroundCheckCreate(BaseModel):
    employee_id: str
    check_type: str
    provider: str = "manual"
    external_check_id: str | None = None
    expiry_date: date | None = None


class EmployeeComplianceScore(BaseModel):
    employee_id: str
    full_name: str
    overall_score: float
    policy_score: float
    training_score: float
    background_check_score: float
    status: str  # 'compliant', 'at_risk', 'non_compliant'
    open_items: int
    details: dict[str, Any]
