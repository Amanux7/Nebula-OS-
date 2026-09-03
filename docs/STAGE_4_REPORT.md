# Stage 4 Report — Company Brain / Knowledge Retrieval

## Outcome

Stage 4 passed its deterministic offline completion gate on 2026-09-03. Company
Brain now supplies bounded, authorized, versioned knowledge to the existing Research
Brief Agent. It remains a modular Python application with scripted model/tool
adapters, not a deployed AI company or a production knowledge service.

AI for judgment. Software for guarantees.

## Stage 3 baseline and corrections

Before implementation: 155 tests passed in 2.73s; Ruff formatting reported 47 files
already formatted; lint passed; mypy reported no issues in 47 source files; git diff
--check passed. No blocking Stage 3 correction was needed. Existing tool/runtime
behavior remains covered by the full suite. The only extension to tool validation
rejects the new reserved knowledge: provenance namespace in returned source IDs.

## Company Brain boundary and implemented domain

Company Brain is source governance, ingestion, retrieval, and evidence access—not
a vector database, memory store, agent persona, or planning engine.

Implemented: KnowledgeSourceId, KnowledgeChunkId, EvidencePackId, KnowledgeSource,
KnowledgeSourceVersion, NormalizedContent, KnowledgeFact, KnowledgeChunk,
KnowledgeScope, KnowledgeQuery, EvidenceCandidate, RetrievalResult, EvidencePack,
SourceType, SourceStatus, TrustClass, and IngestionLimits. Existing Goal, Task,
TaskAttempt, Execution, Action, Observation, Event, and AgentRun meanings are unchanged.
No ExecutionStep or AgentInstance was introduced.

Sources are workspace-scoped, versioned, active/disabled, and trust-labelled.
Content Version is distinct from the optimistic source mutation Version. Version
snapshots preserve normalized content/hash, typed facts, metadata, timestamp,
schema/algorithm versions, and limits. Chunk IDs deterministically bind source,
workspace, version, ordinal, algorithm/configuration, and content hash.

## Ingestion and chunking

Plain text, Markdown, and strict structured-fact JSON are supported. Bytes are
bounded before strict UTF-8 decoding; line endings become LF; prohibited controls
and blank content are rejected. JSON uses exact fields, typed key/value facts,
duplicate-key rejection, and canonical content binding. No semantic rewriting,
web fetching, macros, document execution, or automatic fact extraction occurs.

Paragraph-aware character chunking splits long paragraphs at whitespace or hard
boundaries, trims chunk edges, uses no overlap, and preserves full normalized source
text separately. Structured facts remain typed and get one bounded chunk per fact.
Oversized facts fail instead of losing their grounding identity.

## Retrieval, ports, adapters, and limits

KnowledgeService exposes publish_source, publish_version, disable_source, retrieve,
and get_evidence_pack. Host code issues these commands explicitly. KnowledgeIngestor,
KnowledgeRetriever, KnowledgeStore, and KnowledgeRuntimePort are used boundaries,
alongside existing Clock/IdGenerator ports. Implementations are TextKnowledgeIngestor,
LexicalKnowledgeRetriever, InMemoryKnowledgeStore, and the service's runtime-facing
active_pack/evidence methods. No public HTTP/API server or UI was added.

Lexical-overlap v1 scores unique query term overlap, excludes zero-overlap chunks,
and sorts ties by source identity then ordinal. Grants/trust/status are applied before
ranking. Result validation rejects forged/altered or unpermitted adapter candidates.
Per-source caps and within-source deduplication limit repetition while retaining
distinct cross-source provenance. Empty/truncated results are structured, not invented
evidence. The baseline does not solve synonyms, semantic recall, or query choice.

Defaults: 32,768 source bytes, 16,000 normalized characters, 50 facts, 800 characters
per chunk, 64 chunks/version, 512 query characters, top 5 candidates, 2/source,
4,000 characters for the entire serialized pack, and 5 packs/run including empty
results. Pack bounds include metadata and query; the existing total runtime context
bound still applies. Corpus caps are 100 sources/workspace and 20 versions/source.
Hard maxima and all limit policies are in [ADR-007](architecture/ADR/ADR-007-company-brain-and-knowledge-retrieval.md).

## Permissions, source history, and EvidencePacks

KnowledgeScope on immutable AgentDefinitionVersion grants source IDs and trust classes.
Direct source grants protect the current invariants; KnowledgeCollection is deferred.
Query filters can narrow but not expand permissions. Published broader definitions
do not alter existing AgentRuns. New retrieval uses active/latest permitted versions;
historical packs retain exact captured versions and text rather than a latest alias.

Each immutable pack binds workspace/run, query/filter/limits, retrieval strategy and
version, timestamp, candidates, trust labels, source versions, chunk hashes, and
truncation. AgentWorkingState holds only the active pack ID. Pack history survives
replacement, wait/resume, terminal runs, and source disablement within the process.
It is not durable after process loss. Historical reads validate workspace and run.

