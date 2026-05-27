"""Pydantic schemas used as ADK LlmAgent `output_schema` for structured JSON output.

OpenAI structured outputs strict mode rules (the reason this file looks the
way it does):
1. Every field listed in `properties` MUST also appear in `required` — so
   no Pydantic field has a default. Nullable fields use `T | None` (the
   LLM emits null when it has no value).
2. Every object must set `additionalProperties: false` — enforced via
   `ConfigDict(extra='forbid')` on every model.
3. `dict[str, X]` with arbitrary keys is NOT allowed. Per-video data is
   therefore modeled as `list[Entry]` where each Entry carries `video_id`.
   The deterministic Reducer converts these lists back into
   dict[video_id, …] when writing state["analysis"], so downstream
   consumers (Final agent) get the convenient dict shape.

Field descriptions are propagated into the JSON Schema sent to OpenAI and
help the model emit semantically correct values.
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


Confidence = Literal["high", "medium", "low"]
Dimension = Literal["summary", "comparison", "virality", "timeline", "metadata"]


# ---------- RAG ----------

class PlannerQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    q: str = Field(..., description="Self-contained retrieval query string after rewriting.")
    video_ids: list[str] = Field(
        ..., description="Subset of session video_ids this query targets (1 or 2 items)."
    )
    top_k: int = Field(
        ..., description="Number of top chunks to retrieve from the GPU repo. Typical 5."
    )


class RetrievalPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    needs_metadata: bool = Field(
        ...,
        description=(
            "True only if the user explicitly asks about title/channel/views/"
            "likes/upload_date/duration AND that metadata is not already cached."
        ),
    )
    needs_chunks: bool = Field(
        ...,
        description="True if transcript chunks are needed. False only for pure metadata questions.",
    )
    queries: list[PlannerQuery] = Field(
        ...,
        description="1-3 retrieval queries. Empty array only when needs_chunks=false.",
    )


class GradingResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sufficient: bool = Field(
        ...,
        description=(
            "True if retrieved chunks contain concrete evidence (quotes, timestamps, "
            "or metadata) that would let a downstream writer answer with citations."
        ),
    )
    missing_aspects: list[str] = Field(
        ...,
        description=(
            "Short phrases naming aspects of the question that are NOT covered by "
            "the chunks. Empty list when sufficient=true."
        ),
    )
    reason_brief: str = Field(
        ..., description="One short sentence explaining the grading decision."
    )


# ---------- Analysis: shared ----------

class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quote: str = Field(
        ..., description="Verbatim chunk text. May end with '...' if trimmed."
    )
    video_id: str | None = Field(
        ..., description="The chunk's video_id. Null only if the chunk source is unknown."
    )
    start_time: float | None = Field(
        ..., description="Seconds from the start of the video. Null if the chunk has no timestamp."
    )
    end_time: float | None = Field(
        ..., description="Seconds from the start of the video. Null if the chunk has no timestamp."
    )


# ---------- Analysis: planner ----------

class AnalysisPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dimensions: list[Dimension] = Field(
        ...,
        description=(
            "1-3 analysis dimensions to run for this turn. Pick the smallest set "
            "that answers the user's latest question."
        ),
    )
    rationale_brief: str = Field(
        ...,
        description=(
            "One short sentence justifying the dimension choice. If using the "
            "last-resort fallback, MUST start with 'fallback:'."
        ),
    )


# ---------- Analysis: specialists ----------

class VideoSummaryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    video_id: str = Field(..., description="The video this summary entry is for.")
    summary: str = Field(
        ..., description="1-3 sentence summary focused on the user's latest question."
    )
    key_points: list[str] = Field(
        ..., description="2-5 short bullet strings of the main points for this video."
    )
    evidence: list[Evidence] = Field(
        ..., description="1-4 evidence quotes supporting the summary, with timestamps."
    )


class SummaryBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")
    skipped: bool = Field(
        ..., description="True if this specialist was gated off by the Router."
    )
    per_video: list[VideoSummaryEntry] = Field(
        ..., description="One entry per video_id present in retrieved chunks."
    )
    confidence: Confidence = Field(
        ...,
        description=(
            "high if every claim has supporting evidence; medium if partial; "
            "low if any video lacks usable chunks."
        ),
    )


class ComparisonBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")
    skipped: bool = Field(
        ..., description="True if this specialist was gated off by the Router."
    )
    similarities: list[str] = Field(
        ..., description="0-4 short bullets noting shared aspects across both videos."
    )
    differences: list[str] = Field(
        ..., description="1-4 short bullets — typically the most important list."
    )
    verdict: str = Field(
        ...,
        description=(
            "One sentence answering the comparative question. For neutral "
            "questions, a one-line summary of the key contrast."
        ),
    )
    evidence: list[Evidence] = Field(
        ..., description="2-6 evidence quotes, ideally spanning both videos."
    )
    confidence: Confidence = Field(
        ...,
        description=(
            "high with two-sided grounded evidence; medium if one-sided; "
            "low if either side is inferred."
        ),
    )


class ViralitySignalEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    video_id: str = Field(..., description="The video these signals belong to.")
    signals: list[str] = Field(
        ...,
        description=(
            "2-5 short concrete strings describing performance signals "
            "(hook strength, pacing, like-ratio numbers, etc.)."
        ),
    )


class ViralityBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")
    skipped: bool = Field(
        ..., description="True if this specialist was gated off by the Router."
    )
    per_video_signals: list[ViralitySignalEntry] = Field(
        ..., description="One signals entry per video_id."
    )
    verdict: str = Field(
        ...,
        description=(
            "1-2 sentences naming which video performed better and the primary "
            "reason(s). Acknowledge missing metadata if applicable."
        ),
    )
    evidence: list[Evidence] = Field(
        ...,
        description=(
            "2-5 evidence quotes pulled from transcript chunks (NOT metadata) "
            "that explain the signals."
        ),
    )
    confidence: Confidence = Field(
        ...,
        description=(
            "high if both metadata AND content evidence are present; medium "
            "if only one; low if inferred."
        ),
    )


class HookWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    video_id: str = Field(..., description="The video this hook window is from.")
    start_time: float | None = Field(
        ..., description="Window start in seconds. Null only if the chunk has no timestamp."
    )
    end_time: float | None = Field(
        ..., description="Window end in seconds. Null only if the chunk has no timestamp."
    )
    quote: str = Field(
        ..., description="Verbatim quote from the chunk in this window."
    )


class TimelineBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")
    skipped: bool = Field(
        ..., description="True if this specialist was gated off by the Router."
    )
    per_video_hooks: list[HookWindow] = Field(
        ...,
        description=(
            "One HookWindow per video_id that has time-anchored chunks. Omit "
            "any video that has no time-anchored chunks (do not emit a null entry)."
        ),
    )
    notable_moments: list[Evidence] = Field(
        ...,
        description=(
            "1-4 additional time-anchored Evidence items across both videos. "
            "All entries must have non-null start_time."
        ),
    )
    confidence: Confidence = Field(
        ...,
        description=(
            "high if both videos have time-anchored chunks; medium if one; "
            "low if inferred."
        ),
    )


class MetadataEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    video_id: str = Field(..., description="The video this metadata entry is for.")
    title: str | None = Field(..., description="Video title from the platform.")
    channel: str | None = Field(..., description="Uploading channel name.")
    duration: int | None = Field(..., description="Total duration in seconds.")
    upload_date: str | None = Field(..., description="Upload date in YYYYMMDD format.")
    view_count: int | None = Field(..., description="Total view count at retrieval time.")
    like_count: int | None = Field(..., description="Total like count at retrieval time.")


# MetadataBrief is written by a deterministic agent (no LLM), so it does
# not need to be OpenAI-strict-compatible. Kept here for documentation.
class MetadataBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")
    skipped: bool = Field(
        ..., description="True if this specialist was gated off by the Router."
    )
    per_video: list[MetadataEntry] = Field(
        ..., description="One MetadataEntry per video_id with cached metadata."
    )
