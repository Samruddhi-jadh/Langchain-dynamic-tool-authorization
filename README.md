# LangChain Dynamic Tool Authorization Agent

A production-grade AI agent demonstrating **state-based tool access control**
using LangChain middleware, Groq (Llama 3.3-70b), and a 4-metric evaluation framework.

Built through 9 debugging iterations — each one exposing a real production problem
and requiring a principled engineering fix.

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/YOUR_USERNAME/langchain-dynamic-tool-authorization/blob/main/notebook.ipynb)

---

## Why This Matters

Modern AI systems in production require four things most demos skip:

| Requirement | What Breaks Without It | How This Project Handles It |
|---|---|---|
| Controlled tool access | Users call APIs they shouldn't | Middleware Policy Enforcement Point |
| Reliable execution | Infinite loops, runaway API costs | Circuit breaker via `recursion_limit` |
| Provider-aware engineering | Silent failures on specific providers | Groq schema quirks documented + fixed |
| Measurable performance | No way to know if it works | 4-metric independent evaluation framework |

This project demonstrates all four in a single working system —
built by debugging real failures, not by following a tutorial.

---

## Sample Run

```
🔍 Testing: Unauthenticated user
  🔧 Tool called: public_search
  ✅ Tool     : public_search
  ✅ UX Clean : True
  💬 Response : The latest news includes updates on global events, politics,
                and current affairs...
  Latency     : 0.94s

🔍 Testing: Authenticated early conversation
  🔧 Tool called: private_search
  ✅ Tool     : private_search
  ✅ UX Clean : True
  💬 Response : I've retrieved your user profile from the database. Your
                profile contains your personal details, order history...
  Latency     : 1.19s

🔍 Testing: Authenticated later conversation
  🔧 Tool called: advanced_search
  ✅ Tool     : advanced_search
  ✅ UX Clean : True
  💬 Response : Based on the latest research and analysis, AI is expected
                to continue its rapid growth and advancement in 2025...
  Latency     : 0.87s

📊 FINAL RESULTS
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

Full terminal output: [`results/final_output.txt`](results/final_output.txt)

---

## Architecture

```
USER REQUEST
     │
     ▼
┌──────────────────────────────────────────────┐
│  MIDDLEWARE  (Infrastructure Layer)          │
│  middleware.py → state_based_tools()         │
│                                              │
│  Reads: auth state + message count           │
│  Wraps all tools with make_guarded_tool()    │
│   • Allowed  → execute normally              │
│   • Disallowed → return __ACCESS_DENIED__    │
│  Passes all 3 to Groq (avoids schema bug)    │
│  Post-call: logs any policy violations       │
│                                              │
│  KEY: tool names never change                │
│       agent registry never breaks           │
└─────────────────┬────────────────────────────┘
                  │
                  ▼
┌──────────────────────────────────────────────┐
│  MODEL  (Behavior Layer)                     │
│  agent.py → create_agent()                   │
│                                              │
│  Reads clean tool descriptions               │
│  Picks correct tool based on descriptions    │
│  Hard stop: recursion_limit = 6              │
│  Guided: system prompt rules 1-5             │
│  temperature=0.1 (Groq schema stability)     │
└─────────────────┬────────────────────────────┘
                  │
                  ▼