Disablement prevents new retrieval and future use of active evidence; runtime checks
before and after model invocation reject completion after mid-call revocation. A
new source version alone does not retroactively invalidate an already captured pack.
An explicit new retrieval replaces its active reference. No hard deletion or re-enable
workflow exists; retention/redaction policy remains open.

## Provenance, grounding, and runtime integration

Knowledge references use percent-encoded source ID/version/chunk components under
the reserved knowledge: namespace. Supplied facts/source texts and tool output IDs
cannot impersonate it. Completion requires exact key/value/reference membership in
the active same-run authorized EvidencePack, not merely a plausible citation.
Fabricated sources, chunks, versions, values, foreign runs, and evicted-pack claims
are rejected. Conflicting returned values remain visible and become required-key gaps.

Free-text chunks are exposed with provenance and retained historically but do not
certify a paraphrase. Semantic entailment and conflicts outside the selected evidence
are not solved. No source trust label automatically makes a claim true.

Select ADR-007 Approach A: internal, host-initiated retrieval before model invocation
or after ordinary request_more_context/resume. The four existing Actions remain
unchanged; no model-requested retrieval action, tool wrapper, or planner was added.
KnowledgeRuntimePort keeps integration separate from ToolRuntimeService. ContextAssembler
has a dedicated knowledge_evidence field; it does not flatten knowledge into supplied
facts or tool Observations. Knowledge-enabled runs pin new protocol/policy/evaluator
versions while earlier definition versions retain Stage 2/3 behavior.

## Transactions, security, and observability

Source/version/chunks/publication audit commit atomically. EvidencePack, active run
reference/version, and query/pack audit share the runtime transaction rollback boundary.
Injected failure at publication audit, pack save, run save, and pack audit leaves no
partial state. Direct store guards also validate chunk lineage and pack authority/bounds.
Retrieval requires an idle active run, active parents, current Version, remaining
deadline, and remaining pack budget. There is no lock held across model/tool awaits.

Source/query injection fixtures demonstrate unchanged grants and rejection of denied
actions. Foreign/hidden source canaries never enter returned evidence. Text remains
untrusted even if the source is declared authoritative. Trusted in-process adapters
and host callers are not a hostile-code sandbox or production identity system.

Source publication/disablement and query execution/rejection/pack creation produce
Events. Metadata records workspace/run/execution/attempt/definition/pack correlation,
strategy/version, query length, candidate/returned counts, source versions/count,
duration, evidence characters, and truncation. No raw query/source body/exception
text is copied into Events. Historical packs intentionally retain their bounded
query/evidence, separately from telemetry. No secrets, network, or telemetry service
are required. serialize_pack and serialize_run export explicit evidence references.

## Tests and check results

Final code checks actually executed locally:

| Check | Result |
|---|---|
| python -m ruff format --check src tests | 57 files already formatted |
| python -m ruff check src tests | All checks passed! |
| python -m mypy | Success: no issues found in 55 source files |
| python -m pytest -q --tb=short | 206 passed in 3.52s; 0 failed |
| git diff --check | Passed, exit 0; only existing Git LF/CRLF conversion notices |

The 155 baseline cases remain passing; 51 knowledge cases were added. Existing CI
already discovers these tests and needs no workflow/dependency changes. Normal tests
are offline and secret-free; dependency installation still downloads development
packages. A remote CI run has not been claimed.

### Mandatory A–T scenario coverage

| Scenarios | Implemented checks |
|---|---|
| A, P | Publish/chunk/retrieve/pack and exact structured-fact Research Brief completion |
| B, O, R | v1/v2 history, latest new retrieval, model-visible updated version, eviction and audit retention |
| C, D, L | Foreign workspace source/chunk/version/pack access, ungranted source/trust filters, wrong-run packs |
| E | Disabled-source exclusion and post-model revocation |
| F, G | Both conflicting prices retained with a gap; structured empty no-result/wait behavior |
| H, I, J | Stable ranking, irrelevant exclusion, byte/character/fact/chunk limits, full pack/context bounds |
| K | Wrong source/version/chunk/value rejected; caller/tool namespaces cannot forge evidence |
| M, N | Source prompt injection cannot grant tools; query injection cannot expand sources or limits |
| Q | Free text/reference retained; unsupported paraphrase not accepted as exact fact evidence |
| S, T | Atomic source publication and pack/run/audit failure rollback |

Additional tests exercise stale commands, pending invocation rejection, total retrieval
budget, wait/resume, fixed definition scope, independent trust, malicious retriever,
missing adapter, direct-store guards, and combined knowledge/tool evidence.

## Fictional corpus and deterministic demo

The Aurora Desk fixtures contain product Markdown, pricing v1/v2, conflicting sales
facts, a refund policy, Paper Kite competitor facts, and an adversarial source. No
fixture asserts real company information. Ten evaluation scenarios are both declared
in knowledge_cases.json and executed, including tool_vs_knowledge and knowledge_not_needed.

