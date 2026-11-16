-- Dedicated local care database; every key and index carries both scope fields.
CREATE TABLE feedback (
    person_id TEXT NOT NULL,
    model_version TEXT NOT NULL,
    target_id TEXT NOT NULL,
    window_start INTEGER NOT NULL CHECK(window_start >= 0 AND window_start % 300 = 0),
    event_at REAL NOT NULL CHECK(event_at >= window_start AND event_at < window_start + 300),
    payload_json TEXT NOT NULL,
    created_at REAL NOT NULL CHECK(created_at >= 0),
    updated_at REAL NOT NULL CHECK(updated_at >= created_at),
    is_revoked INTEGER NOT NULL DEFAULT 0 CHECK(is_revoked IN (0,1)),
    revoked_at REAL,
    revocation_reason TEXT,
    revision INTEGER NOT NULL CHECK(revision >= 1),
    CHECK((is_revoked = 0 AND revoked_at IS NULL AND revocation_reason IS NULL)
       OR (is_revoked = 1 AND revoked_at IS NOT NULL AND revocation_reason IS NOT NULL)),
    PRIMARY KEY (person_id, model_version, target_id, window_start)
) WITHOUT ROWID;
CREATE INDEX feedback_scope_status_time
    ON feedback(person_id, model_version, is_revoked, updated_at, target_id, window_start);

CREATE TABLE feedback_audit (
    person_id TEXT NOT NULL,
    model_version TEXT NOT NULL,
    target_id TEXT NOT NULL,
    window_start INTEGER NOT NULL,
    revision INTEGER NOT NULL,
    operation TEXT NOT NULL CHECK(operation IN ('submit','revoke','restore')),
    recorded_at REAL NOT NULL,
    snapshot_json TEXT NOT NULL,
    PRIMARY KEY (person_id, model_version, target_id, window_start, revision),
    FOREIGN KEY (person_id, model_version, target_id, window_start)
      REFERENCES feedback(person_id, model_version, target_id, window_start)
) WITHOUT ROWID;

CREATE TABLE baseline_samples (
    person_id TEXT NOT NULL,
    model_version TEXT NOT NULL,
    sample_id TEXT NOT NULL,
    category TEXT NOT NULL CHECK(category IN ('posture','activity','routine')),
    payload_json TEXT NOT NULL,
    sampled_at REAL NOT NULL CHECK(sampled_at >= 0),
    created_at REAL NOT NULL CHECK(created_at >= 0),
    updated_at REAL NOT NULL CHECK(updated_at >= created_at),
    PRIMARY KEY (person_id, model_version, sample_id)
) WITHOUT ROWID;
CREATE INDEX baseline_scope_category_time
    ON baseline_samples(person_id, model_version, category, sampled_at, sample_id);
