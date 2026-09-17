-- Independent offline external-system fixture. NOT the canonical application DB.
CREATE TABLE fixture_effects (
    idempotency_key TEXT PRIMARY KEY,
    payload_digest TEXT NOT NULL,
    destination TEXT NOT NULL,
    message TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('processed_success','processed_failure')),
    output_json TEXT
) STRICT;
