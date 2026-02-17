# UNSW Exam Master

AI-native exam preparation tool for UNSW students, built with Streamlit + LangChain + Chroma.

## Run

```powershell
.\.venv\Scripts\streamlit.exe run src/app.py
```

## Navigation

- Default landing page is `Dashboard`.
- Use sidebar `Navigation` to switch between `Dashboard`, `Study`, and `Exam`.

## Upgrading & Migrations

- App version is stored in `VERSION` (semantic versioning).
- On app startup, migrations are applied automatically via `src/migrations/migrate.py`.
- SQLite DB path: `data/app.db`.
- Migration lock file: `backups/.migrate.lock` (prevents concurrent migration runs).
- Migration SQL files live in `src/migrations/sql/` and run in ascending order (`001_*.sql`, `002_*.sql`, ...).
- Schema version is stored in SQLite table:
  - `meta(key TEXT PRIMARY KEY, value TEXT)`
  - key `schema_version` stores current integer version.

### Backups before migration

Before pending migrations are applied, the app creates backups in `backups/`:

- `backups/app_<timestamp>.db` (copy of `data/app.db`, when DB exists)
- `backups/subjects_<timestamp>.zip` (zip of `data/subjects`, when folder exists)

### Failure Recovery

- Each migration is executed in a transaction.
- On migration failure:
  - transaction is rolled back
  - `schema_version` is not bumped
  - app shows a recovery message pointing to `backups/`
- If migration lock already exists, app shows a one-time `migration in progress` notice.

## Vector Index Versioning

Each Chroma collection stores:

- `index_version`
- `embedding_model_name`
- `embedding_dim` (when available)

If index metadata does not match current settings, UI shows:

- `Index outdated, please rebuild`
- Rebuild button to clear and rebuild index from current uploaded PDFs
- Rebuild lock prevents double-click / rerun re-entry during index rebuild
- If indexing fails mid-way, index metadata is marked incomplete and UI keeps prompting rebuild

## Manual Test Checklist

1. Fresh start without `data/app.db`:
   - Launch app and verify it starts normally.
   - Confirm `data/app.db` is created.
2. Existing DB migration:
   - Add a new migration SQL, relaunch app, verify version increments.
3. Backup creation:
   - With pending migrations and existing `data/app.db`, verify `backups/app_<timestamp>.db`.
   - With existing `data/subjects`, verify `backups/subjects_<timestamp>.zip`.
4. Version display:
   - Check sidebar About section shows app version and schema version.
5. Index metadata mismatch:
   - Force mismatch metadata (or change expected version) and verify warning + rebuild button.
6. Rebuild workflow:
   - Upload PDFs, click rebuild, verify index stats update and warning disappears.
7. RAG non-regression:
   - Build index, run summary/chat/exam generation, verify outputs still work.
