# ADR-007: Company Brain and Knowledge Retrieval

## Status

Accepted, 2026-09-03. Extends ADR-005/006 without changing their historical decisions.
AI for judgment. Software for guarantees. Stage 4 is an offline retrieval foundation,
not a production knowledge service or a semantic-truth guarantee.

## Context

Stage 3 proves bounded read-only tool execution and receipt grounding (155 baseline
tests). The Research Brief Agent now needs approved organizational information that
is separate from supplied context and observed tool results. A Company Brain is the
logical capability to govern sources, versions, ingestion, retrieval, provenance,
access, and evidence—not a database product, agent persona, or Memory system.

## Decision

### Sources, publication, and authority

KnowledgeSource is stable workspace-scoped identity, name, type, and trust. Its
current state is active or disabled, with an optimistic mutation Version and a
separate current content Version. Publication of each KnowledgeSourceVersion is
sequential and immutable; a snapshot retains normalized content, SHA-256 hash,
typed facts when applicable, source metadata, UTC ingestion time, schema version,
normalization algorithm, chunking algorithm, and effective ingestion limits.
No re-enable or hard-delete command is added. Disabled sources cannot publish new
versions. Disablement revokes use, not historical audit access.

TrustClass is authoritative, approved_internal, or unverified_external. The first
two are allowed by default; broader access requires an explicit immutable grant.
Trust means declared source governance, not proof that every sentence is true.
The trusted application caller supplies approval/classification; authenticated
publishers, approval workflows, and fine-grained principal policies remain deferred.

KnowledgeScope on AgentDefinitionVersion grants up to 20 exact source identities
and an explicit trust allowlist. Collections add no current invariant and are
deferred. A newer definition cannot widen an existing AgentRun. Host query filters
can narrow these grants, never widen them. Source text and query text grant nothing.

### Ingestion and chunks

TextKnowledgeIngestor accepts bytes for plain text, Markdown, and structured facts.
Strict UTF-8 decoding, CRLF/CR-to-LF normalization, and control-character rejection
(except LF/tab) happen before indexing. Empty/blank input is rejected. No files,
URLs, Markdown directives, embedded code, macros, or instructions are executed.
Structured JSON has exactly company and facts; each fact has exactly key/value.
Duplicate JSON keys, duplicate identical facts, extra fields, and invalid types
are rejected. Canonical JSON binds typed facts to stored normalized content.

`paragraph-or-fact-v1` chunks text by paragraphs, splits long paragraphs at whitespace
or a hard character boundary, trims chunk-edge whitespace, and uses no overlap.
The full normalized source is retained separately. Structured facts each get one
chunk containing company/key/value and the original typed fact; oversized individual
facts fail rather than being cut into ungroundable fragments. Chunk IDs hash workspace,
source ID, content version, algorithm, configured size, ordinal, and content hash.
Recreating the same version yields identical chunks; a new version has distinct IDs.
The chunk projection lives in the domain, not inside the application adapter.

### Retrieval policy and bounds

KnowledgeRetriever is replaceable. LexicalKnowledgeRetriever is the only implemented
strategy (`lexical-overlap`, version 1). It tokenizes Unicode word terms after
case-folding and treating underscores as spaces; score is matched unique query terms
divided by unique query terms. Zero-overlap chunks are excluded. Ties use source ID,
then ordinal. Eligibility is checked before ranking; adapters cannot return foreign,
nonexistent, altered, or ungranted chunks. Score is not trust or freshness.

Current retrieval uses the latest published version of each active permitted source.
No semantic reranker, automatic refresh, date-based expiration, or conflict resolver
exists. Creation timestamps and exact versions describe capture freshness, not a
claim that business information is current. Duplicate text within a source is
suppressed; identical text across sources retains separate provenance. Per-source
caps provide simple diversity. Conflicting returned facts stay visible; the existing
required-key evaluator reports a gap when their values disagree. It does not discover
conflicts outside the returned evidence or decide which source is objectively true.

| Bound | Default | Hard maximum |
|---|---:|---:|
| Raw source bytes | 32,768 | 131,072 |
| Normalized source characters | 16,000 | 64,000 |
| Structured facts/source | 50 | 100 |
| Characters/chunk | 800 | 2,000 |
| Chunks/source version | 64 | 128 |
| Query characters | 512 | 512 |
| Returned candidates | 5 | 10 |
| Entire serialized EvidencePack characters | 4,000 | 12,000 |
| Candidates/source | 2 | 5 |
| Published sources/workspace | 100 | 100 |
| Versions/source | 20 | 20 |
| Published packs/run, including empty results | 5 | 5 |

Fact keys/company/name cap at 128 characters, fact values at 512. Query configuration
comes from typed host commands, never parsed from source/model text. Packs are trimmed
deterministically from the ranked tail to fit the full serialized envelope; a budget
too small even for the empty envelope is rejected. Truncation is explicit. ContextAssembler
also counts the full pack with all other runtime context against the existing run
limit (16,000 by default). These are character, not tokenizer budgets.

### Internal capability, not another tool or planner

Select Approach A: host-initiated KnowledgeService retrieval for an idle running
AgentRun before a model invocation. It may follow a normal request_more_context /
host resume cycle. The host explicitly chooses the bounded query; no planning or
automatic retrieval routing is implemented. Approach B (agent-requested retrieval)
is deferred until query-selection evaluation demonstrates a need for a new action.

