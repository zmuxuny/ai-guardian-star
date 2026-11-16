-- Additive migration: existing fields/rows are untouched; old source is NULL.
ALTER TABLE baseline_samples ADD COLUMN source TEXT;
