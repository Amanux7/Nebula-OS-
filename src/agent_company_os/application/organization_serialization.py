"""Explicit versioned organizational exports; no implicit object serialization."""

from agent_company_os.domain.organization import OrganizationSnapshot


def serialize_organization(snapshot: OrganizationSnapshot) -> dict[str, object]:
    graph = snapshot.graph
    return {
        "schema_version": graph.schema_version,
        "graph_id": str(graph.graph_id),
        "workspace_id": str(graph.workspace_id),
        "graph_version": graph.version.value,
        "created_at": graph.created_at.isoformat(),
        "captured_at": snapshot.captured_at.isoformat(),
        "departments": [
            {
                "id": str(d.id),
                "name": d.name,
                "status": d.status.value,
                "description": d.description,
            }
            for d in graph.departments
        ],
        "roles": [{"id": str(r.id), "name": r.name, "is_lead": r.is_lead} for r in graph.roles],
        "capabilities": [
            {"id": str(c.id), "name": c.name, "status": c.status.value} for c in graph.capabilities
        ],
        "agents": [{"id": str(a.agent_id), "version": a.version.value} for a in graph.agents],
        "memberships": [
            {
                "agent_id": str(m.agent_id),
                "department_id": str(m.department_id),
                "role_id": str(m.role_id),
                "status": m.status.value,
                "discoverable": m.discoverable,
                "effective_from": m.effective_from.isoformat() if m.effective_from else None,
                "effective_until": m.effective_until.isoformat() if m.effective_until else None,
            }
            for m in graph.memberships
        ],
        "reporting": [
            {"subordinate": str(r.subordinate), "manager": str(r.manager)} for r in graph.reporting
        ],
        "routes": [
            {
                "source": str(r.source),
                "target": str(r.target),
                "kind": r.kind.value,
                "allowed": r.allowed,
            }
            for r in graph.policy.routes
        ],
        "bounds": {
            "departments": graph.bounds.departments,
            "roles": graph.bounds.roles,
            "capabilities": graph.bounds.capabilities,
            "memberships": graph.bounds.memberships,
            "memberships_per_agent": graph.bounds.memberships_per_agent,
            "agents_per_department": graph.bounds.agents_per_department,
            "reporting_depth": graph.bounds.reporting_depth,
            "cross_department_rules": graph.bounds.cross_department_rules,
        },
    }
