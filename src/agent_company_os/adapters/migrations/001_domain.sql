-- Stage 10 initial storage slice. Runtime/dispatch tables are NOT introduced here.
CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY CHECK (version > 0),
    checksum TEXT NOT NULL
) STRICT;

CREATE TABLE domain_records (
    kind TEXT NOT NULL CHECK (kind IN ('workspace','goal','task','task_attempt','execution')),
    id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    workspace_kind TEXT NOT NULL DEFAULT 'workspace' CHECK (workspace_kind = 'workspace'),
    version INTEGER NOT NULL CHECK (version > 0),
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    payload TEXT NOT NULL CHECK (json_valid(payload)),
    goal_id TEXT,
    goal_kind TEXT NOT NULL DEFAULT 'goal' CHECK (goal_kind = 'goal'),
    task_id TEXT,
    task_kind TEXT NOT NULL DEFAULT 'task' CHECK (task_kind = 'task'),
    execution_id TEXT,
    execution_kind TEXT NOT NULL DEFAULT 'execution' CHECK (execution_kind = 'execution'),
    PRIMARY KEY (kind, id),
    UNIQUE (workspace_id, kind, id),
    FOREIGN KEY (workspace_kind, workspace_id) REFERENCES domain_records(kind,id),
    FOREIGN KEY (workspace_id,goal_kind,goal_id) REFERENCES domain_records(workspace_id,kind,id),
    FOREIGN KEY (workspace_id,task_kind,task_id) REFERENCES domain_records(workspace_id,kind,id),
    FOREIGN KEY (workspace_id,execution_kind,execution_id) REFERENCES domain_records(workspace_id,kind,id),
    CHECK (kind != 'workspace' OR id = workspace_id),
    CHECK ((kind IN ('task','execution')) = (goal_id IS NOT NULL)),
    CHECK ((kind = 'task_attempt') = (task_id IS NOT NULL)),
    CHECK ((kind = 'task_attempt') = (execution_id IS NOT NULL))
) STRICT;

CREATE TABLE domain_audit (
    kind TEXT NOT NULL CHECK (kind IN ('event','transition')),
    id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    subject_kind TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    payload TEXT NOT NULL CHECK (json_valid(payload)),
    PRIMARY KEY (kind,id),
    FOREIGN KEY (workspace_id,subject_kind,subject_id) REFERENCES domain_records(workspace_id,kind,id)
) STRICT;
CREATE INDEX domain_audit_timeline ON domain_audit(workspace_id,occurred_at,id);
CREATE TRIGGER domain_audit_no_update BEFORE UPDATE ON domain_audit
BEGIN SELECT RAISE(ABORT,'audit_is_append_only'); END;
CREATE TRIGGER domain_audit_no_delete BEFORE DELETE ON domain_audit
BEGIN SELECT RAISE(ABORT,'audit_is_append_only'); END;
