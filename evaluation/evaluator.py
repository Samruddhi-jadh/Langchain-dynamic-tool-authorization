"""
evaluator.py
------------
4-metric evaluation framework for the dynamic tool authorization agent.

Why stream() instead of invoke():
  agent.invoke() returns only the final response.
  agent.stream() exposes every intermediate step:
    - Which tools were considered
    - Which tool was called
    - What the tool returned
    - What the final response was
  As we cannot measure tool selection accuracy without seeing tool calls.
  Lesson: always stream in evals and debugging.

Why 4 separate metrics (not 1 combined score):
  Each metric catches a different class of failure:
    Tool Selection  → did model pick the right tool? (behavior layer)
    Block Enforce   → did infra stop disallowed tools? (infra layer)
    Loop-Free       → did model stop after one call? (circuit breaker)
    UX Quality      → is the user response clean? (UX layer)
  A combined score hides which layer failed.

Why loop detection matters:
  Model calling the same tool twice with different queries is a loop.
  recursion_limit catches it as infrastructure, but the evaluator
  records it separately so you can distinguish:
    - "hit recursion limit because of a loop" vs
    - "hit recursion limit because of correct multi-step reasoning"
"""

import time
from agent.response_cleaner import clean_response, check_ux_quality


def evaluate_dynamic_tooling(agent, test_cases: list) -> list:
    """
    Run all test cases and return detailed results with 4 metrics.

    Metrics measured per test:
      - tool_correct:        first tool called is in expected_allowed
      - no_blocked_violated: no tool in expected_blocked was called
      - loop_detected:       same tool called more than once
      - ux_clean:            final response contains no internal system language

    Args:
        agent:      Compiled LangGraph agent from build_agent()
        test_cases: List of test case dicts from test_cases.py

    Returns:
        List of result dicts, one per test case
    """
    results = []

    for case in test_cases:
        print(f"\n Testing: {case['name']}")
        start_time     = time.time()
        used_tools     = []
        loop_detected  = False
        final_response = ""

        try:
            for chunk in agent.stream(
                {"messages": case["state"]["messages"]},
                config={
                    "state": case["state"],
                    "recursion_limit": 6,
                },
                stream_mode="updates",
            ):
                for node_name, node_output in chunk.items():
                    if node_name == "model":
                        for msg in node_output.get("messages", []):
                            # ── Capture tool calls ────────────────────────
                            for tc in getattr(msg, "tool_calls", []):
                                name = tc["name"]
                                if name in used_tools:
                                    loop_detected = True
                                    print(f"  🔁 Loop detected: {name} called again")
                                else:
                                    used_tools.append(name)
                                    print(f"  🔧 Tool called: {name}")

                            # ── Capture final text response ───────────────
                            if hasattr(msg, "content") and msg.content:
                                final_response = msg.content

        except Exception as e:
            print(f"    Error: {type(e).__name__}: {str(e)[:100]}")

        # ── Compute metrics ───────────────────────────────────────────────────
        cleaned      = clean_response(final_response)
        latency      = time.time() - start_time
        first_tool   = used_tools[0] if used_tools else None
        tool_correct = first_tool in case["expected_allowed"] if first_tool else False
        blocked_used = [t for t in used_tools if t in case["expected_blocked"]]
        ux_clean, ux_violations = check_ux_quality(cleaned)

        result = {
            "test":                case["name"],
            "first_tool":          first_tool,
            "all_tools":           used_tools,
            "tool_correct":        tool_correct,
            "loop_detected":       loop_detected,
            "blocked_violated":    blocked_used,
            "no_blocked_violated": len(blocked_used) == 0,
            "ux_clean":            ux_clean,
            "ux_violations":       ux_violations,
            "final_response":      cleaned,
            "latency":             latency,
        }
        results.append(result)

        # ── Per-test output ───────────────────────────────────────────────────
        print(f"  {'✅' if tool_correct else '❌'} Tool     : {first_tool}")
        print(f"  {'✅' if ux_clean    else '❌'} UX Clean : {ux_clean}")
        if ux_violations:
            print(f"    UX Violations : {ux_violations}")
        print(f"   Response  : {cleaned[:120]}")
        print(f"  Blocked ❌  : {blocked_used or 'None'}")
        print(f"  Loop        : {'⚠️  YES' if loop_detected else 'No'}")
        print(f"  Latency     : {latency:.2f}s")

    # ── Summary ───────────────────────────────────────────────────────────────
    sel_acc   = sum(r["tool_correct"]        for r in results) / len(results)
    block_acc = sum(r["no_blocked_violated"] for r in results) / len(results)
    loop_acc  = sum(not r["loop_detected"]   for r in results) / len(results)
    ux_acc    = sum(r["ux_clean"]            for r in results) / len(results)

    print("\n📊 FINAL RESULTS")
    print(f"  Tool Selection Accuracy : {sel_acc:.2%}")
    print(f"  Block Enforcement       : {block_acc:.2%}")
    print(f"  Loop-Free Rate          : {loop_acc:.2%}")
    print(f"  UX Quality              : {ux_acc:.2%}")
    print(f"\n  {'Test':<40} {'Tool':<22} {'Routing':<10} {'UX'}")
    print(f"  {'-'*80}")
    for r in results:
        r_ok = "✅" if r["tool_correct"] else "❌"
        u_ok = "✅" if r["ux_clean"]    else "❌"
        print(f"  {r['test']:<40} {str(r['first_tool']):<22} {r_ok:<10} {u_ok}")

    return results
