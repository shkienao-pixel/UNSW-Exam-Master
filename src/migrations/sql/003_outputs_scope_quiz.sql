-- Extend outputs schema for v0.2.2 scope-bound generation and quiz outputs.
ALTER TABLE outputs ADD COLUMN output_type TEXT NOT NULL DEFAULT '';
ALTER TABLE outputs ADD COLUMN scope_artifact_ids TEXT NOT NULL DEFAULT '[]';
ALTER TABLE outputs ADD COLUMN model_used TEXT NOT NULL DEFAULT '';

UPDATE outputs
SET output_type = CASE WHEN TRIM(COALESCE(output_type, '')) = '' THEN COALESCE(type, '') ELSE output_type END,
    model_used = CASE WHEN TRIM(COALESCE(model_used, '')) = '' THEN COALESCE(model, '') ELSE model_used END,
    scope_artifact_ids = CASE WHEN TRIM(COALESCE(scope_artifact_ids, '')) = '' THEN '[]' ELSE scope_artifact_ids END;

CREATE INDEX IF NOT EXISTS idx_outputs_course_output_type_created
ON outputs(course_id, output_type, created_at DESC);
