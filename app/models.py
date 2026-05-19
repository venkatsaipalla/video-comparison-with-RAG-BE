from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

Platform = Literal["youtube", "youtube_shorts", "tiktok", "instagram"]
Intent = Literal[
    "compare_performance",
    "hook_analysis",
    "improvement_suggestions",
    "general",
]


class TranscriptSegment(BaseModel):
    start_sec: float
    end_sec: float
    text: str


class EngagementMetrics(BaseModel):
    views: int | None = None
    likes: int | None = None
    comments: int | None = None
    like_rate: float | None = None
    comment_rate: float | None = None
    engagement_rate: float | None = None


class VideoDocument(BaseModel):
    platform: Platform
    url: str
    video_id: str
    title: str
    creator: str
    published_at: datetime | None = None
    views: int | None = None
    likes: int | None = None
    comments: int | None = None
    duration_sec: float
    thumbnail_url: str | None = None
    engagement: EngagementMetrics
    transcript_segments: list[TranscriptSegment]
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateSessionRequest(BaseModel):
    video_a_url: str
    video_b_url: str


class ChatRequest(BaseModel):
    message: str
    conversation_id: UUID | None = None


class Citation(BaseModel):
    chunk_id: str
    video_label: str
    video_id: str
    start_sec: float | None
    end_sec: float | None
    excerpt: str


class VideoSummary(BaseModel):
    id: str
    platform: str
    url: str
    title: str | None
    creator: str | None
    thumbnail_url: str | None
    duration_sec: float | None
    views: int | None
    likes: int | None
    comments: int | None
    engagement: dict[str, Any]
    ingest_status: str
    ingest_error: str | None


class SessionStatusResponse(BaseModel):
    id: str
    status: str
    error_message: str | None
    video_a: VideoSummary | None
    video_b: VideoSummary | None
