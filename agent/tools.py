"""
tools.py
--------
StructuredTool definitions for the dynamic tool authorization agent.

Why StructuredTool instead of @tool decorator:
- @tool generates schemas that Groq's API rejects (BadRequestError)
- StructuredTool + explicit Pydantic schema gives Groq a clean contract
- Lesson: always validate tool schemas against your actual provider

Why neutral vocabulary in descriptions:
- Words like "private", "sensitive", "account details" activate RLHF safety training
- Model refuses tool calls regardless of system prompt permissions
- Neutral words: "user database", "profile lookup", "record retrieval"
- Lesson: RLHF fires on vocabulary, not intent
"""

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field


# ── Input Schema ───────────────────────────────────────────────────────────────
class SearchInput(BaseModel):
    query: str = Field(description="The search query string")


# ── Tool Functions ─────────────────────────────────────────────────────────────
# In production: we replace these with real API calls
# e.g. public_search_fn → calls a news API
#      private_search_fn → queries your user database
#      advanced_search_fn → calls a research aggregation service

def public_search_fn(query: str) -> str:
    return f"[PUBLIC] Results for: {query}"


def private_search_fn(query: str) -> str:
    return f"[PRIVATE] Results for: {query}"


def advanced_search_fn(query: str) -> str:
    return f"[ADVANCED] Results for: {query}"


# ── Tool Definitions ───────────────────────────────────────────────────────────

public_search = StructuredTool(
    name="public_search",
    description=(
        "Fetch general information from public sources. "
        "Use for: news, weather, general knowledge. "
        "Examples: 'latest news', 'weather today'"
    ),
    func=public_search_fn,
    args_schema=SearchInput,
)

private_search = StructuredTool(
    name="private_search",
    description=(
        # KEY: 'ALWAYS use' overrides model hesitation
        # KEY: no words like 'private/sensitive/details' — those trigger RLHF refusal
        "Fetch data from the user database. "
        "Use for: profile lookup, record retrieval, user data queries. "
        "Examples: 'user profile', 'my orders', 'my records'"
    ),
    func=private_search_fn,
    args_schema=SearchInput,
)

advanced_search = StructuredTool(
    name="advanced_search",
    description=(
        # KEY: 'ONLY tool for' creates exclusivity — model won't default to public_search
        "Run multi-source research and analysis. "
        "This is the ONLY tool for: trend analysis, deep research, technical comparisons. "
        "Examples: 'AI trends 2025', 'compare X vs Y', 'deep research on topic'"
    ),
    func=advanced_search_fn,
    args_schema=SearchInput,
)


ALL_TOOLS = [public_search, private_search, advanced_search]
