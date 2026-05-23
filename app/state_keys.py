"""Single source of truth for ADK session state keys."""

# Locked at session creation (POST /ingest). Always exactly 2 video IDs.
VIDEO_IDS = "video_ids"

# Metadata cache. Empty initially; populated on-demand by the Retriever
# whenever the Planner sets needs_metadata=True. Survives across turns.
METADATA = "metadata"

# Transient per-turn keys (reset by before_agent_callback on rag_agent).
RETRIEVAL_PLAN = "retrieval_plan"   # JSON string from Planner
CONTEXT_CHUNKS = "context_chunks"   # list[dict] accumulated across loop iters
SEEN_TEXTS = "seen_texts"           # list[str], exact-text dedup key
GRADING = "grading"                 # JSON string from Grader

# Final outputs.
CONTEXT = "context"                 # written by Packer; consumed by Analysis
ANALYSIS = "analysis"               # written by analysis_agent
ANSWER = "answer"                   # written by final_agent
