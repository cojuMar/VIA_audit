from pydantic import BaseModel


class PayrollRecord(BaseModel):
    employee_id: str
    employee_name: str | None = None
    department: str | None = None
    amount: float
    period: str  # "2024-01" format
    payment_date: str | None = None


class InvoiceRecord(BaseModel):
    invoice_id: str
    vendor_name: str
    amount: float
    invoice_date: str  # ISO date
    description: str | None = None
    approval_threshold: float | None = None  # tenant's approval threshold


class CardTransaction(BaseModel):
    transaction_id: str
    employee_id: str
    employee_name: str | None = None
    merchant_name: str
    amount: float
    transaction_date: str  # ISO datetime
    merchant_category: str | None = None
    policy_limit_daily: float | None = None


class UserAccessRecord(BaseModel):
    user_id: str
    user_name: str | None = None
    user_email: str | None = None
    department: str | None = None
    roles: list[str]
    permissions: list[str] = []


class CloudResourceConfig(BaseModel):
    provider: str  # 'aws', 'gcp', 'azure'
    resource_type: str
    resource_id: str
    resource_name: str | None = None
    region: str | None = None
    config: dict


class MonitoringFinding(BaseModel):
    finding_type: str
    severity: str
    title: str
    description: str
    entity_type: str | None = None
    entity_id: str | None = None
    entity_name: str | None = None
    evidence: dict
    risk_score: float | None = None
