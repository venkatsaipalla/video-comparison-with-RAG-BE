"""LangGraph workflow: route → retrieve context is invoked from chat service."""

from typing import TypedDict

from langgraph.graph import END, StateGraph

from app.agents.router import RouteResult, route_query


class GraphState(TypedDict):
    message: str
    route: RouteResult | None


async def _route_node(state: GraphState) -> GraphState:
    result = await route_query(state["message"])
    return {"message": state["message"], "route": result}


def build_router_graph():
    graph = StateGraph(GraphState)
    graph.add_node("route", _route_node)
    graph.set_entry_point("route")
    graph.add_edge("route", END)
    return graph.compile()


_router_graph = None


async def run_router(message: str) -> RouteResult:
    global _router_graph
    if _router_graph is None:
        _router_graph = build_router_graph()
    out = await _router_graph.ainvoke({"message": message, "route": None})
    return out["route"]
