from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, field_validator


class ResourceType(str, Enum):
    DATABASE_READONLY = "database_readonly"
    DATABASE_INFRA = "database_infra"
    API_READONLY = "api_readonly"
    BREAK_GLASS = "break_glass"


class RequestStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"
    REVOKED = "revoked"


class AccessRequestCreate(BaseModel):
    resource_type: ResourceType
    justification: str
    itsm_ticket_id: Optional[str] = None
    requested_duration_seconds: int

    @field_validator("justification")
    @classmethod
    def justification_min_length(cls, v: str) -> str:
        if len(v) < 20:
            raise ValueError("justification must be at least 20 characters")
        return v

    @field_validator("requested_duration_seconds")
    @classmethod
    def duration_must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("requested_duration_seconds must be > 0")
        return v


class AccessRequestResponse(BaseModel):
    request_id: str
    status: RequestStatus
    approved_duration_seconds: Optional[int] = None
    expires_at: Optional[datetime] = None
    credential: Optional[dict] = None  # Only returned to the service, not the user
    vault_lease_id: Optional[str] = None


class PAMAuditEntry(BaseModel):
    request_id: str
    actor_user_id: str
    actor_role: str
    action: str
    resource: Optional[str] = None
    query_text: Optional[str] = None  # Redacted in response
    duration_ms: Optional[int] = None
    status_code: Optional[int] = None
    ip_address: Optional[str] = None


class TokenClaims(BaseModel):
    sub: str
    tenant_id: str
    role: str
    client_access: Optional[list[str]] = None
    iat: int
    exp: int
    jti: str
