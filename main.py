"""
main.py
-------
Single entry point. Builds the agent and runs the full evaluation.

Usage:
    export GROQ_API_KEY=your_key_here
    python main.py
"""

from agent.agent import build_agent
from evaluation.test_cases import TEST_CASES
from evaluation.evaluator import evaluate_dynamic_tooling


def main():
    print("=" * 60)
    print("  LangChain Dynamic Tool Authorization Agent")
    print("  Evaluation Framework — 4 Metrics")
    print("=" * 60)

    agent  = build_agent()
    results = evaluate_dynamic_tooling(agent, TEST_CASES)

    print("\n✅ Evaluation complete.")
    return results


if __name__ == "__main__":
    main()
