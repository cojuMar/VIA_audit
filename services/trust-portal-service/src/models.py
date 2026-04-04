from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel


class PortalConfig(BaseModel):
    id: UUID
    tenant_id: UUID
    slug: str
    company_name: str
    tagline: str | None
    logo_url: str | None
    primary_color: str
    portal_enabled: bool
    require_nda: bool
    nda_version: str
    show_compliance_scores: bool
    chatbot_enabled: bool
    chatbot_welcome_message: str | None
    allowed_frameworks: list[str]


class PortalDocument(BaseModel):
    id: UUID
    tenant_id: UUID
    display_name: str
    description: str | None
    document_type: str
    requires_nda: bool
    is_visible: bool
    valid_from: date | None
    valid_until: date | None
    file_size_bytes: int | None


class NDAAcceptance(BaseModel):
    signatory_name: str
    signatory_email: str
    signatory_company: str | None
    nda_version: str


class ChatMessage(BaseModel):
    role: str  # 'user' or 'assistant'
    content: str
    sources: list[dict] = []


class DeflectionRequest(BaseModel):
    requester_name: str
    requester_email: str
    requester_company: str | None
    questionnaire_type: str = "unknown"
    questions: list[str]  # list of question strings
