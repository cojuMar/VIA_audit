from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, field_validator


class TenantTier(str, Enum):
    SMB_POOL = "smb_pool"
    ENTERPRISE_SILO = "enterprise_silo"


class TenantCreate(BaseModel):
    display_name: str
    tier: TenantTier
    region: str
    external_id: Optional[str] = None  # CRM/billing system ID

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, v: str) -> str:
        if len(v) < 2 or len(v) > 100:
            raise ValueError("display_name must be between 2 and 100 characters")
        return v


class TenantResponse(BaseModel):
    tenant_id: str
    external_id: Optional[str] = None
    display_name: str
    tier: TenantTier
    region: str
    is_active: bool
    created_at: datetime
    schema_name: str  # 'public' for pool, 'tenant_xxx' for silo


class FirmClientLink(BaseModel):
    firm_tenant_id: str
    client_tenant_ids: list[str]  # UUIDs
