from google.adk.agents import SequentialAgent

from app.agents.analysis_agent import analysis_agent
from app.agents.final_agent import final_agent
from app.agents.rag import rag_agent

# Sequential chain: RAG -> Analysis -> Final.
# Each child writes to its own state key (rag_plan, analysis, answer)
# so the next stage can read upstream output without re-tokenizing.
pipeline_agent = SequentialAgent(
    name="pipeline",
    description="Runs the RAG -> Analysis -> Final response chain for video analysis queries.",
    sub_agents=[rag_agent, analysis_agent, final_agent],
)
