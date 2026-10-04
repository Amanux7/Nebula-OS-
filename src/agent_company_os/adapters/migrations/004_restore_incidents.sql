-- Restore provenance and permanent fences survive release of the workspace mode.
CREATE TABLE restore_incidents (
    generation INTEGER PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    backup_id TEXT NOT NULL,
    backup_digest TEXT NOT NULL,
    manifest_json TEXT NOT NULL CHECK(json_valid(manifest_json)),
    restored_at TEXT NOT NULL,
    principal_id TEXT NOT NULL,
    validated INTEGER NOT NULL CHECK(validated=1),
    UNIQUE(workspace_id,generation)
) STRICT;
CREATE TABLE restored_intent_holds (
    workspace_id TEXT NOT NULL,
    intent_id TEXT NOT NULL,
    generation INTEGER NOT NULL,
    PRIMARY KEY(workspace_id,intent_id),
    FOREIGN KEY(workspace_id,generation) REFERENCES restore_incidents(workspace_id,generation)
) STRICT;
CREATE TABLE quarantine_release_audit (
    sequence INTEGER PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    principal_id TEXT NOT NULL,
    generation INTEGER,
    timestamp TEXT NOT NULL,
    previous_mode TEXT NOT NULL,
    new_mode TEXT NOT NULL,
    success INTEGER NOT NULL CHECK(success IN (0,1)),
    reason TEXT NOT NULL,
    recovery_count INTEGER NOT NULL,
    held_intent_count INTEGER NOT NULL
) STRICT;
CREATE TRIGGER restore_incident_no_update BEFORE UPDATE ON restore_incidents
BEGIN SELECT RAISE(ABORT, 'immutable restore provenance'); END;
CREATE TRIGGER restore_incident_no_delete BEFORE DELETE ON restore_incidents
BEGIN SELECT RAISE(ABORT, 'immutable restore provenance'); END;
CREATE TRIGGER restore_hold_no_update BEFORE UPDATE ON restored_intent_holds
BEGIN SELECT RAISE(ABORT, 'immutable restore hold'); END;
CREATE TRIGGER restore_hold_no_delete BEFORE DELETE ON restored_intent_holds
BEGIN SELECT RAISE(ABORT, 'immutable restore hold'); END;
CREATE TRIGGER release_audit_no_update BEFORE UPDATE ON quarantine_release_audit
BEGIN SELECT RAISE(ABORT, 'immutable release audit'); END;
CREATE TRIGGER release_audit_no_delete BEFORE DELETE ON quarantine_release_audit
BEGIN SELECT RAISE(ABORT, 'immutable release audit'); END;
