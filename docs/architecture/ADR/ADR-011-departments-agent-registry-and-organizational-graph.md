# ADR-011: Departments, Agent Registry, and Organizational Graph

## Status

Accepted — Stage 8, 2026-09-06. Offline deterministic implementation.

## Context

Stages 6 and 7 already own plan validation, AgentSelector, canonical Delegations,
AgentRuns, messages, and handoffs. Organizational discovery needs explicit departments,
responsibilities, and capability identities without introducing another source of
agent configuration or allowing hierarchy to transfer authority.

## Decision

### Identity, immutable versions, and publication

One `OrganizationGraph` identifies one workspace's organization. Its optimistic
`revision` and `active_version` pointer are separate from immutable
`OrganizationGraphVersion` content. A graph version owns bounded tuples of Department,
OrgRole, CapabilityDefinition, RegisteredAgent references, DepartmentMembership,
ReportingRelationship, OrganizationPolicy, and bounds. These are canonical structural
records inside the version, not separate independently mutable aggregates.

`OrganizationService` is a trusted host application command boundary. Creating the
graph, constructing a candidate version, publishing, and activating are explicit.
Publication validates structural integrity and exact existing RuntimeStore definitions,
then appends a sequential version. Activation validates again and atomically changes
the pointer with an expected revision. Failed publication/activation leaves the prior
graph, directory, and audit intact. Published versions cannot be edited or removed.
Membership, role, department, reporting, and policy changes publish another whole version.
There is no independently persisted mutable draft or autonomous mutation Action.

Company identity uses the existing Workspace; a duplicate Company aggregate is not
introduced. Graph visualization remains a future projection/client of these records.

### Departments, roles, memberships, and reporting

Departments have active/disabled structural state and bounded untrusted descriptions.
OrgRole expresses responsibility, with an explicit `is_lead` structural designation.
It does not replace the AgentDefinitionVersion runtime role or its communication grants.
Membership uses AgentDefinition identity, department ID, role ID, active/revoked state,
discoverability, and optional UTC effective bounds. The end instant is exclusive.
Queries evaluate effective windows with the injected Clock, without a scheduler.
Disabled departments and revoked/expired/hidden memberships cannot produce candidates.

Multiple memberships must be explicit and bounded. There is at most one active lead
membership per department, conservatively even for non-overlapping future dates.
Reporting supports one manager per subordinate. Self-reporting, unknown/foreign
references, duplicate parents, cycles, and excessive depth fail. Reporting is structural;
it never changes the identity or grants of either participant. Escalation returns the
discoverable department lead as a destination, without assigning or executing a Task.

### Canonical capabilities and registry

`CapabilityId` identifies a workspace-local CapabilityDefinition. Exact immutable
AgentDefinitionVersions may reference up to ten `capability_ids`; publication validates
those IDs against the graph's catalog. Existing `capabilities` string labels remain for
Stage 6 compatibility and historical interpretation. Stage 8 directory queries and demo
requirements use typed IDs; no name or descriptive-text inference exists. Disabled
capabilities cannot satisfy a query requiring them.

RegisteredAgent contains only workspace, AgentDefinitionId, and exact Version. RuntimeStore
remains the single authority for configuration, publication, enabled state, and grants.
AgentRegistry returns canonical definitions in stable ID/version order. Queries filter
department, role, capabilities, effective membership, discoverability, and enabled state.
Returned records/snapshots are immutable. Foreign or altered snapshots and unknown filter
IDs fail explicitly. No natural-language directory search or distributed registry exists.

### Selection and version pinning

An organization-enabled OrchestrationService captures the active graph at start and
stores its immutable OrganizationSnapshot on OrchestrationRun. The snapshot identifies
the exact graph and capture time. Store mutation guards prohibit changing that pin.
New runs use newly activated versions; existing runs and replans keep their original
version and exact registered definition references. Publication of a newer agent version
does not silently replace the version in an already pinned organization.

Membership effective dates continue to be evaluated at use time within that pinned
version. A v2 revocation affects runs/discovery using v2, not a run pinned to v1. This is
historical structural policy, not an emergency global revocation mechanism. Existing
Tool/Knowledge/Memory revocation controls remain independently authoritative.

