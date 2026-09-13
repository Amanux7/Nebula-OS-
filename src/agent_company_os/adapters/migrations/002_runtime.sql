-- Canonical typed records share the same transaction as Stage 1 state and audit.
CREATE TABLE canonical_records (
    collection TEXT NOT NULL,
    record_key TEXT NOT NULL,
    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
    workspace_id TEXT NOT NULL,
    workspace_kind TEXT NOT NULL DEFAULT 'workspace' CHECK (workspace_kind = 'workspace'),
    revision INTEGER NOT NULL CHECK (revision > 0),
    entity_version INTEGER NOT NULL CHECK (entity_version > 0),
    retention TEXT NOT NULL CHECK (retention IN ('operational','audit','sensitive')),
    payload TEXT NOT NULL CHECK(json_valid(payload)),
    PRIMARY KEY(collection,record_key),
    UNIQUE(workspace_id,collection,record_key),
    FOREIGN KEY(workspace_kind,workspace_id) REFERENCES domain_records(kind,id)
) STRICT;
CREATE INDEX canonical_scope ON canonical_records(workspace_id,collection);
CREATE TABLE canonical_links (
    workspace_id TEXT NOT NULL,
    collection TEXT NOT NULL,
    record_key TEXT NOT NULL,
    target_collection TEXT NOT NULL,
    target_key TEXT NOT NULL,
    PRIMARY KEY(collection,record_key,target_collection,target_key),
    FOREIGN KEY(workspace_id,collection,record_key)
        REFERENCES canonical_records(workspace_id,collection,record_key),
    FOREIGN KEY(workspace_id,target_collection,target_key)
        REFERENCES canonical_records(workspace_id,collection,record_key)
) STRICT;
