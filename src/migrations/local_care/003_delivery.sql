CREATE TABLE care_events (
    person_id TEXT NOT NULL, model_version TEXT NOT NULL, event_id TEXT NOT NULL,
    mode TEXT NOT NULL CHECK(mode IN ('shadow','live')),
    kind TEXT NOT NULL, region_id TEXT NOT NULL,
    started_at REAL NOT NULL, ended_at REAL,
    PRIMARY KEY(person_id,model_version,event_id)
) WITHOUT ROWID;
CREATE INDEX care_events_scope_time ON care_events(person_id,model_version,mode,started_at,event_id);
CREATE TABLE care_sessions (
    person_id TEXT NOT NULL, model_version TEXT NOT NULL, mode TEXT NOT NULL,
    checkpoint_json TEXT NOT NULL, active_event_id TEXT, updated_at REAL NOT NULL,
    PRIMARY KEY(person_id,model_version,mode)
) WITHOUT ROWID;
CREATE TABLE care_outbox (
    person_id TEXT NOT NULL, model_version TEXT NOT NULL, message_id TEXT NOT NULL,
    mode TEXT NOT NULL CHECK(mode='live'), event_id TEXT NOT NULL,
    message_type TEXT NOT NULL CHECK(message_type IN ('reminder','feedback')),
    revision INTEGER NOT NULL, payload_json TEXT NOT NULL, created_at REAL NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT, delivered_at REAL,
    PRIMARY KEY(person_id,model_version,message_id),
    FOREIGN KEY(person_id,model_version,event_id) REFERENCES care_events(person_id,model_version,event_id)
) WITHOUT ROWID;
CREATE INDEX care_outbox_scope_pending ON care_outbox(person_id,model_version,delivered_at,created_at,event_id,message_type,revision);
