# 02_WORKER_v0.2.1.md

## Worker Execution (Phase 2.2 / v0.2.1)

### W1. DB Migration + Repository Layer
**Scope**
- Added migration `src/migrations/sql/002_course_workspace.sql`.
- Added `src/services/course_workspace_service.py` for Course/Artifact/Output/Deck/Card persistence.

**DoD**
- [x] Schema adds `courses`, `artifacts`, `outputs`, `decks`, `cards`.
- [x] Migration remains additive and idempotent.
- [x] Repository functions cover create/list/get/update paths required by UI.

**Evidence**
- Command:
  - `python - <<PY ... migrate_to_latest(); latest_migration_version() ... PY`
- Result:
  - `latest_migration_version= 2`
  - `db_schema_version= 2`
  - tables include `courses, artifacts, outputs, decks, cards`.

---

### W2. Course-first Sidebar + Upload Binding
**Scope**
- Replaced free-text collection with course manager in sidebar.
- Enforced active course before upload/index.
- Persisted uploaded PDFs to artifacts with `course_id` binding.

**DoD**
- [x] Sidebar supports create course (`code + name`) and select course.
- [x] Upload blocked when no active course.
- [x] Uploaded PDFs are persisted as artifacts under current `course_id`.

**Evidence**
- Code anchors:
  - `src/app.py` `_render_sidebar`, `_render_study_mode`
  - `src/services/course_workspace_service.py` `create_course`, `save_artifact`, `list_artifacts`
- Search trace:
  - `rg -n "create_course\(|save_artifact\(|course_selector|select_course_first" src/app.py src/services/course_workspace_service.py`

---

### W3. Course-bound Generate + Outputs History
**Scope**
- Study workspace refactored into tabs (`Upload`, `Generate`, `Outputs`, `Q&A`).
- Summary/graph/syllabus generation writes to `outputs` table with `course_id`.
- Outputs tab supports history view + download.

**DoD**
- [x] Generate actions are course-bound.
- [x] Outputs persisted with required metadata fields.
- [x] Outputs tab can view and download historical records.

**Evidence**
- Code anchors:
  - `src/app.py` `_persist_output_record`, `_render_outputs_tab`
  - `src/services/course_workspace_service.py` `create_output`, `list_outputs`, `get_output`
- Search trace:
  - `rg -n "create_output\(|_render_outputs_tab|outputs_history|output_download" src/app.py src/services/course_workspace_service.py`

---

### W4. Standalone Flashcards (Deck/Card MVP)
**Scope**
- Added top-level navigation entry `Flashcards`.
- Added deck creation and card generation per course for:
  - `vocab` cards via `LLMProcessor.generate_flashcards`
  - `mcq` cards via `QuizGenerator.generate_quiz`
- Added review interface (prev/next, reveal answer/explanation).

**DoD**
- [x] Flashcards is independent first-level page.
- [x] Deck/Card DB model is used.
- [x] Supports vocab + mcq flows end-to-end.

**Evidence**
- Code anchors:
  - `src/app.py` `_render_flashcards_page`
  - `src/services/course_workspace_service.py` `create_deck`, `replace_vocab_cards`, `replace_mcq_cards`, `list_cards`
- Search trace:
  - `rg -n "_render_flashcards_page|create_deck\(|replace_vocab_cards|replace_mcq_cards|list_cards" src/app.py src/services/course_workspace_service.py`
