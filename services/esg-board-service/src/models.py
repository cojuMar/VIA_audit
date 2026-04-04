from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class DisclosureCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    metric_definition_id: str
    reporting_period: str  # '2025', '2025-Q1', etc.
    period_type: str = "annual"
    numeric_value: float | None = None
    text_value: str | None = None
    boolean_value: bool | None = None
    currency_value: float | None = None
    currency_code: str = "USD"
    notes: str | None = None
    data_source: str | None = None
    assurance_level: str | None = None
    assured_by: str | None = None
    submitted_by: str | None = None


class TargetCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    metric_definition_id: str
    target_year: int
    baseline_year: int | None = None
    baseline_value: float | None = None
    target_value: float
    target_type: str = "absolute"
    description: str | None = None
    science_based: bool = False
    framework_alignment: list[str] = []


class CommitteeCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    committee_type: str = "other"
    charter: str | None = None
    members: list[str] = []
    chair: str | None = None
    quorum_requirement: int = 3
    meeting_frequency: str = "quarterly"


class MeetingCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    committee_id: str | None = None
    title: str
    meeting_type: str = "regular"
    scheduled_date: str  # ISO datetime string
    location: str | None = None
    virtual_link: str | None = None
    attendees: list[str] = []


class AgendaItemCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    meeting_id: str
    sequence_number: int
    title: str
    item_type: str = "discussion"
    description: str | None = None
    presenter: str | None = None
    duration_minutes: int = 15


class PackageCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    meeting_id: str | None = None
    title: str
    package_type: str = "board_pack"
    reporting_period: str | None = None
    prepared_by: str | None = None
    recipient_list: list[str] = []
    executive_summary: str | None = None
