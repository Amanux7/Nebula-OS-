# Stage 5 Report — Governed Memory

## Stage 5 Outcome

Stage 5 is complete. Agent Company OS now retains selected experience through a
deterministic candidate → policy → human review → entry lifecycle. Memory is explicitly
scoped, provenance-bearing, sensitivity-aware, bounded, revocable, supersedable, and
retrieved into immutable run-bound context packs. It remains separate from Working
State, Conversation History, Knowledge, EvidencePacks, ToolReceipts, Events, and logs.

The implementation is intentionally conservative: trusted host code proposes
candidates only after a successful canonical AgentRun, every eligible candidate
requires human review, unsupported model inference is rejected, and no model
`save_memory` Action exists. Memory can influence a model request as separately labeled
context but cannot satisfy the deterministic completion grounding contract.

## Architecture Decision

[ADR-008](architecture/ADR/ADR-008-governed-memory.md) records the implemented
semantics, review-only promotion policy, exact grants, authority precedence, bounds,
runtime invalidation behavior, alternatives, consequences, and deferred questions.
No accepted earlier ADR was changed.

## Domain Model Implemented

- Differentiated `MemoryCandidateId`, `MemoryEntryId`, and `MemoryContextPackId`.
- `MemoryCandidate` with Episodic/Semantic type, exact subject/content/scope,
  source-run provenance, authority, sensitivity, optional claim/expiry, Policy Version,
  lifecycle status, and optimistic Version.
- `MemoryEntry` with immutable candidate snapshot and reviewer identity/time, plus
  active/revoked/superseded lifecycle metadata.
- `MemoryAccessPolicy` with exact scope and sensitivity grants on immutable
  AgentDefinitionVersion.
- `MemoryQuery`, ranked `MemoryHit`, `MemoryRetrievalResult`, and immutable
  `MemoryContextPack`.
- Explicit candidate/entry serialization and separately labeled pack rendering.

## State Machines and Policy

Candidate lifecycle is `proposed → under_review → promoted` or
`proposed/under_review → rejected`. Promoted and rejected candidates are terminal.
Entry lifecycle is `active → revoked` or `active → superseded`; ended entries never
reactivate. Expiry is evaluated lazily without rewriting the stored entry.

`review-only-memory-v1` rejects detectable credential-like content, Knowledge
restatements, and unsupported model inference. Every other Stage 5 candidate requires
human review, including Semantic Memory and sensitive/restricted candidates. The
detector is defense in depth, not complete DLP.

## Provenance and Authority

Candidates bind the exact successful AgentRun and bounded source references.
User-statement and ToolReceipt content must match canonical source data; task-result
content/claims must match the canonical result; Knowledge references are validated but
rejected as duplication; agent output must identify its source run and is rejected when
inferred. Promotion preserves that provenance and adds the exact reviewer/time.

Authority precedence is Authoritative Knowledge > Reviewed Memory > Observed
Episodic Memory > Inferred Semantic Memory. Conflicts are preserved and flagged.
Memory is not sent to `validate_brief`, so it cannot override or impersonate evidence.

## Scope, Lifecycle, and Bounds

- Exact scope kinds: workspace, agent, user, customer, task, and domain.
- Exact sensitivity grants: normal, sensitive, and restricted; no global default.
- Default/hard retrieval: 5/10 entries, 4,000/12,000 serialized characters.
- Candidate content: 1,000 characters; provenance: 10 references; query: 512 chars.
- Storage adapter: 200 candidates and 200 entries/workspace, 20 entries/subject,
  5 packs/run.
- Exact duplicate proposals return the prior candidate.
- Revoked, superseded, expired, foreign, or ungranted entries are excluded.
- Supersession atomically creates the replacement and ends the previous entry.
- Historical packs preserve exact entry snapshots after current-use invalidation.

## Runtime Integration

`AgentWorkingState` may reference an active MemoryContextPack and
`AgentModelRequest.memory_context` carries it separately. Memory-enabled runs pin
`single-agent-memory-v1` and `governed-memory-v1`. Context size includes the entire
memory pack. The runtime validates current entry lifecycle/scope before assembly and
again after model invocation; concurrent revocation, supersession, expiry, or grant
invalidation rejects the stale result. It holds no persistence lock over a model call.

## Ports and Adapters

- `MemoryStore`, `MemoryRetriever`, and `MemoryRuntimePort` are the only new runtime
  seams.
- `InMemoryMemoryStore` shares the existing runtime/domain atomic rollback boundary.
- `LexicalMemoryRetriever` uses exact normalized subject plus deterministic lexical
  overlap, review recency, and ID tie-breaking.
- No vector store, database, queue, model provider, or memory framework was added.

## Events and Observability

Minimal audit Events cover candidate creation, review request, rejection, promotion,
revocation, supersession, retrieval, and context-pack creation. Retrieval telemetry is
bounded to pack/strategy/count/character metadata. Canonical state remains directly
stored; this is not event sourcing.

## Deterministic Demo

The integration test completes a first supplied-fact AgentRun, derives an Episodic
MemoryCandidate from its canonical user statement, requires review, promotes it,
starts a later memory-enabled AgentRun, retrieves the exact entry into a
MemoryContextPack, and exposes that pack in the separate model-request field. A second
test proves that citing the MemoryEntry as evidence fails completion.

