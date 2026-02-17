# 00_MASTER_PLAN.md

## Project Identity
**App Name:** UNSW Exam Master
**Goal:** A Streamlit-based local study assistant that converts raw course materials (PDF/Video) into structured exam assets.
**Target User:** UNSW Students aiming for High Distinction (HD).

---

## 1. Feature Specifications (The "Definition of Done")

### A. Study Mode (The Input)
- **File Ingestion:** Must support PDF, PPTX, and TXT.
- **YouTube Support:** Must extract transcripts from valid YouTube URLs.
- **Processing:** Content must be chunked by "Topics" or "Weeks", not just random text splitting.

### B. Summary Engine (The output)
- **Constraint:** Summaries must be strictly hierarchical (H1: Chapter -> H2: Key Concept -> H3: Definition/Formula).
- **Requirement:** Must identify and render LaTeX formulas correctly.

### C. Knowledge Graph
- **Tool:** Use `streamlit-agraph` or `graphviz`.
- **Logic:** Nodes = Key Concepts; Edges = Verbs (e.g., "calculates", "influences").

### D. Exam Simulator (The Core)
- **Quiz Format:** JSON-based generation.
- **Question Types:** Multiple Choice (MCQ) & Short Answer.
- **Feedback:** EVERY question must have an "Explanation" field detailing why the answer is correct.

---

## 2. Sprint Roadmap (Kanban)

### Phase 1: Infrastructure (Current)
- [ ] **1.1 Project Setup:** Create strict folder structure (see Architect).
- [ ] **1.2 Base UI:** Create Streamlit sidebar layout with API Key input.
- [ ] **1.3 Data Loader:** Implement `PDFProcessor` and `YouTubeLoader` classes.

### Phase 2: Logic Implementation
- [ ] **2.1 RAG Pipeline:** Set up LangChain + VectorStore (Chroma/FAISS).
- [ ] **2.2 Prompt Engineering:** Write system prompts for "Professor Persona".

### Phase 3: Exam Features
- [ ] **3.1 Quiz Generator:** Connect LLM to generate valid JSON quizzes.
- [ ] **3.2 Quiz UI:** Render interactive radio buttons and "Show Answer" toggles.

---

## 3. Operational Rules
- **No Spaghetti Code:** If a file exceeds 100 lines, refactor it.
- **User First:** If an error occurs, show a friendly `st.error` message, not a traceback.