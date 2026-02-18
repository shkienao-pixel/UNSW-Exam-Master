-- Flashcards + Mistakes Bank schema for v0.2.4

CREATE TABLE IF NOT EXISTS flashcards (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    course_id TEXT NOT NULL,
    deck_id TEXT NOT NULL,
    card_type TEXT NOT NULL CHECK (card_type IN ('mcq', 'knowledge')),
    scope_json TEXT NOT NULL,
    front_json TEXT NOT NULL,
    back_json TEXT NOT NULL,
    stats_json TEXT NOT NULL,
    source_refs_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_flashcards_user_course_deck
ON flashcards(user_id, course_id, deck_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_flashcards_card_type
ON flashcards(card_type, created_at DESC);

CREATE TABLE IF NOT EXISTS mistakes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    flashcard_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'mastered', 'archived')),
    added_at TEXT NOT NULL,
    wrong_count INTEGER NOT NULL DEFAULT 1,
    last_wrong_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(user_id, flashcard_id),
    FOREIGN KEY(flashcard_id) REFERENCES flashcards(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_mistakes_user_status_wrong_last
ON mistakes(user_id, status, wrong_count DESC, last_wrong_at DESC);
