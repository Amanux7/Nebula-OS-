-- Separate local identity database. Never restored from a canonical application backup.
CREATE TABLE operator_schema(version INTEGER PRIMARY KEY CHECK(version=1), checksum TEXT NOT NULL);
CREATE TABLE operator_accounts(
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('viewer','auditor','operator','admin')),
    enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
    version INTEGER NOT NULL CHECK(version > 0),
    credential_digest TEXT NOT NULL UNIQUE CHECK(length(credential_digest)=64)
);
CREATE TABLE operator_sessions(
    digest TEXT PRIMARY KEY CHECK(length(digest)=64),
    principal_id TEXT NOT NULL REFERENCES operator_accounts(id),
    principal_version INTEGER NOT NULL CHECK(principal_version > 0),
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked INTEGER NOT NULL CHECK(revoked IN (0,1))
);
CREATE TABLE operator_audit(
    sequence INTEGER PRIMARY KEY,
    principal_id TEXT NOT NULL REFERENCES operator_accounts(id),
    workspace_id TEXT NOT NULL,
    command TEXT NOT NULL CHECK(command IN ('local_provision','session_created','session_revoked','disabled')),
    target_id TEXT NOT NULL REFERENCES operator_accounts(id),
    timestamp TEXT NOT NULL
);
CREATE INDEX operator_audit_workspace ON operator_audit(workspace_id, sequence);
CREATE TRIGGER operator_audit_no_update BEFORE UPDATE ON operator_audit
BEGIN SELECT RAISE(ABORT, 'operator audit is immutable'); END;
CREATE TRIGGER operator_audit_no_delete BEFORE DELETE ON operator_audit
BEGIN SELECT RAISE(ABORT, 'operator audit is immutable'); END;
