-- Scope Set persistence and output scope_set_id for v0.2.3.
CREATE TABLE IF NOT EXISTS scope_sets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id TEXT NOT NULL,
    name TEXT NOT NULL,
    is_default INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(course_id) REFERENCES courses(id) ON DELETE CASCADE,
    UNIQUE(course_id, name)
);

CREATE TABLE IF NOT EXISTS scope_set_items (
    scope_set_id INTEGER NOT NULL,
    artifact_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(scope_set_id, artifact_id),
    FOREIGN KEY(scope_set_id) REFERENCES scope_sets(id) ON DELETE CASCADE,
    FOREIGN KEY(artifact_id) REFERENCES artifacts(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_scope_sets_course_default
ON scope_sets(course_id, is_default, created_at ASC);

CREATE INDEX IF NOT EXISTS idx_scope_set_items_scope
ON scope_set_items(scope_set_id, artifact_id);

ALTER TABLE outputs ADD COLUMN scope_set_id INTEGER;

CREATE INDEX IF NOT EXISTS idx_outputs_course_scope_set_created
ON outputs(course_id, scope_set_id, created_at DESC);
