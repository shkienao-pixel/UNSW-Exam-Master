# 02_WORKER.md

## 1. Coding Standards (Python)
- **Type Hinting:** ALL functions must have type hints.
  - *Bad:* `def process(file):`
  - *Good:* `def process_file(file: UploadedFile) -> str:`
- **Docstrings:** Use Google-style docstrings for every class and complex function.
- **Variable Naming:** Use `snake_case` for variables/functions, `CamelCase` for classes.

## 2. Streamlit Best Practices
- **State Management:** NEVER rely on global variables. Use `st.session_state['key']`.
- **Caching:** Use `@st.cache_data` for data loading and `@st.cache_resource` for loading ML models/databases.
- **Feedback:** Use `st.spinner("Processing...")` for long-running tasks.

## 3. Error Handling Strategy
- Wrap all external API calls (OpenAI/Gemini) in `try-except` blocks.
- If an API call fails, return a default safe object or raise a custom `AppException`.
- **Never** let the user see a raw Python `Traceback`.

## 4. Implementation Rules
- **Do not** write logic inside `app.py`. `app.py` should only contain UI calls like `st.title`, `st.sidebar`, and calls to `src/services`.
- **Do not** hardcode API keys. Always use `os.getenv` or Streamlit secrets.

---

## Task Plan: Phase 2.2 Dashboard (Portal-style IA, no asset copying)

### Objective
Add a new `Dashboard` page as default landing page while keeping existing `Study` and `Exam` features intact.

### Files to Change
1. `src/app.py`
   - Add top-level navigation with default `Dashboard`.
   - Implement `_render_dashboard()` with:
     - Hero header (app info + quick action buttons)
     - Quick action cards
     - Updates (read latest 3 changelog items)
     - Activity/events block
     - Need-help block
   - Reuse existing Study/Exam renderers unchanged where possible.
   - Add minimal helper functions:
     - changelog parsing
     - shared index-build action
     - activity timestamp updates
   - Keep migration/version/index checks working.

2. `src/i18n.py`
   - Add translation keys (EN/ZH) for all new Dashboard labels/buttons/messages.

3. `README.md` (optional lightweight update)
   - Add one short note describing new default Dashboard navigation.

### Scope/Architecture Guardrails
- No runtime scraping/external fetch.
- No UNSW logos/images/text reuse.
- No structural architecture change outside current Streamlit app + services pattern.
- Existing Study/Exam behavior must remain available.

### Risks & Mitigations
1. **Risk:** Dashboard actions duplicate index build logic and drift from Study page.
   - **Mitigation:** extract a shared helper for index build action.
2. **Risk:** Streamlit rerun behavior causes double execution for action buttons.
   - **Mitigation:** reuse existing `index_rebuild_in_progress` lock state.
3. **Risk:** Changelog parser brittle to markdown format changes.
   - **Mitigation:** fallback to first non-empty bullet lines from file.
4. **Risk:** Navigation refactor accidentally hides existing tabs.
   - **Mitigation:** switch to explicit page router with `Dashboard/Study/Exam` and keep previous render functions intact.
