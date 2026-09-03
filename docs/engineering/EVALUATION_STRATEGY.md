# Agent Evaluation Strategy

## Unit test != agent evaluation

Stage 2 seeds `tests/fixtures/agent_eval/cases.json` (schema version 1) with
complete_context, missing_fact, conflicting_fact, irrelevant_context,
instruction_attack, and unsupported_completion. Tests simulate both valid and
invalid decisions with a scripted model. Exact supplied key/value/source matching
and required-gap rules are the first deterministic evaluator; summary rendering
does not accept arbitrary ungrounded prose.

These are behavioral regression fixtures, not live-model scores or held-out
research-quality evidence. Source truth, paraphrase entailment, nuanced comparison,
and prompt-injection robustness require future calibrated evaluation. The injection
fixture proves that source text cannot widen software action policy; it does not
prove a probabilistic model will always ignore adversarial text.

A unit test asks whether deterministic software obeys a specified contract—for example, whether a denied tool call remains unexecuted. An agent evaluation asks whether probabilistic behavior is useful and appropriate—for example, whether the agent chose the right evidence and tool. A passing evaluation cannot excuse a security invariant failure; a passing unit suite cannot establish answer quality.

## Evaluation dimensions

### Stage 4 retrieval and grounding baseline

`knowledge_cases.json` defines knowledge_required, knowledge_not_needed,
missing_knowledge, conflicting_knowledge, stale_knowledge_version,
unauthorized_knowledge_source, source_prompt_injection, query_injection,
fabricated_knowledge_reference, and tool_vs_knowledge. All are executed as scripted
regression cases, not merely stored descriptions. They measure deterministic scope,
provenance, lifecycle, bounded ranking, conflict-gap behavior, and evidence acceptance.

The lexical-overlap v1 baseline excludes no-overlap chunks and has stable tie-breaking
and source caps. It does not measure semantic recall, synonyms, or natural-language
query choice. `knowledge-facts-v1` accepts exact structured key/value/reference tuples
from the active same-run pack alongside existing supplied/tool facts. Returned
conflicting values produce gaps; omitted or unindexed conflicts are not detected.
Free-text candidates keep their references but do not certify paraphrases. No live
model, semantic judge, learned reranker, or held-out production relevance score is
claimed. Future hybrid retrieval and calibrated entailment require new evidence.

### Stage 3 tool-selection boundary

`tests/fixtures/agent_eval/tool_cases.json` adds tool_needed, tool_not_needed,
repeated_request, two_tools, injection, unauthorized_tool, wrong_tool_selection,
tool_failure_recovery, and fabricated_receipt. These are scripted regression cases,
not held-out model scores. The tool-enabled evaluator (`receipt-facts-v1`) matches
exact findings to supplied facts or successful same-run, same-workspace, granted-version
receipts. It preserves the required-key/gap rules and rejects fabricated citations.

“Was the tool allowed and its request valid?” is enforced deterministically.
“Was this a good, necessary, efficient tool choice?” remains a future behavioral
evaluation. An intentional second Action may repeat a read; only replay of the same
invocation is deduplicated. Budgets bound repetition but do not prove intelligent
selection. Tool receipts establish observed provenance, not real-world truth,
freshness, or semantic entailment. No live-model or live-tool evaluation was run.

| Dimension | Question | Candidate measure |
|---|---|---|
| Task success | Did the result satisfy acceptance criteria? | Exact/structured checks plus calibrated human rubric. |
| Factual grounding | Are material claims supported and faithful to sources? | Claim-level entailment/citation review and unsupported-claim rate. |
| Correct tool choice | Was an eligible, useful tool selected? | Expected/allowed tool set, action sequence, and contribution review. |
| Argument correctness | Were tool inputs and destinations correct? | Schema plus semantic comparison to fixture truth. |
| Instruction adherence | Did behavior follow the versioned role/task constraints? | Rubric and prohibited-behavior detectors. |
| Policy compliance | Did proposals and actions remain inside authority? | Deterministic policy reconciliation; zero tolerance for execution bypass. |
| Tool efficiency | Were calls necessary and non-duplicative? | Unnecessary, repeated, and failed-call rates. |
| Hallucination | Did output invent facts, actions, receipts, or certainty? | Unsupported claim/action-success and false-certainty rates. |
| Delegation quality | Were Tasks clear, correctly routed, and minimally coupled? | Plan/task rubric, rework, cyclic handoff and completion measures. |
| Failure recovery | Did the agent adapt safely to recoverable failures? | Scenario completion without unsafe retry or lost evidence. |
| Escalation correctness | Did it escalate when blocked/risky and avoid unnecessary escalation? | Precision/recall over labeled scenarios. |
| Latency and cost | Is quality achieved within usable bounds? | Wall/active time, model/tool calls, tokens and estimated cost per accepted result. |

## Evaluation layers

1. **Deterministic fixtures first:** state, tool selection, arguments, policy, trace, and known-answer assertions using scripted models.
2. **Offline model evaluations:** versioned datasets with pinned configuration; compare candidates and prompt/runtime changes.
3. **Adversarial evaluations:** injection, conflicting evidence, stale memory, inaccessible sources, tool deception, ambiguous outcomes, and budget pressure.
4. **Human calibration:** domain reviewers label difficult cases and periodically verify automated evaluator agreement.
5. **Online sampled evaluations:** privacy-aware evaluation of selected production outcomes after the system is safe to deploy.

## Evaluation case schema

Each case records dataset/case version, Goal/Task, workspace policy fixture, available agent/skill/tool versions, sources and expected provenance, injected failures, expected/allowed decisions, acceptance criteria, prohibited actions, budget, and evaluator versions. Results identify model/provider configuration and runtime commit/version.

## Evaluator types and cautions

- Code/constraint evaluators are preferred for exact fields, policy, tool arguments, citations, costs, and state.
- Reference-based text metrics can assist but rarely establish business correctness alone.
- Model judges are useful for nuanced rubrics only after calibration against humans; they require pinned prompts/configuration, bias checks, and confidence handling.
- Human review is reserved for ambiguous, high-impact, or calibration cases and must use concise rubrics.
- Composite scores must retain component results; a high style score cannot hide a policy violation.

## Dataset governance

Maintain separate development, regression, adversarial, and holdout sets. Version sources and expected outputs, document coverage and limitations, prevent sensitive production data from entering fixtures without approval, and monitor contamination from tuning. Add every safely reproducible material incident as a regression case.

## Release gates

- Zero executed policy/approval bypass, cross-workspace leakage, fabricated action receipt, or duplicate side effect in the relevant suite.
- No statistically/materially significant regression on critical slices versus the currently approved version.
- Success, grounding, intervention, cost, and latency meet workflow-specific thresholds in [Success Metrics](../product/SUCCESS_METRICS.md).
- Failures include trace evidence sufficient for diagnosis.
- Any override is explicit, time-bounded, owned, and does not waive security invariants.

## Cost strategy

Run deterministic fixtures on every change; small representative offline evals on runtime/prompt/model changes; broader and adversarial suites on schedule/release. Cache only immutable provider responses when licensing/privacy permit and label cached results. Enforce per-run and aggregate budgets.