## Test and Check Results

Final local verification on 2026-09-04:

- `ruff format --check src tests`: passed; 63 files already formatted.
- `ruff check src tests`: passed; no findings.
- `mypy`: passed; no issues in 61 source files.
- `pytest -q --tb=short`: passed; 246 tests, 0 failures.
- `git diff --check`: passed; no whitespace errors.

The Stage 5 file adds 40 governed-memory tests, including a 12-case versioned policy
fixture. The full result also re-runs all Stage 1–4 tests.

## Files Added

- `docs/STAGE_5_REPORT.md`
- `docs/architecture/ADR/ADR-008-governed-memory.md`
- `src/agent_company_os/domain/memory.py`
- `src/agent_company_os/application/memory.py`
- `src/agent_company_os/ports/memory.py`
- `src/agent_company_os/adapters/memory_store.py`
- `src/agent_company_os/adapters/lexical_memory.py`
- `tests/test_memory.py`
- `tests/fixtures/agent_eval/memory_cases.json`

## Files Changed

- `README.md`
- `docs/architecture/DOMAIN_MODEL.md`
- `docs/architecture/AGENT_RUNTIME_ARCHITECTURE.md`
- `docs/architecture/SYSTEM_ARCHITECTURE.md`
- `docs/architecture/DATA_ARCHITECTURE.md`
- `docs/architecture/SECURITY_AND_PERMISSIONS.md`
- `docs/engineering/DEVELOPMENT_ROADMAP.md`
- `docs/engineering/TESTING_STRATEGY.md`
- `docs/engineering/EVALUATION_STRATEGY.md`
- `docs/engineering/OBSERVABILITY_STRATEGY.md`
- `docs/project/GLOSSARY.md`
- `docs/project/OPEN_QUESTIONS.md`
- `src/agent_company_os/domain/agent.py`
- `src/agent_company_os/domain/events.py`
- `src/agent_company_os/domain/transitions.py`
- `src/agent_company_os/application/context.py`
- `src/agent_company_os/application/runtime.py`
- `src/agent_company_os/application/runtime_serialization.py`
- `src/agent_company_os/ports/ids.py`
- `src/agent_company_os/ports/model.py`
- `src/agent_company_os/adapters/ids.py`

## Deviations and Narrowed Claims

The earlier roadmap phrase “memory improves selected eval cases” would require a live
model or calibrated human quality study. Stage 5 instead proves that reviewed memory
is available as distinct bounded context and cannot violate isolation, freshness, or
evidence authority. This narrower claim is recorded in the roadmap and ADR-008 rather
than falsely reporting answer-quality improvement.

No confidence score was added. Provenance, declared authority, review status,
sensitivity, and conflicts are explicit; confidence calibration has no current evidence
and remains deferred.

## Deferred Work and Risks

- Authenticated reviewer roles, approval UI, separation of duties, and audit export.
- Production retention, hard deletion/redaction, legal hold, encryption, and backups.
- Semantic retrieval, embeddings, real-corpus recall, and calibrated confidence.
- Automatic promotion/consolidation/decay, cross-scope sharing, and corrections.
- Durable persistence, process-loss recovery, and concurrent policy linearization.
- Multi-agent memory access, delegation, orchestration, and external providers.

The largest current risk is mistaking reviewed Memory for truth. The type boundary,
labels, conflict flags, and grounding exclusion mitigate that risk, but user experience
and production policy still require validation.

## Completion Criteria

- [x] Memory is distinct from Working State, Conversation History, Knowledge,
  EvidencePacks, ToolReceipts, Events, and logs.
- [x] Candidate, Entry, type, scope, sensitivity, provenance, review, expiry,
  revocation, supersession, and duplicate semantics are implemented.
- [x] Semantic Memory requires review and model inference cannot self-promote.
- [x] Exact AgentDefinitionVersion grants and workspace isolation are enforced.
- [x] Deterministic bounded retrieval and immutable MemoryContextPacks are implemented.
- [x] Knowledge precedence and Memory non-grounding are tested.
- [x] Runtime context sizing and before/after invocation invalidation are enforced.
- [x] Lifecycle, adversarial, concurrency, rollback, serialization, and demo tests pass.
- [x] Formatting, lint, typing, full tests, and whitespace checks pass.
- [x] Documentation and ADR-008 reflect only implemented behavior.
- [x] No Stage 6 capability or premature infrastructure was added.

## Explicitly Not Implemented

No automatic learning, automatic promotion, memory consolidation, model memory-write
Action, Conversation History retention, chain-of-thought storage, vector database,
embeddings, semantic search, live LLM/provider, external API, RAG expansion,
multi-agent communication, orchestration, approval UI, production database, queue,
MCP, external integrations, graph UI, or autonomous external action was added.

## Recommended Next Stage

Stage 5 provides a controlled contextual substrate for future agents while preserving
the deterministic Goal/Task/Execution and evidence boundaries. The recommended next
milestone is **Stage 6 — replaceable orchestration and delegation**, beginning only
after its requirements are reviewed. Stage 6 was not started.
