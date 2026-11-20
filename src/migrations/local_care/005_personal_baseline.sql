-- Local-only features and derived samples. Nothing here is an outbox payload.
CREATE TABLE posture_features (
    person_id TEXT NOT NULL, model_version TEXT NOT NULL, mode TEXT NOT NULL,
    event_id TEXT NOT NULL, feature_version TEXT NOT NULL, camera_revision TEXT NOT NULL,
    feature_json TEXT NOT NULL, guards_json TEXT NOT NULL, captured_at REAL NOT NULL,
    PRIMARY KEY(person_id,model_version,mode,event_id),
    FOREIGN KEY(person_id,model_version,event_id) REFERENCES care_events(person_id,model_version,event_id)
) WITHOUT ROWID;
CREATE TABLE posture_samples (
    person_id TEXT NOT NULL, model_version TEXT NOT NULL, mode TEXT NOT NULL,
    event_id TEXT NOT NULL, label TEXT NOT NULL CHECK(label IN ('normal','risk')),
    feedback_revision INTEGER NOT NULL,
    PRIMARY KEY(person_id,model_version,mode,event_id),
    FOREIGN KEY(person_id,model_version,mode,event_id)
        REFERENCES posture_features(person_id,model_version,mode,event_id)
) WITHOUT ROWID;
CREATE TABLE posture_histograms (
    person_id TEXT NOT NULL, model_version TEXT NOT NULL, mode TEXT NOT NULL,
    feature_version TEXT NOT NULL, camera_revision TEXT NOT NULL, day_start REAL NOT NULL,
    region_id TEXT NOT NULL, time_slot INTEGER NOT NULL,
    axis TEXT NOT NULL, bin INTEGER NOT NULL, count INTEGER NOT NULL CHECK(count>0),
    PRIMARY KEY(person_id,model_version,mode,feature_version,camera_revision,day_start,region_id,time_slot,axis,bin)
) WITHOUT ROWID;
CREATE INDEX posture_features_scope_time ON posture_features(person_id,model_version,mode,captured_at,event_id);
