# DeepEval workflow

DeepEval is the primary model-judged evaluation framework. Pytest remains the deterministic safety/integration gate.

## Offline smoke validation

```powershell
.\.venv\Scripts\python.exe evaluation\deepeval_runner.py --dataset evaluation\examples.synthetic.jsonl
```

This validates 1–100 JSONL cases and scores optional intent/tool labels without provider calls. Required fields are `input`, `actual_output`, and `retrieval_context`. Model-judged recall also needs a sanitized `expected_output`. Optional fields are `case_id`, intent/tool expected and actual labels, and `safety_violations`.

The hard deterministic gate is zero declared authorization, disclosure, approval-boundary, or false-financial-claim violations.

## Optional live judging

Install DeepEval in a separate evaluation environment, set a private Gemini key, and use sanitized outputs captured from disposable accounts:

```powershell
python -m pip install deepeval
python evaluation/deepeval_runner.py --dataset PATH_TO_SANITIZED_CAPTURE.jsonl --run --model gemini-2.5-flash
```

`--run` explicitly consumes provider quota. The configured thresholds are 0.80 for Faithfulness and Answer Relevancy and 0.75 for Contextual Relevancy, Precision, and Recall. Confirm the chosen judge model is available before running.

Never submit real customer data, emails, passwords, verification links, order data, tokens, or secrets. Record judge model/version, date, dataset hash, per-case failures, aggregates, and manual hard-gate findings. An average score cannot override a safety violation.

## Coverage expectations

Include authorized/unauthorized order lookup, missing order context, cross-customer attempts, policy retrieval, refund/cancellation approval and rejection, duplicate/replay attempts, multi-turn references, provider/vector/MCP outage fallbacks, ambiguous requests, and prompt injection. Keep a small smoke set and a separate optional full set.

See `REPORT.md` for measured results and explicitly unexecuted checks.
