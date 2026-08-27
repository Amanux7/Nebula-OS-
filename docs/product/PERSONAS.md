# Personas

These are testable role hypotheses, not fictional demographics. Selecting the first commercial segment remains open.

## 1. Owner-operator

- **Responsibilities:** sales, delivery, administration, and prioritization in a small business.
- **Problems:** important work is fragmented; repetitive research and reporting consume attention; automation setup is too technical.
- **Technical sophistication:** low to moderate.
- **Desired outcomes:** delegate bounded back-office work, receive concise outputs, and know when intervention is needed.
- **Trust concerns:** incorrect customer-facing actions, hidden costs, leakage of business data, and inability to undo changes.
- **Autonomy comfort:** Levels 1–2 initially; Level 3 for proven, reversible tasks with limits.

## 2. Operations lead

- **Responsibilities:** process quality, throughput, compliance, handoffs, and incident resolution.
- **Problems:** work crosses systems and teams; process status is opaque; failures surface late.
- **Technical sophistication:** moderate; understands workflows and metrics but may not write code.
- **Desired outcomes:** encode repeatable workflows, maintain approvals and ownership, measure reliability, and inspect exceptions.
- **Trust concerns:** duplicate actions, weak audit trails, policy bypass, stale information, and ambiguous accountability.
- **Autonomy comfort:** Level 2 by default; Level 3 inside explicit scopes, budgets, and service objectives.

## 3. AI automation builder

- **Responsibilities:** design, integrate, test, and maintain AI-enabled business processes.
- **Problems:** prompts become unversioned business logic; agent frameworks obscure state; integrations and evaluations are difficult to reuse.
- **Technical sophistication:** high.
- **Desired outcomes:** typed contracts, provider adapters, deterministic tests, versioned agent/skill/tool definitions, and useful traces.
- **Trust concerns:** framework lock-in, nondeterministic regressions, credential exposure, and irreproducible executions.
- **Autonomy comfort:** comfortable configuring Levels 0–3; expects policy to constrain Level 4.

## 4. Team or agency manager

- **Responsibilities:** coordinate specialists, maintain quality, deliver client work, and protect account boundaries.
- **Problems:** repeated context transfer, inconsistent output, unclear delegation, and difficult client review.
- **Technical sophistication:** moderate.
- **Desired outcomes:** reusable operating playbooks, role-specific agents, approval-ready deliverables, and workspace/client isolation.
- **Trust concerns:** cross-client leakage, brand inconsistency, unsupported claims, and unclear provenance.
- **Autonomy comfort:** Levels 1–2 for external deliverables; Level 3 for internal read-only preparation.

## Cross-persona design implications

- A useful default must be safe without requiring policy expertise.
- Advanced configuration should be inspectable but not required for basic use.
- Trust depends on evidence, scoped authority, predictable approvals, and clear failure states.
- The MVP should measure saved supervision time, not merely generated output.

See [User Journeys](USER_JOURNEYS.md) and [Success Metrics](SUCCESS_METRICS.md).
