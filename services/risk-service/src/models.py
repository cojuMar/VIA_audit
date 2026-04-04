from datetime import date

from pydantic import BaseModel


class RiskCreate(BaseModel):
    risk_id: str  # e.g. "RISK-001"
    title: str
    description: str
    category_key: str
    owner: str | None = None
    department: str | None = None
    inherent_likelihood: int  # 1-5
    inherent_impact: int  # 1-5
    residual_likelihood: int | None = None
    residual_impact: int | None = None
    target_likelihood: int | None = None
    target_impact: int | None = None
    framework_control_refs: list[str] = []
    source: str = "manual"
    identified_date: date | None = None
    review_date: date | None = None


class RiskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    owner: str | None = None
    department: str | None = None
    status: str | None = None
    residual_likelihood: int | None = None
    residual_impact: int | None = None
    target_likelihood: int | None = None
    target_impact: int | None = None
    review_date: date | None = None


class AssessmentCreate(BaseModel):
    risk_id: str
    assessed_by: str
    inherent_likelihood: int
    inherent_impact: int
    residual_likelihood: int | None = None
    residual_impact: int | None = None
    assessment_notes: str | None = None
    controls_evaluated: list[str] = []


class TreatmentCreate(BaseModel):
    risk_id: str
    treatment_type: str  # mitigate/accept/transfer/avoid
    title: str
    description: str
    owner: str | None = None
    target_date: date | None = None
    cost_estimate: float | None = None


class TreatmentUpdate(BaseModel):
    status: str | None = None
    completed_date: date | None = None
    effectiveness_rating: int | None = None
    description: str | None = None


class IndicatorCreate(BaseModel):
    risk_id: str
    indicator_name: str
    description: str | None = None
    metric_type: str  # kri/kpi/kci
    threshold_green: float | None = None
    threshold_amber: float | None = None
    threshold_red: float | None = None
    data_source: str | None = None


class IndicatorReading(BaseModel):
    indicator_id: str
    value: float
    notes: str | None = None
