# Success Metrics

Metrics are evaluated per versioned workflow and representative dataset. Raw execution count, prompt count, agent count, and generated words are not success measures.

## MVP outcome metrics

| Dimension | Metric | Initial target | Measurement |
|---|---|---:|---|
| Task completion | Accepted completion rate | ≥ 80% | Executions meeting acceptance criteria without manual rework beyond approval. |
| Correctness | Critical factual error rate | < 2% | Human-reviewed factual claims on the reference evaluation set. |
| Grounding | Supported material-claim rate | ≥ 95% | Material claims linked to a valid source that supports them. |
| Reliability | System-caused terminal failure rate | < 5% | Excludes deliberate policy denial and invalid user input. |
| Failure visibility | Diagnosable seeded failures | 100% | Reviewer can identify failing component/category from trace. |
| Human effort | Median active supervision time | ≥ 40% below manual baseline | Time spent configuring, correcting, and approving—not wall-clock runtime. |
| Approval safety | External writes executed without required approval | 0 | Policy/audit reconciliation. |
| Approval quality | Materially edited approved drafts | Establish baseline, then reduce | Measures useful readiness; must not incentivize careless approval. |
| Agent behavior | Unnecessary tool-call rate | < 10% | Tool calls that contribute no evidence or state change. |
| Recovery | Duplicate external effects during retries | 0 | Idempotency and receipt reconciliation tests. |
| Cost | Cost per accepted completion | Baseline in pilot; budget enforced 100% | Provider usage plus allocated tool costs. |
| Latency | Interactive status acknowledgement | p95 < 2 s | Goal accepted and execution ID returned; completion SLO is use-case-specific. |
| Trust | Users who can correctly explain/verify an outcome | ≥ 80% in usability study | Scenario-based study, not satisfaction alone. |

Targets are working hypotheses to revisit after the Stage 2 prototype establishes realistic baselines.

## Guardrail metrics

- Policy-denied actions that nevertheless reach a tool: **zero**.
- Cross-workspace access in automated isolation tests: **zero**.
- Secrets or credentials found in logs/traces: **zero**.
- Executions exceeding configured hard budget or iteration limit: **zero**.
- External success claims lacking a verifiable receipt: **zero**.
- Critical evaluation regressions promoted to production: **zero**.

## Operational indicators

Track completion time by step, retry rate and cause, tool availability, approval wait time, cancellation latency, escalation rate, token/model usage, evaluation distribution, stale-source usage, and artifact delivery failures. Segment by workflow, definition version, provider/model, tool version, and autonomy level.

## Interpretation rules

- Pair completion with correctness, policy compliance, cost, and supervision time.
- Treat rejection and escalation as potentially correct safety outcomes.
- Compare against a manual or simpler deterministic baseline.
- Do not combine unlike workflows into a single success score.
- Record metric definition and evaluation-set versions so trends are reproducible.
