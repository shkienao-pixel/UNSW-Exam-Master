-- Course-scoped workspace entities.
CREATE TABLE IF NOT EXISTS courses (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id TEXT NOT NULL,
    file_name TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    file_path TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(course_id) REFERENCES courses(id) ON DELETE CASCADE,
    UNIQUE(course_id, file_hash)
);

CREATE INDEX IF NOT EXISTS idx_artifacts_course_created
ON artifacts(course_id, created_at DESC);

CREATE TABLE IF NOT EXISTS outputs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id TEXT NOT NULL,
    type TEXT NOT NULL,
    scope TEXT NOT NULL,
    model TEXT NOT NULL,
    status TEXT NOT NULL,
    content TEXT,
    path TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(course_id) REFERENCES courses(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_outputs_course_created
ON outputs(course_id, created_at DESC);

CREATE TABLE IF NOT EXISTS decks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id TEXT NOT NULL,
    name TEXT NOT NULL,
    deck_type TEXT NOT NULL CHECK(deck_type IN ('vocab', 'mcq')),
    created_at TEXT NOT NULL,
    FOREIGN KEY(course_id) REFERENCES courses(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_decks_course_type
ON decks(course_id, deck_type, created_at DESC);

CREATE TABLE IF NOT EXISTS cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    deck_id INTEGER NOT NULL,
    course_id TEXT NOT NULL,
    card_type TEXT NOT NULL CHECK(card_type IN ('vocab', 'mcq')),
    front TEXT,
    back TEXT,
    question TEXT,
    options_json TEXT,
    answer TEXT,
    explanation TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(deck_id) REFERENCES decks(id) ON DELETE CASCADE,
    FOREIGN KEY(course_id) REFERENCES courses(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_cards_deck_created
ON cards(deck_id, created_at ASC);
