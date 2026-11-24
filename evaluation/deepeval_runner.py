"""Opt-in, Gemini-based DeepEval evaluation on sanitized captured outputs.

Default: validate dataset only. --run explicitly sends rows to Gemini judge.
Never pass real customer data or verification tokens.
"""
import argparse
import json
import os
from pathlib import Path


def load_cases(path):
    cases = []
    with Path(path).open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"Line {line_number}: expected JSON object")
            for key in ("input", "actual_output", "retrieval_context"):
                if key not in row:
                    raise ValueError(f"Line {line_number}: missing {key}")
            if not all(isinstance(row[key], str) for key in ("input", "actual_output")):
                raise ValueError(f"Line {line_number}: invalid text field")
            if not isinstance(row["retrieval_context"], list) or not all(
                isinstance(x, str) for x in row["retrieval_context"]
            ):
                raise ValueError(f"Line {line_number}: invalid retrieval_context")
            if not row["input"].strip() or not row["actual_output"].strip():
                raise ValueError(f"Line {line_number}: empty question or response")
            if "safety_violations" in row and not isinstance(
                row["safety_violations"], list
            ):
                raise ValueError(f"Line {line_number}: invalid safety_violations")
            cases.append(row)
    if not cases or len(cases) > 100:
        raise ValueError("Dataset must contain between 1 and 100 cases")
    return cases


def deterministic_summary(cases):
    """Score routing/tool labels and hard safety gates without an LLM."""
    summary = {"cases": len(cases), "safety_violations": 0}
    for field in ("intent", "tool"):
        eligible = [
            row for row in cases
            if f"expected_{field}" in row and f"actual_{field}" in row
        ]
        correct = sum(
            row[f"expected_{field}"] == row[f"actual_{field}"]
            for row in eligible
        )
        summary[f"{field}_cases"] = len(eligible)
        summary[f"{field}_accuracy"] = (
            correct / len(eligible) if eligible else None
        )
    summary["safety_violations"] = sum(
        len(row.get("safety_violations", [])) for row in cases
    )
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--run", action="store_true", help="Explicitly permit judge API calls")
    parser.add_argument("--model", default="gemini-2.5-flash")
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Limit live judge cases; use 2 for the ten-metric-call smoke run",
    )
    args = parser.parse_args()
    cases = load_cases(args.dataset)
    if args.limit is not None:
        if not 1 <= args.limit <= len(cases):
            parser.error("--limit must be between 1 and the dataset size")
        cases = cases[:args.limit]
    print("Cases validated:", len(cases))
    summary = deterministic_summary(cases)
    print("Deterministic fixture checks:", json.dumps(summary, sort_keys=True))
    if summary["safety_violations"]:
        print("HARD GATE FAILED: safety violations present")
        return 1
    if not args.run:
        print("DRY RUN. Gemini judge calls: 0")
        return 0
    if not os.environ.get("GEMINI_API_KEY"):
        raise RuntimeError("GEMINI_API_KEY required for explicit live evaluation")
    # Imported only with --run; framework is optional and isolated.
    from deepeval import evaluate
    from deepeval.models import GeminiModel
    from deepeval.metrics import (
        AnswerRelevancyMetric,
        ContextualPrecisionMetric,
        ContextualRecallMetric,
        ContextualRelevancyMetric,
        FaithfulnessMetric,
    )
    from deepeval.test_case import LLMTestCase

    # DeepEval 2.x names this constructor argument ``model_name``.
    model = GeminiModel(model_name=args.model, api_key=os.environ["GEMINI_API_KEY"])
    test_cases = [
        LLMTestCase(
            input=row["input"],
            actual_output=row["actual_output"],
            expected_output=row.get("expected_output"),
            retrieval_context=row["retrieval_context"],
        ) for row in cases
    ]
    metrics = [
        FaithfulnessMetric(threshold=0.8, model=model),
        AnswerRelevancyMetric(threshold=0.8, model=model),
        ContextualRelevancyMetric(threshold=0.75, model=model),
        ContextualPrecisionMetric(threshold=0.75, model=model),
        ContextualRecallMetric(threshold=0.75, model=model),
    ]
    evaluate(test_cases=test_cases, metrics=metrics)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
