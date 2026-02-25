-- Operation metrics table for tracking index and generation performance.
CREATE TABLE IF NOT EXISTS operation_metrics (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    operation  TEXT    NOT NULL,           -- "index" | "summary" | "quiz" | "flashcard" | "graph" | "chat" | "outline"
    course_id  TEXT    NOT NULL DEFAULT '',
    elapsed_s  REAL    NOT NULL,           -- wall-clock seconds
    meta_json  TEXT    NOT NULL DEFAULT '{}',
    created_at TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_metrics_operation_created
ON operation_metrics(operation, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_metrics_course_created
ON operation_metrics(course_id, created_at DESC);
