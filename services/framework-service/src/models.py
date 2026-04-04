from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional, Dict, Any
from uuid import UUID
from enum import Enum


class ControlStatus(str, Enum):
    NOT_STARTED = 'not_started'
    IN_PROGRESS = 'in_progress'
    PASSING = 'passing'
    FAILING = 'failing'
    NOT_APPLICABLE = 'not_applicable'
    EXCEPTION = 'exception'


class EquivalenceType(str, Enum):
    FULL = 'full'
    PARTIAL = 'partial'
    RELATED = 'related'


class GapSeverity(str, Enum):
    CRITICAL = 'critical'
    HIGH = 'high'
    MEDIUM = 'medium'
    LOW = 'low'


@dataclass
class FrameworkControl:
    id: UUID
    framework_id: UUID
    control_id: str        # e.g. 'CC6.1'
    domain: str
    title: str
    description: str
    guidance: Optional[str]
    evidence_types: List[str]
    testing_frequency: str
    is_key_control: bool


@dataclass
class CrosswalkEntry:
    source_control_id: UUID
    target_control_id: UUID
    equivalence_type: EquivalenceType
    notes: Optional[str]


@dataclass
class ComplianceScore:
    framework_id: UUID
    framework_name: str
    score_pct: float
    passing_controls: int
    failing_controls: int
    not_started_controls: int
    total_controls: int
    computed_at: datetime


@dataclass
class GapItem:
    framework_control_id: UUID
    control_id: str
    control_title: str
    domain: str
    gap_severity: GapSeverity
    gap_description: str
    remediation_steps: Optional[str]


@dataclass
class CalendarEvent:
    framework_id: UUID
    framework_name: str
    event_type: str
    title: str
    due_date: date
    description: Optional[str]
    is_completed: bool
    days_until_due: int
