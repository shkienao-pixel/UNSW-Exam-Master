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