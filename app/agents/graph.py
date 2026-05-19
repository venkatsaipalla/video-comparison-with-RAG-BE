"""LangGraph workflow: route → retrieve context is invoked from chat service."""

from __future__ import annotations

from typing import Optional, TypedDict

from langgraph.graph import END, StateGraph

from app.agents.router import RouteResult, route_query


class GraphState(TypedDict):
    message: str
    route_result: Optional[RouteResult]


async def _route_node(state: GraphState) -> GraphState:
    result = await route_query(state["message"])
    return {"route_result": result}


def build_router_graph():
    graph = StateGraph(GraphState)
    graph.add_node("classify", _route_node)
    graph.set_entry_point("classify")
    graph.add_edge("classify", END)
    return graph.compile()


_router_graph = None


async def run_router(message: str) -> RouteResult:
    global _router_graph
    if _router_graph is None:
        _router_graph = build_router_graph()
    out = await _router_graph.ainvoke({"message": message, "route_result": None})
    return out["route_result"]
