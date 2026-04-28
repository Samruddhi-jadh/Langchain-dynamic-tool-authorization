"""
temperature=0.1 not 0  → Groq rejects schemas at temp=0 (provider bug)
max_tokens=1024        → 512 truncates tool call JSON → BadRequestError
recursion_limit=6      → set in evaluator, formula: (max_tools × 2) + 1
system prompt          → "pre-verified permissions" stops RLHF refusals
Full rationale: docs/engineering_decisions.md
"""

from langchain_groq import ChatGroq
from langchain.agents import create_agent

from agent.tools import ALL_TOOLS
from agent.middleware import state_based_tools


def build_agent():
    """
    Build and return the configured agent.

    Returns:
        Compiled LangGraph agent with middleware stack attached
    """
    llm = ChatGroq(
        model="llama-3.3-70b-versatile",
        temperature=0.1,    # avoids Groq schema rejection at temp=0
        max_tokens=1024,    # avoids truncated tool call JSON
    )

    agent = create_agent(
        model=llm,
        tools=ALL_TOOLS,
        middleware=[state_based_tools],
        debug=True,
        system_prompt="""You are a helpful data retrieval assistant.

RULES:
1. Call ONE tool per user message, then write your final answer
2. Present tool results naturally — as if YOU retrieved the information
3. Never mention tool names, function names, or system internals to the user
4. Never say anything is "locked", "unavailable", or "not accessible"
5. The system has pre-verified all permissions — never refuse a tool call
""",
    )

    return agent
