from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional, Dict, Any
from uuid import UUID
from enum import Enum


class VendorType(str, Enum):
    SAAS = 'saas'
    INFRASTRUCTURE = 'infrastructure'
    PROFESSIONAL_SERVICES = 'professional_services'
    DATA_PROCESSOR = 'data_processor'
    FINANCIAL = 'financial'
    HARDWARE = 'hardware'
    OTHER = 'other'


class RiskTier(str, Enum):
    CRITICAL = 'critical'
    HIGH = 'high'
    MEDIUM = 'medium'
    LOW = 'low'
    UNRATED = 'unrated'


class VendorStatus(str, Enum):
    ACTIVE = 'active'
    INACTIVE = 'inactive'
    UNDER_REVIEW = 'under_review'
    OFFBOARDED = 'offboarded'


@dataclass
class VendorIntakeRequest:
    name: str
    vendor_type: VendorType
    website: Optional[str]
    description: Optional[str]
    primary_contact_name: Optional[str]
    primary_contact_email: Optional[str]
    data_types_processed: List[str]
    integrations_depth: str
    processes_pii: bool
    processes_phi: bool
    processes_pci: bool
    uses_ai: bool
    sub_processors: List[str]


@dataclass
class RiskRubricScore:
    vendor_id: UUID
    inherent_score: float          # 0.0–10.0
    risk_tier: RiskTier
    score_factors: Dict[str, Any]  # breakdown of what drove the score
    recommended_questionnaire: str # 'sig-lite', 'caiq-v4', or 'custom-base'


@dataclass
class QuestionnaireResponse:
    question_id: str
    answer: Any
    notes: Optional[str] = None


@dataclass
class VendorDocAnalysis:
    document_id: UUID
    document_type: str
    gaps: List[str]
    score: float                   # 0.0–10.0 (10 = most secure)
    summary: str
    expiry_date: Optional[date]
    certifications_found: List[str]


@dataclass
class MonitoringAlert:
    vendor_id: UUID
    vendor_name: str
    event_type: str
    severity: str
    title: str
    description: str
    source_url: Optional[str]
