# Risk Register

Scale: Probability and impact are qualitative Stage 0 estimates (`Low`, `Medium`, `High`). Status is `Open`, `Monitoring`, or `Mitigating`. Owner identifies the accountable system layer or product function until named individuals exist.

| Risk ID | Risk | Probability | Impact | Mitigation | Detection | Owner / layer | Status |
|---|---|---|---|---|---|---|---|
| R-001 | Hallucinated facts or action-success claims | High | High | Provenance, structured receipts, claim checks, uncertainty/escalation | Grounding evals; unsupported claims; receipt reconciliation | Runtime / Evaluation | Mitigating |
| R-002 | Infinite or non-progressing agent loops | Medium | High | Iteration/time/cost limits, repeated-decision and cycle detection | Limit events, repeated action signatures, queue age | Agent Runtime | Mitigating |
| R-003 | Runaway model/tool cost | Medium | High | Per-execution/workspace budgets, estimates, hard caps, rate limits | Cost/usage alerts and budget-denial events | Runtime / Operations | Mitigating |
| R-004 | Tool misuse or wrong arguments/destination | High | High | Least privilege, typed/semantic validation, risk classes, approval | Tool evals, denial/approval audits, anomaly review | Tool Runtime / Policy | Mitigating |
| R-005 | Direct or indirect prompt injection | High | High | Trust separation, minimal tools/context, external validation, sandbox/approval | Adversarial evals, suspicious-content flags, action anomalies | Security / Context | Mitigating |
| R-006 | Knowledge poisoning or compromised source | Medium | High | Source ownership/provenance, quarantine, freshness/version, conflict handling | Source changes, retrieval evals, user reports | Knowledge | Open |
| R-007 | Permission or policy implementation failure | Medium | Critical | Deny by default, central decisions at each boundary, conformance tests | Policy reconciliation, unauthorized-attempt alerting | Policy / Security | Mitigating |
| R-008 | Cross-workspace data leakage | Low | Critical | Scoped records/jobs/indexes/caches, DB/data enforcement, adversarial tests | Isolation suite, audit anomalies, canary tenants | Data / Security | Mitigating |
| R-009 | Duplicated external actions on retry | Medium | High | Idempotency keys, receipts, atomic attempt records, reconcile unknowns | Duplicate-effect fixtures, provider reconciliation | Tool Runtime / Execution | Mitigating |
| R-010 | Model, tool, or API outage | High | Medium | Timeouts, classified capped retries, circuit breaking, pause/escalate, adapters | Dependency SLOs, error/latency alerts | Execution Infrastructure | Open |
| R-011 | Stale or contradictory memory | Medium | High | Provenance, scope, expiry/supersession, authoritative-source precedence | Memory age/conflict evals and correction rate | Memory | Open |
| R-012 | Context overflow or omission of critical evidence | High | Medium | Explicit budgets, prioritization, provenance-preserving summaries, escalation | Truncation metrics, missing-evidence evals | Context / Runtime | Open |
| R-013 | Poor delegation or cyclic handoffs | Medium | Medium | Typed tasks/acceptance criteria, eligibility rules, handoff limits/cycle checks | Rework, handoff depth/cycles, delegation evals | Orchestration | Open |
| R-014 | Hidden, stuck, or falsely successful execution | Medium | High | Explicit terminal/wait states, leases, heartbeats, receipts, reconciliation | Stale execution alerts, state/receipt audits | State / Observability | Mitigating |
| R-015 | Over-engineering before workflow validation | High | Medium | Staged roadmap, modular monolith default, decision triggers, scope gate | Stage review, unused abstractions/services | Engineering | Mitigating |
| R-016 | Unnecessary agentification | High | Medium | Deterministic-first review, baseline workflow comparison | Tool/model calls and variance without quality gain | Product / Architecture | Mitigating |
| R-017 | Secret leakage to model, logs, or tools | Medium | Critical | Secret broker, redaction/allowlists, scoped tokens, no raw credentials in context | Canary-secret tests, secret scans, audit alerts | Security / Tool Runtime | Mitigating |
| R-018 | Approval confusion, fatigue, replay, or rubber-stamping | Medium | High | Risk-based approvals, exact payload binding, expiry, clear effects, batch limits | Edit/reject rates, approval time/anomalies, replay tests | Product / Policy | Open |
| R-019 | Evaluation blind spots or evaluator gaming | High | High | Multiple metrics, holdouts, human calibration, adversarial/incident cases | Evaluator disagreement, production incidents, slice analysis | Evaluation | Open |
| R-020 | Framework/provider lock-in | Medium | Medium | Typed ports, normalized contracts, targeted compatibility prototypes | Adapter-specific leakage and migration test failures | Architecture | Monitoring |
| R-021 | Data retention/privacy non-compliance | Medium | High | Classification, minimization, per-category retention/deletion, audit | Deletion verification, retention scans, access reviews | Data / Security | Open |
| R-022 | Unsafe code/file/browser execution | Medium | Critical | Out of MVP, deny by default, future sandbox/egress/file policies | Capability inventory, sandbox escape tests, policy audit | Security / Tool Runtime | Open |
| R-023 | Race between cancellation/revocation and action | Medium | High | Recheck immediately before effect, leases, transactional state, narrow tokens | Race/fault tests, post-revocation call audit | Policy / Execution | Open |
| R-024 | Initial product fails to save supervision time | Medium | High | Narrow workflow, manual baseline, measure active human effort, usability study | Intervention/rework time and retention interviews | Product | Open |

## Review cadence

Review at every stage gate and after a material incident, new tool risk class, autonomy increase, data category, or deployment change. Owners must turn high/critical open risks into testable controls before the relevant capability ships.
