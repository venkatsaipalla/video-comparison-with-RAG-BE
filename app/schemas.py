"""Pydantic schemas used as ADK LlmAgent `output_schema` for structured JSON output."""
from pydantic import BaseModel, Field


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
