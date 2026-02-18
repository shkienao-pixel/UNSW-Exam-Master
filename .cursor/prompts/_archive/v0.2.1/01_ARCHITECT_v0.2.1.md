# 01_ARCHITECT_v0.2.1.md

## 1. Information Architecture

### Sidebar Navigation (Top-level)
- `dashboard`
- `study`
- `flashcards`
- `exam`

### Course Control Block (Sidebar)
- Create Course form:
  - `course_code` (required, unique)
  - `course_name` (required)
- Active Course selector:
  - source: `courses` table
  - stored in session as `active_course_id`

### Study Workspace Tabs (course-scoped)
- `Upload`:
  - PDF upload (blocked if no active course)
  - artifacts saved to disk + DB (`artifacts`)
  - index build per active course
- `Generate`:
  - summary / graph / syllabus actions
  - all writes to `outputs`
- `Outputs`:
  - historical outputs list (filtered by active course)
  - view + download per output

### Flashcards Workspace (standalone page)
- Deck management:
  - create deck (`vocab`/`mcq`)
  - select deck
- Generation:
  - vocab cards from `LLMProcessor.generate_flashcards`
  - mcq cards from `QuizGenerator.generate_quiz`
- Review:
  - card-by-card flip/reveal (MVP)

---

## 2. Data Model

### `courses`
- `id TEXT PRIMARY KEY`
- `code TEXT NOT NULL UNIQUE`
- `name TEXT NOT NULL`
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`

### `artifacts`
- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `course_id TEXT NOT NULL` FK -> `courses(id)`
- `file_name TEXT NOT NULL`
- `file_hash TEXT NOT NULL`
- `file_path TEXT NOT NULL`
- `created_at TEXT NOT NULL`
- UNIQUE(`course_id`, `file_hash`)

### `outputs`
- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `course_id TEXT NOT NULL` FK -> `courses(id)`
- `type TEXT NOT NULL` (`summary`/`graph`/`syllabus`)
- `scope TEXT NOT NULL` (default `course`)
- `model TEXT NOT NULL`
- `status TEXT NOT NULL` (`success`/`failed`)
- `content TEXT`
- `path TEXT`
- `created_at TEXT NOT NULL`

### `decks`
- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `course_id TEXT NOT NULL` FK -> `courses(id)`
- `name TEXT NOT NULL`
- `deck_type TEXT NOT NULL` (`vocab`/`mcq`)
- `created_at TEXT NOT NULL`

### `cards`
- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `deck_id INTEGER NOT NULL` FK -> `decks(id)`
- `course_id TEXT NOT NULL` FK -> `courses(id)`
- `card_type TEXT NOT NULL` (`vocab`/`mcq`)
- `front TEXT`
- `back TEXT`
- `question TEXT`
- `options_json TEXT`
- `answer TEXT`
- `explanation TEXT`
- `created_at TEXT NOT NULL`

---

## 3. Migration Strategy
- Add `002_course_workspace.sql`.
- Only additive schema changes (no destructive alteration).
- Keep `migrate.py` workflow unchanged:
  - lock file
  - `BEGIN IMMEDIATE`
  - rollback on error
  - schema_version bump only on success

---

## 4. Service/API Signatures

### `services/course_workspace_service.py`
- `list_courses() -> list[dict[str, Any]]`
- `create_course(code: str, name: str) -> dict[str, Any]`
- `get_course(course_id: str) -> dict[str, Any] | None`
- `save_artifact(course_id: str, file_name: str, file_bytes: bytes) -> dict[str, Any]`
- `list_artifacts(course_id: str) -> list[dict[str, Any]]`
- `create_output(course_id: str, output_type: str, content: str, scope: str = "course", model: str = "gpt-4o", status: str = "success", path: str = "") -> int`
- `list_outputs(course_id: str, output_type: str = "") -> list[dict[str, Any]]`
- `create_deck(course_id: str, name: str, deck_type: str) -> int`
- `list_decks(course_id: str) -> list[dict[str, Any]]`
- `replace_vocab_cards(deck_id: int, course_id: str, cards: list[dict[str, str]]) -> int`
- `replace_mcq_cards(deck_id: int, course_id: str, questions: list[dict[str, Any]]) -> int`
- `list_cards(deck_id: int) -> list[dict[str, Any]]`

---

## 5. State Management Contract
- Source of truth for active course: `st.session_state["active_course_id"]`.
- Course switch clears course-derived transient state (summary/graph/syllabus/chat/exam cache).
- Generation and indexing always read active course id from state at execution time.
