# ADR-008: Governed Memory

## Status

Accepted — Stage 5, 2026-09-04.

## Context

Stage 4 established authoritative Knowledge and immutable EvidencePacks. Retained
experience has different authority, privacy, freshness, and lifecycle semantics. A
generic memory field, automatic transcript retention, or model-controlled write path
would let unsupported output become durable context and could silently override
company sources. Stage 5 needs one deterministic, offline seam that proves governance
without choosing embeddings, a vector database, or a production retention system.

## Decision

### Meaning and records

Memory is deliberately retained, experience-derived context. It is not Working State,
Conversation History, Knowledge, an EvidencePack, a ToolReceipt, an Event, or a log.

- `MemoryCandidate` is a bounded host-derived proposal with type, subject, content,
  exact scope, provenance, authority, sensitivity, optional structured claim/expiry,
  policy version, status, and optimistic Version.
- `MemoryEntry` is created only from a human-approved candidate. Its content,
  provenance, review identity/time, type, scope, and sensitivity are immutable.
  Lifecycle metadata may move from `active` to `revoked` or `superseded`.
- `MemoryContextPack` is an immutable, workspace/run-bound snapshot of exact retrieved
  entries, ranking metadata, conflict flags, query, bounds, and capture time. It is
  separate from `EvidencePack` and cannot satisfy the completion grounding contract.
- `episodic` and `semantic` are the only Stage 5 memory types. Both require review;
  semantic memory never auto-promotes.

### Creation, review, and provenance

There is no model `save_memory` Action. Trusted host code proposes candidates after a
successful source AgentRun from canonical user statements, successful ToolReceipt
facts, task results, active Knowledge references, or explicitly identified agent
output. Exact source run and references are retained. Knowledge-derived restatements,
detectable credential-like content, and unsupported model inference are rejected.
All otherwise eligible candidates enter `under_review`. A named human reviewer must
approve or reject them. Policy decisions and lifecycle changes are audited.

The secret-pattern check is defense in depth, not a claim of complete secret detection.
Production identity, DLP, deletion, and reviewer authorization remain deferred.

### Scope, sensitivity, and retrieval

An immutable `MemoryAccessPolicy` is attached to an `AgentDefinitionVersion`. It uses
explicit exact `MemoryScope` grants (`workspace`, `agent`, `user`, `customer`, `task`,
or `domain`) and sensitivity grants (`normal`, `sensitive`, `restricted`). There is no
implicit global scope. Queries may narrow but never widen those grants.

The Stage 5 retriever requires an exact normalized subject match, then ranks by bounded
lexical overlap, review recency, and stable ID. Relevance score is not truth or
authority. It returns at most 5 entries by default (10 hard maximum), at most 4,000
serialized characters by default (12,000 hard maximum), and at most 5 packs per run.
Candidate content is limited to 1,000 characters; provenance to 10 references;
workspaces to 200 candidates and 200 entries; and subjects to 20 entries.

Expired, revoked, superseded, foreign-workspace, out-of-scope, or sensitivity-denied
entries are excluded. Expiry is evaluated lazily without rewriting history. Revocation
and supersession do not hard-delete prior entries or historical packs. Exact duplicate
candidates return the existing record. Promotion and supersession share an atomic
boundary with candidate, entry, Event, and runtime state changes.

### Runtime use and precedence

Host code retrieves memory before a model invocation. `AgentWorkingState` holds only
the active pack ID; `AgentModelRequest.memory_context` carries the separate pack.
The runtime revalidates the active pack before context assembly and again after the
model call. Concurrent revocation, supersession, expiry, or scope invalidation rejects
the stale result. The runtime protocol and policy versions are pinned as
`single-agent-memory-v1` and `governed-memory-v1` for memory-enabled definitions.

Authority precedence is:

1. authoritative/approved Knowledge;
2. reviewed Memory;
3. observed Episodic Memory;
4. inferred Semantic Memory.

Conflicts are preserved and flagged; Memory is not overwritten merely because it
conflicts. More importantly, Memory is never passed to `validate_brief` as evidence.
Only supplied facts, successful same-run ToolReceipt facts, and active structured
Knowledge facts can ground Stage 5 completion. Thus higher authority wins by contract,
not prompt wording.

### Audit and persistence

Minimal Events cover candidate creation, review request, rejection, promotion,
revocation, supersession, retrieval, and pack creation. Canonical entity state remains
directly stored; this is not event sourcing. The implementation uses an in-memory
adapter sharing the existing runtime rollback boundary. No durable database, queue,
vector index, background consolidation process, or distributed transaction is chosen.

## Alternatives Considered

### Model-controlled `save_memory`

Rejected for Stage 5. It expands the untrusted Action surface and makes poisoning and
duplicate control harder before policy and review behavior are proven.

### Auto-promote concrete episodic observations

Deferred. Even concrete observations may be sensitive, misleading, or scoped to the
wrong subject. Review-only promotion is intentionally conservative and measurable.

### Store every conversation or execution as memory

Rejected. History and audit data have different purposes and retention duties. Broad
capture would violate minimization and make retrieval authority ambiguous.

### Let Memory participate in grounding

Rejected. Reviewed experience is still not an authoritative source. Knowledge and
receipts retain their explicit evidence roles.

### Embeddings/vector storage or a memory framework

Rejected. Exact-subject lexical retrieval proves scope, lifecycle, precedence, and
runtime invalidation without infrastructure or semantic-quality claims.

### Hard delete on revocation or expiry

Rejected for the in-memory Stage 5 contract because it destroys audit interpretation.
Production privacy deletion and redaction require a later category-specific design.

## Consequences

- Historical executions identify exact memory snapshots and remain interpretable.
- Human review and exact grants reduce poisoning and accidental over-sharing.
- Retrieval is deterministic, testable, and intentionally limited in recall.
- Conflicts remain visible while Knowledge keeps authoritative precedence.
- New memory does not retroactively change an existing pack; invalidation changes do.
- Review creates operational work, and the in-memory adapter provides no durability.
- Secret detection, reviewer identity, and lexical relevance are not production-grade.

## Deferred Questions

- Authenticated reviewer roles, separation of duties, and approval UI.
- Production retention, user deletion, redaction, legal hold, and backup propagation.
- Evidence-based auto-promotion criteria, if any, and correction workflows.
- Confidence calibration and whether it adds value beyond authority/provenance.
- Semantic/hybrid retrieval, embeddings, indexes, and corpus-scale performance.
- Cross-scope sharing, portability, multi-agent memory, and delegation semantics.
- Durable persistence, concurrent policy linearization, and process-loss recovery.
- Automated consolidation, decay, summarization, and contradiction adjudication.
