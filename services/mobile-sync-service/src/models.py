from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ResponsePayload(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    question_id: str
    response_value: str | None = None
    numeric_response: float | None = None
    boolean_response: bool | None = None
    gps_latitude: float | None = None
    gps_longitude: float | None = None
    comment: str | None = None
    is_finding: bool = False
    finding_severity: str | None = None
    photo_references: list[str] = []
    client_answered_at: str | None = None
    sync_id: str  # client UUID for dedup


class FieldAuditCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    assignment_id: str | None = None
    template_id: str
    auditor_email: str
    auditor_name: str | None = None
    location_name: str
    device_id: str | None = None
    client_created_at: str | None = None
    gps_latitude: float | None = None
    gps_longitude: float | None = None
    gps_accuracy_meters: float | None = None
    notes: str | None = None


class SyncBatchPayload(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    device_id: str
    auditor_email: str
    field_audits: list[dict] = []  # full audit objects with nested responses
    responses: list[ResponsePayload] = []  # standalone responses for existing audits
    photo_sync_ids: list[str] = []  # sync_ids of photos already uploaded


class AssignmentCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    template_id: str
    assigned_to_email: str
    assigned_to_name: str | None = None
    location_name: str
    location_address: str | None = None
    scheduled_date: str
    due_date: str
    priority: str = "medium"
    notes: str | None = None
    engagement_id: str | None = None
