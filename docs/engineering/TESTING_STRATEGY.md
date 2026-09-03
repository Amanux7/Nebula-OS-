# Testing Strategy

## Objectives

Stage 2 implementation evidence is in [Stage 2 report](../STAGE_2_REPORT.md).
Run `python -m ruff format --check src tests`, `python -m ruff check src tests`,
`python -m mypy`, and `python -m pytest -q` after installing `.[dev]`.
CI uses the same checks with no secrets or live-provider calls. Dependency setup
downloads packages; the test phase itself requires no network service.

`tests/test_runtime.py` exercises completion, bounded iterations/context, wait/resume,
grounding pressure, policy/schema rejection, provider and real async timeouts,
stale versions, cross-workspace references, duplicate drive/start, cancellation
races, immutable definition history, serialization, and multi-record rollback.
The scripted adapter is not evidence of probabilistic model quality.

Tests protect domain invariants, tenant isolation, safe side effects, recoverability, policy enforcement, and reproducible behavior. The regular suite must run without paid services or live model calls. Tests are layered by failure locality rather than a single end-to-end pyramid.

## Test layers

### Implemented Stage 4 tests

`tests/test_knowledge.py` adds 51 deterministic tests, backed by fictional sources in
`tests/fixtures/knowledge/` and versioned `agent_eval/knowledge_cases.json`. The suite
covers the requested A–T matrix: ingestion/chunking, exact source history, tenant/run
isolation, grants/trust, disablement, conflicts, empty results, deterministic ranking,
source/pack bounds, forged references, source/query injection, exact structured facts,
free-text limitations, context eviction, and atomic source/pack publication failures.
Additional checks cover stale commands, in-flight retrieval rejection, post-model
revocation, wait/resume, query budgets, adapter poisoning, direct-store validation,
and caller/tool provenance spoofing. Combined knowledge/tool evidence succeeds without
network calls. The same CI commands run 206 total tests with no new dependencies.
Exact local check results are in [Stage 4 report](../STAGE_4_REPORT.md); remote CI is
not asserted. In-memory rollback is not crash recovery or distributed atomicity.

### Implemented Stage 3 tests

`tests/test_tools.py` and `tests/fixtures/agent_eval/tool_cases.json` add deterministic
tool-use, no-tool-needed, repeated-read, two-tool, wrong-selection, unauthorized,
recovery, fabricated-provenance, and injection scenarios. They cover exact grants,
risk denials, strict argument/output validation (including Unicode/UTF-8 bytes),
normalized errors, actual async timeout, call budgets, replay and in-flight duplicate
ownership, parent/run/registry races, coroutine and domain cancellation, immutable
version history, receipt export/correlation, bounded previews, context overflow,
same-workspace foreign-run and cross-workspace evidence, and claim/result rollback.
Tests assert no executor call after preflight rejection and no Task completion from
a tool result alone. Failures can return to a valid waiting state.

The same existing CI commands include these tests without secrets, live APIs, new
dependencies, or infrastructure. [Stage 3 report](../STAGE_3_REPORT.md) records local
results; a remote CI run is not claimed. Timed async tests use generous outer guards;
fake clocks/IDs and gate-controlled concurrency keep business assertions deterministic.
Adapter cancellation cooperation and in-memory rollback do not prove crash recovery.

### Target test layers

| Layer | Scope | Representative assertions |
|---|---|---|
| Unit tests | Pure domain rules, parsers, transition functions, budget arithmetic | Illegal transitions rejected; permissions narrow; retry classifier correct. |
| Schema tests | Versioned commands/events/model/tool contracts | Valid fixtures round-trip; unknown/old versions handled; size/enum constraints enforced. |
| Contract tests | Ports and adapters, including provider/tool/secret/storage conformance | Every adapter maps errors and usage consistently and honors deadlines. |
| Integration tests | Real local persistence/queue/index combinations | Transactions, outbox delivery, concurrency, migrations, deletion propagation. |
| Agent Runtime tests | Loop driven by scripted Model Provider and clock | Decisions validate; limits, stalls, refusal, cancellation, and escalation reach correct states. |
| Tool tests | Fake/sandbox connectors through Tool Runtime | Authorization, schemas, idempotency, receipts, ambiguous outcomes, rate limits, redaction. |
| Workflow tests | Versioned deterministic/agentic step graphs | Dependencies, resume, partial failure, compensation, and cancellation propagation. |
| Policy tests | Decision tables and adversarial identities/resources/actions | Deny-by-default, workspace isolation, approval requirements, revocation and expiry. |
| Failure tests | Injected process/provider/storage/network failures | No hidden/lost work; bounded retries; recovery preserves exact state and avoids duplicates. |
| End-to-end tests | Narrow user outcomes through deployed test stack | Goal to artifact/approval/trace works; failure is diagnosable; external effects use sandboxes. |

## Deterministic test doubles

- **Scripted model:** returns decisions, malformed payloads, refusals, delays, usage, and provider errors by scenario key.
- **In-memory model:** applies simple deterministic rules for property/state tests; it is not presented as AI.
- **Tool fake:** records requests and simulates receipts, transient/permanent failures, timeouts, and outcome-unknown responses.
- **Clock and ID providers:** allow exact deadlines, expiry, retry, ordering, and trace assertions.
- **Policy evaluator:** loads explicit decision tables; production policy adapters pass the same conformance suite.
- **Knowledge/memory fixtures:** return provenance-bearing results with trust and access labels.

Golden traces may assert stable structured fields, but volatile timestamps/IDs and free-form text should be normalized. A snapshot is not a substitute for semantic assertions.

## Critical scenario matrix

Every runtime-affecting change should consider:

- happy completion, valid escalation, user cancellation, timeout, and budget exhaustion;
- malformed and semantically invalid model/tool output;
- prompt injection in knowledge and tool observations;
- authorization denial, required approval, expired/revoked approval, and changed payload;
- transient retry, permanent failure, ambiguous external outcome, and worker loss after side effect;
- duplicate/out-of-order event delivery and concurrent state updates;
- cross-workspace identifiers and data in caches, indexes, artifacts, jobs, and traces;
- context overflow, stale knowledge/memory, repeated decisions, and cyclic handoffs;
- telemetry/log redaction and trace completeness.

## Test environments and live providers

- Pull requests run lint/type/schema/unit/contract tests and fast integrations locally in CI.
- Merge/nightly suites run real infrastructure containers, concurrency, failure injection, and security cases.
- Optional scheduled/manual suites may call pinned live model/tool sandboxes with budgets and quarantined credentials.
- Live results are AI evaluations or compatibility signals, not required for the deterministic correctness gate unless a release policy explicitly says so.
- No test may perform a real consequential external action.

## Fixtures and data

Fixtures are synthetic or approved/de-identified, workspace-labeled, versioned, small enough to inspect, and include adversarial cases. Evaluation datasets are separated from developer tuning sets. Secrets are injected only into dedicated security/sandbox tests and never committed.

## Quality gates

Stage 1 will set language-specific coverage and mutation targets after tooling is chosen. Regardless of percentage, changes cannot merge with failing state-machine, tenant-isolation, approval-binding, idempotency, secret-redaction, or schema-compatibility tests. Flaky tests are defects: quarantine requires an owner, reason, and expiry.

## Testability requirements for design

All nondeterminism—model, time, IDs, network, scheduling, storage, and tool effects—must have controllable boundaries. Runtime behavior should be executable from fixtures without UI or provider access. Production incidents should yield minimized regression fixtures when sensitive data can be safely removed.

Software correctness tests are complemented, not replaced, by [Evaluation Strategy](EVALUATION_STRATEGY.md).
