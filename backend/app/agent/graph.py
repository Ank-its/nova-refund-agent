"""The tool-calling agent: a LangGraph ReAct loop (START → agent ⇄ tools → END).

The LLM decides each turn whether to call a tool or answer; tools_condition loops
back through the tools until it produces a final, tool-free reply. The model
orchestrates but never decides — submit_refund enforces the policy. GRAPH is None
when no LLM key is set; the chat route then uses the deterministic fallback.
"""
from __future__ import annotations

from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from app.agent.llm import make_agent_model
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.tools import TOOLS


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]


def build_graph():
    model = make_agent_model()
    if model is None:
        return None
    llm = model.bind_tools(TOOLS)

    async def agent(state: AgentState) -> dict:
        msgs = state["messages"]
        # Lead every turn with the system prompt without persisting it into the
        # accumulating message history.
        if not msgs or not isinstance(msgs[0], SystemMessage):
            msgs = [SystemMessage(content=SYSTEM_PROMPT), *msgs]
        response = await llm.ainvoke(msgs)
        return {"messages": [response]}

    g = StateGraph(AgentState)
    g.add_node("agent", agent)
    g.add_node("tools", ToolNode(TOOLS))
    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", tools_condition)
    g.add_edge("tools", "agent")
    return g.compile()


GRAPH = build_graph()
