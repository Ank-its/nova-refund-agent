"""LangGraph assembly and convenience runner."""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.agent.nodes import ask_reason, clarify, decide, extract, route, smalltalk
from app.agent.state import AgentState


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("extract", extract)
    g.add_node("ask_reason", ask_reason)
    g.add_node("decide", decide)
    g.add_node("clarify", clarify)
    g.add_node("smalltalk", smalltalk)

    g.add_edge(START, "extract")
    g.add_conditional_edges(
        "extract",
        route,
        {
            "ask_reason": "ask_reason",
            "decide": "decide",
            "clarify": "clarify",
            "smalltalk": "smalltalk",
        },
    )
    for node in ("ask_reason", "decide", "clarify", "smalltalk"):
        g.add_edge(node, END)
    return g.compile()


GRAPH = build_graph()


async def run_agent(
    *,
    customer_id: int,
    user_text: str,
    history: list[dict] | None = None,
    pending_candidates: list[str] | None = None,
    pending_reason_for: str | None = None,
) -> AgentState:
    state: AgentState = {
        "user_text": user_text,
        "customer_id": customer_id,
        "history": history or [],
        "pending_candidates": pending_candidates or [],
        "pending_reason_for": pending_reason_for,
        "trace": [],
    }
    return await GRAPH.ainvoke(state)
