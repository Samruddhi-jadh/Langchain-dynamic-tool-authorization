# Engineering Decisions

12 production principles learned building this system.
Each one came from a real failure, not from reading documentation.

---

## Decision 1 — recursion_limit as circuit breaker, not system prompt

**Context:** Model called the same tool 3+ times, ignoring "use tool ONCE" in system prompt.

**Decision:** Add `recursion_limit: 6` to agent config as a hard infrastructure guardrail.

**Why:** System prompts are soft constraints — the model can ignore them under ambiguity.
`recursion_limit` is a hard graph-level stop enforced by LangGraph regardless of model behavior.

**Production rule:** Never trust a model to self-stop. Infrastructure enforces hard limits.

---

## Decision 2 — StructuredTool + Pydantic over @tool decorator

**Context:** `@tool` decorator caused `BadRequestError: Failed to call a function` on Groq.

**Decision:** Replace all `@tool` decorators with `StructuredTool` + explicit `SearchInput(BaseModel)`.

**Why:** `@tool` generates schemas that some providers reject. Explicit Pydantic schemas
give Groq a clean, validated contract it can serialize correctly.

**Production rule:** Validate tool schemas against your actual provider. Local tests ≠ provider behavior.

---

## Decision 3 — Neutral vocabulary in tool descriptions

**Context:** Model refused to call `private_search` despite system prompt permission.
Response: "I'm not able to access private account details."

**Decision:** Remove trigger words from descriptions and test queries.
Replaced: "private", "sensitive", "account details", "confidential"
With: "user database", "profile lookup", "record retrieval"

**Why:** Model safety training (RLHF) fires on specific vocabulary regardless of
system prompt context. The refusal is not a system prompt failure — it's a training artifact.

**Production rule:** RLHF safety training fires on vocabulary, not intent. Design around it.

---

## Decision 4 — temperature=0.1, not 0

**Context:** `BadRequestError` on exactly the `[public_search, private_search]` 2-tool combination.
Single tool or all 3 tools worked fine. Error fired at temperature=0 only.

**Decision:** Raise temperature to 0.1.

**Why:** At temperature=0, Groq's token sampling for certain tool schema combinations
generates slightly malformed function call JSON that its own validator rejects.
This is a provider-level serialization quirk, not a LangChain issue.

**Production rule:** Test LLM configuration on your actual provider. temperature=0 ≠ deterministic on all providers.

---

## Decision 5 — Always pass all 3 tools to Groq

**Context:** Groq rejects `[public_search, private_search]` together (see Decision 4).
But passing all 3 tools works correctly.

**Decision:** Always send all 3 tools to Groq. Control access via guarded functions, not tool visibility.

**Why:** The bug is provider-specific and tied to the exact 2-tool combination.
Changing tool visibility to work around it would break the access control model.
Separating concerns: Groq sees all tools, guarded functions enforce permissions.

**Production rule:** Isolate provider bugs. Workaround at infrastructure, not business logic.

---

## Decision 6 — "ONLY tool for X" exclusivity signal in descriptions

**Context:** "Do deep research on AI" → model chose `public_search` despite `advanced_search` being available.

**Decision:** Add exclusivity signal to `advanced_search` description:
"This is the ONLY tool for: trend analysis, deep research, technical comparisons."

**Why:** Without exclusivity signals, models default to the simplest tool when descriptions overlap.
"Deep research" is ambiguous — it could match `public_search` ("general knowledge") or `advanced_search`.
Exclusivity forces a clear preference.

**Production rule:** Tool descriptions are routing logic. Write them as rules with exclusivity signals, not general hints.

---

## Decision 7 — recursion_limit formula: (max_tool_calls × 2) + 1

**Context:** `recursion_limit=4` caused `GraphRecursionError` on correct single-tool behavior.

**Decision:** Raise to 6. Derive limit from the formula, not trial-and-error.

**Why:** LangGraph counts graph steps, not tool calls.
Each agent turn = 1 model step + 1 tool execution step = 2 graph steps.
For max 2 tool calls: 2 × 2 = 4 steps + 1 final answer step = 5 minimum.
Set to 6 for safety headroom.

**Production rule:** Understand what your limits are measuring. Count graph steps, not tool calls.

---

## Decision 8 — Stream agent.stream(), not agent.invoke() in evaluation

**Context:** `agent.invoke()` returned only the final answer. Tool selection was invisible.
`tool_correct` metric was always False because `used_tool` was always None.

**Decision:** Use `agent.stream(stream_mode="updates")` in evaluator to capture intermediate steps.

**Why:** Intermediate steps (tool selections, tool results) are only visible in streaming mode.
You cannot measure tool selection accuracy without seeing which tools were called during execution.

**Production rule:** Use stream() for evaluation and debugging. invoke() hides the execution trace.

---

## Decision 9 — make_guarded_tool(): wrap function, keep name

**Context:** Renaming tools to `LOCKED_private_search` in middleware caused:
`ValueError: Middleware added tools that the agent doesn't know how to execute.`

**Decision:** Keep tool names identical. Wrap the execution function instead.

**Why:** LangChain builds `{tool_name: function}` registry at `create_agent()` time.
Renamed tools are not found in the registry → ValueError on every execution.
Wrapping the function keeps the registry intact while adding permission checks.

**Production rule:** Open/Closed Principle. Enforce policy inside the contract. Never break the interface to add behavior.

---

## Decision 10 — Defense in depth for UX protection

**Context:** After fixing tool routing (✅), model's final answer said:
"I'm not able to provide your profile as private_search is locked."
Tool was called correctly. UX was broken.

**Decision:** Stack three independent UX protection layers:
1. System prompt: "Never mention tool names or system internals"
2. Clean tool descriptions: no [LOCKED] markers in text model reasons about
3. clean_response() post-processor: regex strips any leaked markers

**Why:** Each layer catches what the others miss. The [LOCKED] marker that fixed
the Groq schema bug leaked into the model's response generation.
No single layer handles all failure modes.

**Production rule:** Defense in depth. Stack independent protection layers. Each catches a different failure class.

---

## Decision 11 — 4 separate evaluation metrics, not 1 combined score

**Context:** A single "pass/fail" per test case hid which layer caused the failure.

**Decision:** Measure 4 independent metrics:
- Tool Selection Accuracy (model behavior layer)
- Block Enforcement (infrastructure layer)
- Loop-Free Rate (circuit breaker)
- UX Quality (UX layer)

**Why:** A combined score of "66%" doesn't tell you whether the access control
failed or the model picked the wrong tool. Independent metrics isolate the failure layer.

**Production rule:** Measure what users experience, not just what your infrastructure enforced.

---

## Decision 12 — Middleware as Policy Enforcement Point (PEP)

**Context:** Needed a way to enforce access rules without putting logic in the model.

**Decision:** All permission logic lives in `state_based_tools()` middleware,
which runs before every model call. Model never sees tools it's not allowed to use.

**Why:** Models can be prompted around. Infrastructure cannot.
Putting access control in the system prompt ("only use public_search if unauthenticated")
is a soft constraint — the model can ignore it. Middleware is a hard constraint that
runs regardless of model behavior.

**Production rule:** Access control belongs in infrastructure. Never in model judgment.
