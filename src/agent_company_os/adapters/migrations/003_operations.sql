CREATE TABLE operational_modes (
    workspace_id TEXT PRIMARY KEY,
    workspace_kind TEXT NOT NULL DEFAULT 'workspace' CHECK(workspace_kind='workspace'),
    mode TEXT NOT NULL CHECK(mode IN ('normal','maintenance','restore_quarantine')),
    version INTEGER NOT NULL CHECK(version > 0),
    FOREIGN KEY(workspace_kind,workspace_id) REFERENCES domain_records(kind,id)
);
CREATE TABLE operational_audit (
    sequence INTEGER PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    workspace_kind TEXT NOT NULL DEFAULT 'workspace' CHECK(workspace_kind='workspace'),
    principal_id TEXT NOT NULL,
    previous_mode TEXT NOT NULL,
    mode TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    reason TEXT NOT NULL CHECK(reason IN ('operator_command','canonical_restore')),
    FOREIGN KEY(workspace_kind,workspace_id) REFERENCES domain_records(kind,id)
);
CREATE TRIGGER operational_audit_no_update BEFORE UPDATE ON operational_audit
BEGIN SELECT RAISE(ABORT, 'immutable operational audit'); END;
CREATE TRIGGER operational_audit_no_delete BEFORE DELETE ON operational_audit
BEGIN SELECT RAISE(ABORT, 'immutable operational audit'); END;