AgentRegistry discovers; the existing AgentSelector selects. Required departments and
roles filter candidates. Preferred departments are attempted first; if no preferred
candidate meets runtime requirements, selection falls back deterministically. The
existing active-run-count/ID/version tie-break remains within each group. Tool grants,
Knowledge sources, Memory scopes, autonomy, and orchestration allowlists still apply.
Plan acceptance, delegation, and execution recheck eligibility. Missing registry wiring
fails for pinned runs; organization requirements on legacy unpinned runs fail explicitly.
Legacy Stage 6/7 services without organizational requirements retain their baseline behavior.

### Department policy intersection

OrganizationPolicy contains explicit directional allow/deny rules for delegate,
message, and handoff. Same-department routes default to allow; cross-department routes
default to deny. Explicit rules override defaults, and duplicate/conflicting rules fail
validation. For multiple effective memberships, every source/target department pair must
allow the operation. A second membership cannot launder a denied route.

Initial host routing may specify a source department; with none, the host is the root
initiator and does not impersonate a department. Dependency-result sources and prior
assignees constrain delegation. Message delivery applies organizational policy before
the existing Stage 7 participant/version/role/reference checks. Handoff resolution
requires both handoff and delegation policy, original Task requirements, and requested
recipient requirements before existing canonical redelegation. Required department
conflicts are rejected; a preference can permit cross-department specialization.

Organization can only narrow eligibility. A lead cannot inherit Tool grants, Knowledge,
Memory, credentials, receipts, or identity. Models, plans, and messages have no port for
organizational writes; role spoofing and description injection have no structural effect.

### Bounds, events, and storage

| Bound | Default | Hard maximum |
|---|---:|---:|
| Departments | 12 | 32 |
| Roles | 16 | 64 |
| Capabilities | 32 | 128 |
| Memberships / registered agents / reporting edges | 64 each | 256 each |
| Memberships per agent | 3 | 8 |
| Agents per department | 20 | 64 |
| Reporting depth, in edges | 5 | 10 |
| Cross-department rules | 64 | 256 |

Names are at most 200 characters, department descriptions 1,000 characters, and
capability query/definition lists ten IDs. Whole-version bounds apply before traversal.
Events record version creation and activation with graph/version and structural counts;
the exact snapshot supplies the detailed change history. Existing orchestration Events
include the graph pin. Query telemetry is not an immutable Event per directory read.
There is no metrics backend or claim of production telemetry.

InMemoryOrganizationStore shares the existing runtime/domain lock and rollback boundary.
No graph database, external dependency, event sourcing, queue, or service is added.
Explicit serialization exports graph identity/version, structure, lifecycle, dates,
rules, and limits for audit. Historical orchestration remains linked to exact state.

## Alternatives

- Independent repositories and versions for every role/membership/edge: rejected at
  this scale; whole snapshots make coherent activation and historical routing simpler.
- Registry copies full mutable agent configuration: rejected; exact references resolve
  existing RuntimeStore records and avoid duplicate authority.
- Registry chooses the final agent: rejected; selection remains the existing port.
- Hierarchy-derived permission aggregation: rejected; department policy only narrows.
- Latest graph on every operation: rejected; changes historical semantics mid-run.
- Semantic directory search, dynamic agents, or graph database: unnecessary to prove
  the current organizational invariants and explicitly deferred.

## Consequences

Organization-aware runs remain reproducible and existing permission enforcement is
preserved. Whole versions are easy to audit but copy bounded structure. Conservative
multi-membership policy may reject a route that a future explicit department-context
model could safely allow. Lead windows are deliberately simple. All state disappears
on process exit. Host administration is trusted in-process code, not authenticated
production identity; tests prove deterministic guarantees, not live-model quality.

## Deferred Questions

Authenticated organization administrators and approvers; immediate revocation of pinned
structure; department-context selection for matrix organizations; overlapping lead
windows; durable concurrent storage and recovery; revision retention/redaction; UI and
visual organization editor; LDAP/SCIM; distributed directory; calibrated selection
quality; analytics; dynamic agent creation, hiring/firing, and autonomous restructuring.
Stage 9 is not implemented by this decision.
