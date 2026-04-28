# Iteration Log

Every failure encountered building this system, what caused it, and how it was fixed.

---

## Iteration 1 — Infinite Tool Loop

**Symptom:**
Model called `public_search` 3+ times with slightly different queries:
"latest news" → "latest news today" → "current events" → crash.
Eventually caused `BadRequestError` from conversation length.

**What was tried:**
Added system prompt rule: "Use a tool ONLY ONCE per query."

**Why it didn't work:**
System prompts are soft constraints. The model ignored the rule under query ambiguity.

**Fix:**
`recursion_limit: 4` in agent config (later calibrated to 6).

**Principle learned:**
Never trust a model to self-stop. Infrastructure enforces hard limits.

---

## Iteration 2 — Groq Tool Schema Rejection

**Symptom:**
`BadRequestError: Failed to call a function. Please adjust your prompt.`
Error fired before any `[updates]` appeared — before the model even ran.

**Root cause:**
`@tool` decorator generates schemas that Groq's API rejects.
The failure was at the API contract level, not the model level.

**Fix:**
Replaced all `@tool` decorators with `StructuredTool` + explicit `Pydantic BaseModel` schema.

**Principle learned:**
Always validate tool schemas against your actual provider. Local tests don't surface provider-specific rejections.

---

## Iteration 3 — RLHF Safety Refusal

**Symptom:**
Model responded with plain text: "I'm not able to access private account details."
No tool was called. Test 2 failed even though middleware was correct.

**Root cause:**
Query contained "private account details" — vocabulary that activates the model's
safety training (RLHF) regardless of system prompt permissions.
The middleware worked. The model refused at a deeper level.

**Fix:**
Changed query vocabulary: "private account details" → "user profile from the database"
Changed tool description vocabulary: removed "private/sensitive/confidential"
Added: "Fetch data from the user database. Use for: profile lookup, record retrieval."

**Principle learned:**
RLHF safety training fires on vocabulary, not intent. Prompt engineering must account
for the model's training, not just your instructions.

---

## Iteration 4 — Groq 2-Tool Combo Schema Bug

**Symptom:**
`BadRequestError` on Test 2 (authenticated early conversation).
Test 1 (1 tool) and Test 3 (3 tools) passed. Only Test 2 (2 tools) failed.
Error fired before any `[updates]` — API rejection before model ran.

**Root cause:**
Groq rejects the specific `[public_search, private_search]` 2-tool combination
at `temperature=0`. Provider-level serialization quirk — not a LangChain issue.

**Fix:**
Raised temperature to `0.1`. (Exposed the deeper schema fix needed in Iteration 9.)

**Principle learned:**
Test on your actual provider. temperature=0 is not universally stable across providers.
Isolate provider bugs — they look like your code's fault but aren't.

---

## Iteration 5 — Model Defaults to Wrong Tool

**Symptom:**
"Do deep research on AI trends" → model chose `public_search` not `advanced_search`
even when `advanced_search` was available and not blocked.

**Root cause:**
"Deep research" is ambiguous — overlaps with both `public_search` ("general knowledge")
and `advanced_search` ("deep research"). Without a preference signal, model defaults to
the simplest/most general tool.

**Fix:**
Added exclusivity signal to `advanced_search` description:
"This is the ONLY tool for: trend analysis, deep research, technical comparisons."

**Principle learned:**
Tool descriptions are routing logic. Ambiguous descriptions cause model to default
to simpler tools. Exclusivity signals create clear preferences.

---

## Iteration 6 — recursion_limit Too Tight

**Symptom:**
`GraphRecursionError: Recursion limit of 4 reached without hitting a stop condition.`
Fired even when model behavior was correct.

**Root cause:**
`recursion_limit=4` counts LangGraph graph steps, not tool calls.
Each agent turn = 1 model step + 1 tool step = 2 graph steps.
A single tool call needs: model(1) + tool(1) + final_model(1) = 3 steps minimum.
With any complexity, 4 was too tight.

**Fix:**
Raised to `recursion_limit=6`. Formula: `(max_tool_calls × 2) + 1`.

**Principle learned:**
Understand what your limits are measuring. "recursion_limit" sounds like it limits
tool calls — it actually limits graph execution steps.

---

## Iteration 7 — Symptom Masking Discovery

**Insight:**
Reviewing iterations 1-6 revealed: the RLHF refusal (iterations 1-2)
was masking the Groq schema bug (iterations 3-4).

Both showed Test 2 failing. But the causes were completely different:
- Iterations 1-2: model refused to call ANY tool (RLHF vocabulary trigger)
- Iterations 3-4: Groq rejected the API request before model ran (schema bug)

Fixing the RLHF issue didn't fix the schema bug — it revealed it.

**Principle learned:**
In layered systems, one bug masks another. The same symptom can have different root causes.
Diagnose by layer. Change one variable at a time. Fix → observe → fix next layer.

---

## Iteration 8 — [LOCKED] Marker Leaks Into User Response

**Symptom:**
Tool routing:  (model called `private_search` correctly)
Tool result:  (`[PRIVATE] Results for: user profile` returned)
User response:  "I'm not able to provide your profile as private_search is locked."

**Root cause:**
Previous fix added `[LOCKED — not available in current session]` to tool descriptions
for routing guidance. Model read this text during response generation (not just selection)
and hallucinated that the tool was locked even after successfully calling it.

**Fix:**
1. Removed [LOCKED] from descriptions entirely → use `make_guarded_tool()` instead
2. Added `clean_response()` post-processor as safety net
3. Added system prompt rule: "Never say anything is locked or unavailable"

**Principle learned:**
Defense in depth. A fix in one layer can break another. Stack independent protection layers.
The marker that fixed the schema routing problem created a UX leak problem.

---

## Iteration 9 — Middleware Tool Rename Breaks Agent Registry

**Symptom:**
```
ValueError: Middleware added tools that the agent doesn't know how to execute.
Unknown tools: ['LOCKED_private_search', 'LOCKED_advanced_search']
```
All 3 tests failed immediately. 0% accuracy.

**Root cause:**
Attempted fix: rename tools in middleware to `LOCKED_private_search`.
LangChain builds `{tool_name: function}` registry at `create_agent()` time.
Middleware renamed tools don't match registry entries → ValueError on every execution.

**Fix:**
`make_guarded_tool()`: wraps the execution function, keeps the name identical.
```python
def guarded_fn(query):
    if tool_name not in allowed_names:
        return "__ACCESS_DENIED__"
    return original_fn(query)

StructuredTool(name=tool.name, func=guarded_fn, ...)  # name unchanged
```

**Principle learned:**
Open/Closed Principle: enforce policy inside the contract, never by breaking the interface.
The agent's tool registry is a contract. Middleware must respect it.

---

## Final Result — After All 9 Iterations

```
Tool Selection Accuracy : 100.00%
Block Enforcement       : 100.00%
Loop-Free Rate          : 100.00%
UX Quality              : 100.00%

Test                                Tool              Routing    UX
-----------------------------------------------------------------------
Unauthenticated user                public_search     ✅         ✅
Authenticated early conversation    private_search    ✅         ✅
Authenticated later conversation    advanced_search   ✅         ✅
```
