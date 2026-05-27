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

# Analysis ecosystem (transient per-turn, reset by analysis_agent before_callback).
ANALYSIS_PLAN = "analysis_plan"             # AnalysisPlan from Router
ANALYSIS_SUMMARY = "analysis_summary"       # SummaryBrief from Summarizer
ANALYSIS_COMPARISON = "analysis_comparison" # ComparisonBrief from Comparator
ANALYSIS_VIRALITY = "analysis_virality"     # ViralityBrief from Virality
ANALYSIS_TIMELINE = "analysis_timeline"     # TimelineBrief from Timeline
ANALYSIS_METADATA = "analysis_metadata"     # MetadataBrief from MetadataLookup

ANALYSIS = "analysis"               # FinalAnalysis from deterministic Reducer; consumed by final_agent
ANSWER = "answer"                   # written by final_agent
