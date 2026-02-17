# 01_ARCHITECT.md

## 1. Technical Stack (Strict Enforcement)
- **Frontend:** Streamlit (`streamlit`)
- **Orchestration:** LangChain (`langchain`, `langchain-community`)
- **LLM Interface:** ChatOpenAI or GoogleGenerativeAI
- **Data Processing:** `pypdf`, `youtube-transcript-api`, `tiktoken`
- **Vector Store:** `chromadb` or `faiss-cpu` (Local only)
- **Visualization:** `graphviz`

## 2. Directory Structure Blueprint
You must strictly follow this folder structure. Do not create files in root except `app.py`.

```text
/UNSW-Exam-App
├── .cursor/prompts/       # Agent Rules
├── data/
│   ├── raw/               # User uploads go here temporarily
│   └── vector_db/         # ChromaDB persistence
├── src/
│   ├── app.py             # Main entry point (UI Layout only)
│   ├── config.py          # Global settings (Colors, Prompts)
│   ├── services/          # Business Logic
│   │   ├── document_processor.py  # PDF/Text handling
│   │   ├── llm_service.py         # Chains & Prompts
│   │   └── quiz_generator.py      # Exam logic
│   └── utils/             # Helpers
│       ├── file_utils.py
│       └── session_state.py       # Manage st.session_state
└── requirements.txt
Quiz JSON Structure
The LLM MUST output quizzes in this exact JSON format:
{
  "quiz_title": "Chapter 1 Review",
  "questions": [
    {
      "id": 1,
      "type": "MCQ",
      "question": "What is the time complexity of QuickSort?",
      "options": ["O(n)", "O(n log n)", "O(n^2)", "O(1)"],
      "correct_answer": "O(n log n)",
      "explanation": "Average case is n log n, worst case is n^2."
    }
  ]
}