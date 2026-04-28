"""
middleware.py
-------------
Policy Enforcement Point (PEP) for tool access control.

Architecture decision: TWO separate concerns, handled separately.

CONCERN 1 — What tools does the MODEL see?
  → Controlled by passing all tools with guarded functions
  → Model sees clean descriptions, no leaked markers

CONCERN 2 — What if model calls a disallowed tool anyway?
  → Controlled by make_guarded_tool() wrapping the execution function
  → Returns __ACCESS_DENIED__ instead of executing
"""

from langchain_core.tools import StructuredTool
from langchain.agents.middleware import wrap_model_call, ModelResponse, ModelRequest
from typing import Callable


def make_guarded_tool(tool: StructuredTool, allowed_names: set) -> StructuredTool:
    """
    Wraps a tool's execution function with a permission check.

    If the tool name is not in allowed_names:
      - Function returns '__ACCESS_DENIED__' instead of executing
      - Model receives the denial as a tool result
      - clean_response() strips it before showing to user

    Tool name stays IDENTICAL → agent registry never breaks.
    Tool description stays IDENTICAL → no leaked markers in model reasoning.

    Args:
        tool:          The original StructuredTool to wrap
        allowed_names: Set of tool names permitted in this request

    Returns:
        New StructuredTool with same name/description but guarded function
    """
    original_fn = tool.func
    tool_name   = tool.name

    def guarded_fn(query: str) -> str:
        if tool_name not in allowed_names:
            # Hard block at execution level
            # Fires even if model ignores routing guidance
            return "__ACCESS_DENIED__"
        return original_fn(query)

    return StructuredTool(
        name=tool.name,                 # ← SAME name, registry intact
        description=tool.description,  # ← SAME description, no leaked markers
        func=guarded_fn,               # ← wrapped with permission check
        args_schema=tool.args_schema,
    )


@wrap_model_call
def state_based_tools(
    request: ModelRequest,
    handler: Callable[[ModelRequest], ModelResponse]
) -> ModelResponse:
    """
    Middleware that enforces tool access policy based on conversation state.

    Policy rules:
      - Unauthenticated user       → public_search only
      - Authenticated, < 5 msgs   → public_search + private_search
      - Authenticated, 5+ msgs    → all tools

    Why message_count matters:
      In real systems, longer conversations signal established sessions
      where advanced/expensive tools become appropriate.
      This is a simplified model of progressive trust.

    Args:
        request: Current model request (contains state, tools, messages)
        handler: Next handler in middleware chain

    Returns:
        ModelResponse after enforcing policy
    """
    state            = request.state
    is_authenticated = state.get("authenticated", False)
    message_count    = len(state["messages"])

    # ── Determine allowed tools by policy ────────────────────────────────────
    if not is_authenticated:
        allowed_names = {"public_search"}
    elif message_count < 5:
        allowed_names = {"public_search", "private_search"}
    else:
        allowed_names = {"public_search", "private_search", "advanced_search"}

    # ── Wrap ALL tools with permission guards ─────────────────────────────────
    # Disallowed tools get guarded functions → return ACCESS_DENIED if called
    all_guarded_tools = [
        make_guarded_tool(t, allowed_names)
        for t in request.tools
    ]

    response = handler(request.override(tools=all_guarded_tools))

    # ── Post-call audit: log policy violations ────────────────────────────────
    # In production: send to Datadog, LangSmith, or your audit system
    for msg in getattr(response, "messages", []):
        for tc in getattr(msg, "tool_calls", []):
            if tc["name"] not in allowed_names:
                print(
                    f"  🚨 POLICY VIOLATION: model called '{tc['name']}' "
                    f"(allowed: {allowed_names}) — execution blocked by guard"
                )

    return response