AgentRuntimeService depends on KnowledgeRuntimePort for the active pack and grounded
facts. KnowledgeService depends on KnowledgeStore, KnowledgeIngestor, KnowledgeRetriever,
Clock, and IdGenerator. It does not register itself in ToolRegistry. ToolRuntimeService
continues to govern executable capabilities; tools and knowledge can both contribute
independent evidence to the same run. The four action families remain unchanged.

Knowledge-enabled runs pin `single-agent-knowledge-v1`, `bounded-knowledge-tools-v1`,
and `knowledge-facts-v1`. Earlier definitions retain their Stage 2/3 semantic identities.
ContextAssembler puts EvidencePack in a dedicated `knowledge_evidence` request field,
separate from instructions, supplied facts, and tool Observations.

### Evidence, grounding, and history

EvidenceCandidate carries exact chunk content/hash, source/version/name, declared
trust, source-version timestamp, relevance score, and typed fact if applicable.
EvidencePack is immutable and bound to workspace/run, query/filter/limits, strategy
version, ranked candidates, truncation metadata, and capture time. The run pins its
AgentDefinitionVersion and holds only an active pack ID in working state. All packs
remain separately readable after replacement, completion, or source disablement.
`serialize_pack` exports bounded historical evidence explicitly, not via object internals.

References are `knowledge:<encoded source ID>:<content version>:<encoded chunk ID>`.
Components are percent-encoded. Caller fact/source IDs and tool output IDs cannot
impersonate the reserved knowledge or tool_receipt namespaces. Grounding requires
exact key/value/reference membership in the active same-run permitted pack; a valid
reference alone is insufficient. Evicted packs remain auditable but cannot ground
new completion proposals. Updated sources do not reinterpret captured packs.

Free-text chunks are model-visible with references and persisted provenance, but do
not enter the exact structured-fact evaluator. Paraphrases, arbitrary narrative, and
universal semantic entailment remain unverified, not silently accepted. A retrieval
pack is evidence of what was supplied, not proof of world truth or that the model
actually considered every item. No output is promoted to Knowledge or Memory.

### Transactions, revocation, and audit

InMemoryKnowledgeStore uses the RuntimeStore transaction lock. Source/version/chunks
and publication Event commit together; pack, active run reference/version, query Event,
and pack Event commit together. Failure rolls all participating records back. Reads
are workspace/run scoped; direct publication validates chunk derivation and lineage.
No external I/O occurs inside these bounded synchronous retrieval transactions.
There is no claim of durable recovery, distributed atomicity, or hostile-code isolation.

Retrieval checks run version, active parents, deadline, pending invocation, grants,
trust, and source status. Context assembly and post-model reconciliation recheck
active evidence, so disablement during a model call prevents accepting its completion.
An exact captured older version is still usable until disablement or pack replacement.
In-flight retrieval mutation is denied; no background refresh or worker is present.

Events: knowledge_source_published, knowledge_source_disabled, knowledge_query_executed,
knowledge_query_rejected, evidence_pack_created. Source Events use KnowledgeSource
subjects; retrieval Events use AgentRun subjects and execution/attempt/definition/pack
correlation. Metadata includes query length, strategy/version, candidate/returned/source
counts, duration, source versions, evidence characters, and truncation. No raw query,
document body, exception message, or secret is copied into Event metadata. Query text
exists only in the access-controlled historical pack/model input. Rejection audit is
separate from the rolled-back operation; inaccessible run identity is not audited via
an unauthorized read. Normalized rejection metadata does not provide production rate
limiting or tamper-evident retention.

## Alternatives

- Vector storage/embeddings: unnecessary to prove scope/provenance; defer until a
  representative corpus shows lexical recall limitations worth the complexity.
- Full documents in every context: unbounded and loses the selection record; use packs.
- Mutable latest references in history: silently changes interpretation; exact versions.
- Tool-wrapper retrieval or new model action now: conflates execution and organizational
  knowledge, or adds query-selection behavior without evidence. Keep the internal seam.
- Event sourcing, separate services, queues, databases, or orchestration framework:
  no current requirement; retain typed ports and in-memory adapters.

## Consequences

The deterministic corpus and 51 added tests cover the A–T Stage 4 scenarios. The full
206-test gate passes locally. Scripted evaluations establish enforcement and baseline
ranking, not live-model relevance, adversarial robustness, or semantic answer quality.
Small hard corpus bounds make synchronous scanning acceptable for this stage.

The former roadmap's broad deletion/semantic-quality targets are narrowed to the
requested disablement and deterministic baseline gate. Actual deletion propagation,
calibrated semantic quality, and live providers remain explicitly unimplemented.

## Deferred Questions

Authenticated source publishers and readers; collection semantics; retention/deletion
and historical redaction; revision-effective dates and refresh policy; cross-source
conflict adjudication; free-text entailment evaluation; query-selection strategy;
semantic/hybrid ranking; durable indexes/transactions/recovery; source count scaling;
production rate limits and audit storage. Stage 5 must separately decide Memory
ownership, promotion, expiry, and conflict policy. It is not started by this ADR.
