from google.adk.agents import LoopAgent, SequentialAgent
from google.adk.agents.callback_context import CallbackContext

from app import state_keys as K
from app.agents.rag.grader import grader_agent, escalation_check
from app.agents.rag.packer import packer_agent
from app.agents.rag.planner import planner_agent
from app.agents.rag.retriever import retriever_agent


def _reset_transient(callback_context: CallbackContext) -> None:
    """Clear per-turn transient state at the start of every RAG run."""
    s = callback_context.state
    s[K.RETRIEVAL_PLAN] = ""
    s[K.CONTEXT_CHUNKS] = []
    s[K.SEEN_TEXTS] = []
    s[K.GRADING] = ""
    return None


retrieval_loop = LoopAgent(
    name="retrieval_loop",
    description="Plan -> retrieve -> grade. Escalates on sufficient grading.",
    sub_agents=[planner_agent, retriever_agent, grader_agent, escalation_check],
    max_iterations=2,
)


rag_agent = SequentialAgent(
    name="rag_agent",
    description="Self-corrective RAG: planner-rewriter + retriever + grader loop, then packer.",
    sub_agents=[retrieval_loop, packer_agent],
    before_agent_callback=_reset_transient,
)
