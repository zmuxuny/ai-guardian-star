-- Additive only; previous feedback, events and checkpoints are unchanged.
CREATE TABLE weekly_observations (
 person_id TEXT NOT NULL, model_version TEXT NOT NULL, mode TEXT NOT NULL CHECK(mode IN ('live','shadow')),
 observation_id TEXT NOT NULL, region_id TEXT NOT NULL,
 started_at REAL NOT NULL, ended_at REAL NOT NULL CHECK(ended_at>started_at),
 valid INTEGER NOT NULL CHECK(valid IN (0,1)), quality REAL CHECK(quality>=0 AND quality<=1),
 PRIMARY KEY(person_id,model_version,mode,observation_id)
);
CREATE INDEX weekly_observations_scope_time ON weekly_observations(person_id,model_version,mode,ended_at,started_at);
CREATE TABLE weekly_policies (
 person_id TEXT NOT NULL, model_version TEXT NOT NULL, mode TEXT NOT NULL CHECK(mode IN ('live','shadow')),
 retention_days INTEGER NOT NULL CHECK(retention_days BETWEEN 1 AND 3650),
 min_samples INTEGER NOT NULL CHECK(min_samples BETWEEN 1 AND 10080), last_cleanup REAL,
 PRIMARY KEY(person_id,model_version,mode)
);
CREATE TABLE care_privacy (
 person_id TEXT NOT NULL, model_version TEXT NOT NULL, erased_at REAL NOT NULL,
 PRIMARY KEY(person_id,model_version)
);
