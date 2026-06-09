"""LLM boundary: builds the configured provider's chat model.

``make_agent_model`` returns the model the tool-calling agent drives
(``agent/graph.py``); ``compose_title`` names a conversation. All prompts live in
``agent/prompts.py``. The provider (OpenAI / Anthropic / Google) is set via
config; with no key the callers fall back so the app still runs.
"""
from __future__ import annotations

from app.agent.prompts import TITLE_PROMPT
from app.core.config import get_settings


def _make_chat(temperature: float):
    """Build a LangChain chat model for the configured provider, or None if no
    key is set. Provider imports are local so only the selected SDK is loaded.
    """
    settings = get_settings()
    if not settings.llm_enabled:
        return None
    provider = settings.provider
    model = settings.active_model
    key = settings.active_api_key

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=model, api_key=key, temperature=temperature)
    if provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=model, google_api_key=key, temperature=temperature
        )
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(model=model, api_key=key, temperature=temperature)


def make_agent_model():
    """The chat model the tool-calling agent drives (temperature 0), or None."""
    return _make_chat(temperature=0)


def _fallback_title(message: str) -> str:
    title = " ".join((message or "").split()[:6]).strip()
    return title[:60] or "New conversation"


async def compose_title(first_message: str) -> str:
    """A short conversation title (LLM, with a plain fallback)."""
    chat = _make_chat(temperature=0.2)
    if chat is None:
        return _fallback_title(first_message)
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        msg = await chat.ainvoke([SystemMessage(TITLE_PROMPT), HumanMessage(first_message)])
        title = (msg.content or "").strip().strip('"').strip()
        return title[:60] or _fallback_title(first_message)
    except Exception:
        return _fallback_title(first_message)
