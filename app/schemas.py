"""Pydantic schemas used as ADK LlmAgent `output_schema` for structured JSON output."""
from typing import Literal

from pydantic import BaseModel, Field


# ---------- RAG ----------

class PlannerQuery(BaseModel):
    q: str = Field(..., description="Self-contained retrieval query string.")
    video_ids: list[str] = Field(
        ..., description="Subset of session video_ids this query targets."
    )
    top_k: int = Field(5, ge=1, le=20)


class RetrievalPlan(BaseModel):
    needs_metadata: bool = False
    needs_chunks: bool = True
    queries: list[PlannerQuery] = Field(default_factory=list, max_length=3)


class GradingResult(BaseModel):
    sufficient: bool
    missing_aspects: list[str] = Field(default_factory=list)
    reason_brief: str = ""


# ---------- Analysis ----------

Confidence = Literal["high", "medium", "low"]
Dimension = Literal["summary", "comparison", "virality", "timeline", "metadata"]


class Evidence(BaseModel):
    """One grounded citation. start_time/end_time in seconds, video_id from chunk payload."""
    quote: str
    video_id: str | None = None
    start_time: float | None = None
    end_time: float | None = None


class VideoSummary(BaseModel):
    summary: str = ""
    key_points: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)


class AnalysisPlan(BaseModel):
    dimensions: list[Dimension] = Field(default_factory=list, max_length=3)
    rationale_brief: str = ""


class SummaryBrief(BaseModel):
    skipped: bool = False
    per_video: dict[str, VideoSummary] = Field(default_factory=dict)
    confidence: Confidence = "medium"


class ComparisonBrief(BaseModel):
    skipped: bool = False
    similarities: list[str] = Field(default_factory=list)
    differences: list[str] = Field(default_factory=list)
    verdict: str = ""
    evidence: list[Evidence] = Field(default_factory=list)
    confidence: Confidence = "medium"


class ViralityBrief(BaseModel):
    skipped: bool = False
    per_video_signals: dict[str, list[str]] = Field(default_factory=dict)
    verdict: str = ""
    evidence: list[Evidence] = Field(default_factory=list)
    confidence: Confidence = "medium"


class HookWindow(BaseModel):
    start_time: float | None = None
    end_time: float | None = None
    quote: str = ""


class TimelineBrief(BaseModel):
    skipped: bool = False
    per_video_hooks: dict[str, HookWindow] = Field(default_factory=dict)
    notable_moments: list[Evidence] = Field(default_factory=list)
    confidence: Confidence = "medium"


class MetadataBrief(BaseModel):
    skipped: bool = False
    per_video: dict[str, dict] = Field(default_factory=dict)


class FinalAnalysis(BaseModel):
    dimensions_used: list[Dimension] = Field(default_factory=list)
    confidence: Confidence = "medium"
    grounded: bool = True
    notes: str = ""
    per_video_summary: dict[str, VideoSummary] = Field(default_factory=dict)
    comparison: ComparisonBrief | None = None
    virality: ViralityBrief | None = None
    timeline: TimelineBrief | None = None
    metadata_view: dict[str, dict] | None = None
