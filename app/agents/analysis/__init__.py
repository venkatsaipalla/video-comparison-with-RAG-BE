from google.adk.agents import ParallelAgent, SequentialAgent
from google.adk.agents.callback_context import CallbackContext

from app import state_keys as K
from app.agents.analysis.comparator import comparator_agent
from app.agents.analysis.metadata_lookup import metadata_lookup_agent
from app.agents.analysis.reducer import reducer_agent
from app.agents.analysis.router import router_agent
from app.agents.analysis.summarizer import summarizer_agent
from app.agents.analysis.timeline import timeline_agent
from app.agents.analysis.virality import virality_agent


def _reset_transient(callback_context: CallbackContext) -> None:
    """Clear per-turn analysis state at the start of every run."""
    s = callback_context.state
    s[K.ANALYSIS_PLAN] = ""
    s[K.ANALYSIS_SUMMARY] = ""
    s[K.ANALYSIS_COMPARISON] = ""
    s[K.ANALYSIS_VIRALITY] = ""
    s[K.ANALYSIS_TIMELINE] = ""
    s[K.ANALYSIS_METADATA] = ""
    return None


specialists_parallel = ParallelAgent(
    name="analysis_specialists",
    description="Runs the selected analysis specialists in parallel; gated specialists no-op.",
    sub_agents=[
        summarizer_agent,
        comparator_agent,
        virality_agent,
        timeline_agent,
        metadata_lookup_agent,
    ],
)


analysis_agent = SequentialAgent(
    name="analysis_agent",
    description="Router -> parallel specialists -> reducer. Writes state['analysis'].",
    sub_agents=[router_agent, specialists_parallel, reducer_agent],
    before_agent_callback=_reset_transient,
)
