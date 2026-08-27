# Engineering Principles

These principles apply to product code, prompts, configuration, infrastructure, and operational procedures. Exceptions require explicit rationale and, when architectural, an ADR.

1. **Simple before clever.** Use the smallest design that satisfies known reliability and safety needs.
2. **Explicit before implicit.** Represent identity, state, transitions, authority, versions, and failure directly.
3. **Typed boundaries.** Commands, events, model decisions, tool requests/results, and stored records use versioned schemas.
4. **Structured outputs.** Free-form text is an artifact, not a control-plane contract.
5. **Validate all model output.** Parse, schema-check, semantically validate, authorize, and bound it outside the model.
6. **Agents do not receive unrestricted credentials.** A brokered Tool Runtime resolves narrow capabilities at execution time.
7. **Deterministic logic stays deterministic.** Do not add model variance where rules, code, or a workflow state machine suffice.
8. **Every execution is traceable.** Correlate definition versions, inputs/references, decisions, tools, state transitions, approvals, usage, and outcomes.
9. **Failure is a first-class state.** Classify errors, outcome certainty, retryability, and recovery paths; never silently drop work.
10. **Human approval is architecture, not UI decoration.** Bind authorization to an exact action and revalidate before execution.
11. **Model providers remain replaceable where practical.** Isolate provider semantics behind ports without pretending all models behave identically.
12. **Business logic does not live entirely inside prompts.** Put permissions, limits, routing invariants, calculations, and state transitions in testable code/configuration.
13. **Agent definitions are data-driven where practical.** Version and validate them; do not scatter identities and instructions through application code.
14. **Test behavior, not only implementation.** Assert domain invariants, policy outcomes, side effects, recovery, and evaluated output quality.
15. **Never claim successful external execution without evidence.** Require a receipt or reconciliation result; preserve `unknown` when outcome is ambiguous.
16. **Deny and minimize by default.** Access, data exposure, tools, network destinations, retries, and retention start narrow.
17. **Derived views are disposable.** Queues, caches, search indexes, analytics, and graphs can be rebuilt from canonical state.
18. **Version what changes behavior.** Agent, Skill, Tool, Workflow, Policy, evaluator, model configuration, and datasets must be identifiable in results.
19. **Design for cancellation and idempotency.** Long-running and external work must tolerate retries, process loss, and user intervention.
20. **Measure usefulness with safety and cost.** Throughput without correctness, policy compliance, and reduced supervision is not success.

## Review prompts

Before merging a runtime change, ask:

- Which state transition or invariant changes?
- What authority is required, and where is it enforced?
- Can retries duplicate a side effect or conceal an uncertain outcome?
- Which exact versions appear in traces and evaluations?
- Can regular tests run deterministically without external providers?
- What will an operator and user see when this fails?
