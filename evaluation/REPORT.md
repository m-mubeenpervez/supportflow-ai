# Evaluation report

This report records reproducible, sanitized results only. Private deployment paths,
credentials, customer identities and message contents are intentionally omitted.

## Automated baseline

- Backend regression: 514 passed.
- Frontend regression: 20 passed.
- Production frontend build: passed.
- DeepEval deterministic smoke dataset: 3/3 fixtures valid; intent and tool labels
  3/3. No model-judged scores are claimed unless a live run is explicitly recorded.
- Docker configuration validation and secret checks: passed in the verified run.

## Security and workflow coverage

Tests cover JWT/session revocation, customer isolation, RBAC, first-admin bootstrap,
seven-policy routing, RAG storage/retrieval, MCP authorization, approval/rejection
gates, audit persistence, notification fan-out, email leases/retries/idempotency and
safe disabled-worker behavior. Human approval remains mandatory for sensitive actions;
no financial transfer is implemented.

## Email delivery status

Verification and notification workers run as independent Compose services and remain
disabled by default. Test-mode envelope allowlisting is fail-closed and validates all
recipients before SMTP. Controlled isolated fixture tests previously received owner
confirmation of two authorized inbox messages; this is not a claim of unrestricted
production delivery. No production SMTP activation is enabled.

## Database and release safety

The owner deployment and any recovery database are private operational concerns and
are not required by a clean clone. Fresh clones use their own Compose database,
credentials and first-Super-Admin bootstrap. Private dumps, archives, migration
overrides and `.env` files are excluded from Git. Historical recovery resources are
preserved outside the release snapshot.

## Limitations

Live Gemini judging, unrestricted SMTP, and authenticated browser journeys require
explicit credentials/fixtures and are not represented by invented scores. Review
queue counts before any approved delivery enablement. A release commit should be
verified again in a clean clone with independently generated secrets.