The integration path is: create workspace/Goal/Task/Execution/TaskAttempt; publish
sources; publish a scoped Research Brief Agent version; start with insufficient
supplied facts; retrieve authorized evidence; invoke scripted model; optionally use
the independently granted fixture tool; validate exact knowledge/tool findings;
complete AgentRun/TaskAttempt/Task/eligible Execution. Goal satisfaction stays explicit.
Waiting for missing context, resuming, retrieving, and completing is also verified.

## Files added or changed

Added:

- docs/STAGE_4_REPORT.md
- docs/architecture/ADR/ADR-007-company-brain-and-knowledge-retrieval.md
- src/agent_company_os/domain/knowledge.py
- src/agent_company_os/domain/chunking.py
- src/agent_company_os/ports/knowledge.py
- src/agent_company_os/application/knowledge.py
- src/agent_company_os/adapters/knowledge_ingestion.py
- src/agent_company_os/adapters/knowledge_store.py
- src/agent_company_os/adapters/lexical_retrieval.py
- tests/test_knowledge.py
- tests/fixtures/agent_eval/knowledge_cases.json
- tests/fixtures/knowledge/pricing_v1.json
- tests/fixtures/knowledge/pricing_v2.json
- tests/fixtures/knowledge/sales_notes.json
- tests/fixtures/knowledge/product.md
- tests/fixtures/knowledge/refund_policy.txt
- tests/fixtures/knowledge/competitors.json
- tests/fixtures/knowledge/injection.md

Changed:

- README.md
- docs/architecture/DOMAIN_MODEL.md
- docs/architecture/AGENT_RUNTIME_ARCHITECTURE.md
- docs/architecture/SYSTEM_ARCHITECTURE.md
- docs/architecture/DATA_ARCHITECTURE.md
- docs/architecture/SECURITY_AND_PERMISSIONS.md
- docs/engineering/DEVELOPMENT_ROADMAP.md
- docs/engineering/TESTING_STRATEGY.md
- docs/engineering/EVALUATION_STRATEGY.md
- docs/engineering/OBSERVABILITY_STRATEGY.md
- docs/project/GLOSSARY.md
- docs/project/OPEN_QUESTIONS.md
- src/agent_company_os/domain/agent.py
- src/agent_company_os/domain/decisions.py
- src/agent_company_os/domain/events.py
- src/agent_company_os/domain/transitions.py
- src/agent_company_os/ports/ids.py
- src/agent_company_os/ports/model.py
- src/agent_company_os/adapters/ids.py
- src/agent_company_os/application/context.py
- src/agent_company_os/application/runtime.py
- src/agent_company_os/application/runtime_serialization.py
- src/agent_company_os/application/tool_validation.py

## Architectural decisions and deviations

ADR-007 records the internal retrieval choice, canonical source/pack boundaries,
trust versus relevance, version/freshness policy, bounds, conflict behavior, and
limited grounding contract. Accepted ADR-001 through ADR-006 were not edited.
The older roadmap's broad semantic-quality and deletion-propagation expectations
are explicitly deferred in ADR-007 in favor of the requested lexical/disablement
gate. No generic collection, vector, model-provider, memory, or planner abstraction
was introduced without a current invariant.

## Explicitly not implemented / deferred work

No learned Memory, episodic/semantic promotion, conversation retention system,
agent learning, automatic source updates, multi-agent delegation/communication,
Chief of Staff, planner/router, embeddings, vector database, semantic reranker,
live LLM provider, new external tools, external writes, OAuth, MCP, production
integrations, graph UI, queues, message bus, microservices, event sourcing,
distributed orchestration, web crawling, OCR, PDF ingestion, or paid API calls.
Existing scripted single-agent and read-only fixture-tool behavior is retained.

## Risks / open questions

- Lexical relevance and exact extraction do not prove natural-language answer quality.
- Query choice, effective dates, refresh, conflicting-source precedence, and calibrated
  free-text entailment remain open; timestamps alone are not freshness guarantees.
- Authenticated publishers/readers, collections, fine resource scopes, production rate
  limits, durable transactions/indexes, and process-loss recovery remain deferred.
- Source/pack retention, actual deletion, redaction, and audit privacy require policy
  before real sensitive documents are ingested. Disablement is not deletion.
- Small synchronous corpus limits are intentional; production scale needs new evidence.

## Completion and recommended next stage

All mandatory Stage 4 implementation and A–T test criteria passed. Documentation
reflects the offline baseline; no live-model, Memory, or multi-agent functionality
is claimed. The verified source identity, immutable evidence, permission checks,
and context separation enable a separate Stage 5 design for governed Memory.

Ready for Stage 5: first decide ownership, promotion/review, expiry/deletion, and
conflict handling with authoritative Knowledge. Stage 5 has not been started.
