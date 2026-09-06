from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class ProductType(StrEnum):
    MUTUAL_FUND = "mutual_fund"
    PMS = "pms"
    AIF = "aif"


class EvidenceKind(StrEnum):
    VERIFIED_FACT = "verified_fact"
    CALCULATED_METRIC = "calculated_metric"
    AI_ASSESSMENT = "ai_assessment"
    USER_INPUT = "user_input"
    DOCUMENT_EXTRACT = "document_extract"


class CashFlowKind(StrEnum):
    CONTRIBUTION = "Contribution"
    DISTRIBUTION = "Distribution"
    RESIDUAL_VALUE = "Residual value"


class AnalysisStatus(StrEnum):
    COMPLETE = "ANALYSIS COMPLETE"
    PARTIAL = "ANALYSIS PARTIAL"
    INSUFFICIENT = "INSUFFICIENT VERIFIED DATA"
    SOURCE_UNAVAILABLE = "SOURCE UNAVAILABLE"


class SourceRef(BaseModel):
    model_config = ConfigDict(frozen=True)
    title: str
    publisher: str
    url: HttpUrl | None = None
    observed_at: date
    retrieved_at: datetime
    page: int | None = Field(default=None, ge=1)


class EvidenceItem(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    kind: EvidenceKind
    label: str
    value: str | float | int | list[str]
    unit: str | None = None
    source: SourceRef
    excerpt: str | None = Field(default=None, max_length=500)
    confidence: float = Field(default=1.0, ge=0, le=1)


class ProductIdentity(BaseModel):
    model_config = ConfigDict(frozen=True)
    product_type: ProductType
    name: str
    provider: str
    registration_id: str | None = None
    scheme_code: str | None = None
    plan: str | None = None
    option: str | None = None
    vintage: str | None = None
    category: str | None = None
    benchmark: str | None = None
    inception_date: date | None = None


class PerformancePoint(BaseModel):
    model_config = ConfigDict(frozen=True)
    date: date
    value: float
    series_kind: Literal["NAV", "TWRR", "TRI", "valuation", "cash_flow"]


class PrivateMarketCashFlow(BaseModel):
    model_config = ConfigDict(frozen=True)
    date: date
    kind: CashFlowKind
    amount: float = Field(ge=0, allow_inf_nan=False)
    note: str | None = Field(default=None, max_length=200)


class Metric(BaseModel):
    model_config = ConfigDict(frozen=True)
    key: str
    label: str
    value: float | None
    unit: str
    period: str | None = None
    as_of: date | None = None
    source_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SourceResult(BaseModel):
    source_name: str
    available: bool
    products: list[ProductIdentity] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    performance_points: list[PerformancePoint] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error_code: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AIConclusion(BaseModel):
    text: str
    evidence_ids: list[str] = Field(min_length=1)


class AIAnalysis(BaseModel):
    available: bool = True
    pros: list[AIConclusion] = Field(default_factory=list)
    cons: list[AIConclusion] = Field(default_factory=list)
    outlook: AIConclusion | None = None
    fit: list[AIConclusion] = Field(default_factory=list)
    risks: list[AIConclusion] = Field(default_factory=list)
    monitoring: list[AIConclusion] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"] = "low"
    limitations: list[str] = Field(default_factory=list)


class ChartSpec(BaseModel):
    kind: Literal["growth_of_100k", "reported_performance", "cash_flow_timeline"]
    product: list[PerformancePoint] = Field(default_factory=list)
    benchmark: list[PerformancePoint] = Field(default_factory=list)


class AnalysisReport(BaseModel):
    identity: ProductIdentity
    status: AnalysisStatus
    evidence: list[EvidenceItem]
    metrics: list[Metric]
    ai: AIAnalysis | None = None
    chart: ChartSpec | None = None
    warnings: list[str] = Field(default_factory=list)
