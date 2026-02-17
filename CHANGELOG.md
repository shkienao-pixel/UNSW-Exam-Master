# Changelog

## 0.2.0 - 2026-02-17
- Added app versioning with `VERSION` file and sidebar About section.
- Added SQLite schema migration system:
  - `src/migrations/migrate.py`
  - SQL migrations under `src/migrations/sql/`
  - automatic startup migration execution.
- Added migration backups:
  - `app.db` copied to `backups/app_<timestamp>.db`
  - `data/subjects` zipped to `backups/subjects_<timestamp>.zip` when present.
- Added Chroma index settings metadata:
  - `index_version`
  - `embedding_model_name`
  - `embedding_dim`
- Added index compatibility checks and rebuild warning in UI.
- Added global UI language switch (Chinese/English).
- Added optional PDF export dependency (`reportlab`) to requirements.