┌──────────────────────────────────────────────┐
│  UX LAYER  (Response Cleaner)                │
│  response_cleaner.py → clean_response()      │
│                                              │
│  Strips: [PUBLIC] [PRIVATE] [ADVANCED]       │
│  Strips: __ACCESS_DENIED__, tool name leaks  │
│  Safety net: catches what prompts miss       │
└──────────────────────────────────────────────┘
```

## Tool Access Policy

| User State | public_search | private_search | advanced_search |
|---|:---:|:---:|:---:|
| Unauthenticated | ✅ | ❌ | ❌ |
| Authenticated + < 5 messages | ✅ | ✅ | ❌ |
| Authenticated + 5+ messages | ✅ | ✅ | ✅ |

---

## What I Actually Solved — 9 Real Failures

Most GitHub projects show the working version.
This one documents every failure that led there.

**Failure 1 — Infinite Tool Loop**
Model called `public_search` 3 times with different queries, eventually crashing.
Fix: `recursion_limit` as hard circuit breaker in infrastructure config.
*Lesson: Never trust a model to self-stop. Infrastructure enforces hard limits.*

**Failure 2 — Groq Schema Rejection**
`@tool` decorator generated schemas Groq's API rejected on first call.
Fix: `StructuredTool` + explicit Pydantic `args_schema`.
*Lesson: Validate tool schemas against your actual provider, not just locally.*

**Failure 3 — RLHF Safety Override**
Model refused to call `private_search` despite system prompt permission.
"private account details" activated safety training regardless of instructions.
Fix: Neutral vocabulary — "user database", "profile lookup", "record retrieval".
*Lesson: Model safety training fires on vocabulary, not intent.*

**Failure 4 — Groq 2-Tool Combo Schema Bug**
Exactly `[public_search, private_search]` together caused `BadRequestError`.
Single tool or all 3 worked fine. Provider-level serialization quirk.
Fix: Always pass all 3 tools; use guarded functions for access control.
*Lesson: Isolate provider bugs. Workaround at infrastructure, not business logic.*

**Failure 5 — Wrong Tool Selected**
"Do deep research" → model chose `public_search` despite `advanced_search` being available.
Fix: Added "ONLY tool for trend analysis" exclusivity signal to description.
*Lesson: Tool descriptions are routing logic. Write them as rules, not hints.*

**Failure 6 — Recursion Limit Too Tight**
`recursion_limit=4` caused `GraphRecursionError` on correct behavior.
Fix: Raised to 6. Formula: `(max_tool_calls × 2) + 1` counts graph steps.
*Lesson: Understand what your limits are actually measuring.*

**Failure 7 — Symptom Masking**
RLHF refusal was hiding the Groq schema bug. Same failing test, different root causes.
Fixing the first revealed the second.
*Lesson: In layered systems, one bug masks another. Diagnose layer by layer.*

**Failure 8 — Marker Leaks Into User Response**
`[LOCKED]` text in description appeared in model's final user-facing answer.
Fix: `make_guarded_tool()` + `clean_response()` post-processor.
*Lesson: Defense in depth. One protection layer always misses something.*

**Failure 9 — Middleware Rename Breaks Agent Registry**
Renaming tools to `LOCKED_private_search` caused `ValueError` on all tests.
LangChain builds `{name: fn}` registry at creation time. Renamed tools not found.
Fix: Keep names identical. Permission check wraps the function, not the name.
*Lesson: Open/Closed Principle: enforce policy inside the contract, never by breaking the interface.*

Full engineering log: [`docs/iteration_log.md`](docs/iteration_log.md)

---

## Project Structure

```
langchain-dynamic-tool-authorization/
│
├── README.md
├── requirements.txt
├── notebook.ipynb              ← full Colab notebook (runnable)
├── main.py                     ← single entry point
│
├── agent/
│   ├── tools.py                ← StructuredTool definitions + SearchInput schema
│   ├── middleware.py           ← state_based_tools + make_guarded_tool
│   ├── agent.py                ← create_agent with LLM config + system prompt
│   └── response_cleaner.py    ← clean_response + UX leak detection
│
├── evaluation/
│   ├── test_cases.py           ← 3 test scenarios with design rationale
│   └── evaluator.py           ← 4-metric evaluation framework
│
├── docs/
│   ├── architecture.md         ← system design with diagrams
│   ├── engineering_decisions.md← 12 production principles with context
│   └── iteration_log.md        ← all 9 failures documented
│
└── results/
    └── final_output.txt        ← terminal output at 100/100/100/100
```

---

## Run It Yourself

**Option 1 — Google Colab (no setup, recommended)**

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/YOUR_USERNAME/langchain-dynamic-tool-authorization/blob/main/notebook.ipynb)

Click → add your Groq API key in the first cell → Run All → see 100/100/100/100.

**Option 2 — Local**

```bash
git clone https://github.com/YOUR_USERNAME/langchain-dynamic-tool-authorization
cd langchain-dynamic-tool-authorization
pip install -r requirements.txt
export GROQ_API_KEY=your_key_here
python main.py
```

Groq API key: free tier at [console.groq.com](https://console.groq.com)

---

## Skills Demonstrated

| Skill | Where |
|---|---|
| LangChain Agents | `create_agent` with full middleware stack |
| Access Control | Policy Enforcement Point in `middleware.py` |
| Prompt Engineering | RLHF vocabulary bypass, description-as-router |
| Provider Debugging | Groq schema quirks, temperature bug, combo rejection |
| Defense in Depth | 4-layer UX protection stack |
| Evaluation Design | 4 independent metrics, stream-based inspection |
| Production Patterns | Circuit breaker, audit logging, Open/Closed Principle |
| Iterative Debugging | 9 documented failures with root cause analysis |

---

## Requirements

```
langchain
langchain-groq
langgraph
deepagents
pydantic
```
