# UNSWExam / Study Assistant — Project Long-Term Context (Keep)

## 0) Product Goal
A web app for students to upload learning materials and generate:
- Study summary
- Quiz (test questions)
- Flashcards (MCQ + Knowledge cards)
- Mistakes review (错题本)
Key requirement: modules/pages MUST NOT be tightly coupled; each feature has its own page and state.

## 1) Current Version / Baseline
- Current app version target: v0.2.x (recently referenced v0.2.1 -> v0.2.3 -> v0.2.4 QA doc)
- Routes must all be reachable and refresh-safe:
  /dashboard /study /quiz /flashcards /mistakes
- Quiz and Flashcards state must be independent.

## 2) Core UX / Page Separation
- The following must be separate pages with navigation always available:
  Dashboard, Study, Quiz, Flashcards, Mistakes.
- Page refresh should not break routing or state.
- NO “everything in one page” coupling.

## 3) Generation Scope (重要需求)
Problem: users upload too many files → generated content too mixed.
Required solution:
- In “Generate” flow, allow selecting partial files / chapters.
- Add manual “+” to add chapters/sections.
- Different chapters can be associated with different files.
- Save this mapping as memory (persistent configuration) so users don’t redo it.

## 4) Quiz Module Requirements (重要需求)
- Question count exists ONLY in Quiz generation, not elsewhere.
- Translation of the question stem must be toggleable anytime (on/off).
- Options must be selectable; each question MUST have “Submit”.
- Only after Submit:
  - show correct/incorrect result
  - show explanation/analysis
  - correct => green border, wrong => red border, unanswered => black border
- Should support per-question submission state (not all-or-nothing).

## 5) Flashcards Module Requirements
- Mixed card generation supported (MCQ + Knowledge cards)
- Rendering contract correct for both types
- showAnswer toggle works
- known/unknown updates stats
- Deck end-state correct

## 6) Mistakes (错题本) Rules
- unknown writes into mistake bank and deduplicates by question identity
- repeated unknown increments wrongCount
- list filtering available
- review only shows active
- master/delete state changes correct (delete = soft delete / archived)

## 7) Regression Must Hold
- Study unaffected
- Quiz unaffected by Flashcards changes
- Document extraction/chunking unaffected

## 8) QA Checklist (High-Level)
Routing:
- 5 routes reachable
- refresh stable
- quiz/flashcards not coupled
Flashcards:
- mixed cards, rendering contract, toggles, stats, end-state
Mistakes:
- unknown write+dedupe, wrongCount, filters, review active only, master/delete
Regression:
- study/quiz/chunking unaffected

## 9) Engineering Conventions
- Prefer idempotent migrations; failures rollback safely
- Avoid hidden coupling between modules; use clear state boundaries
- Persist “generation scope” + chapter-file mapping

## 10) When context gets long
If the agent seems to forget constraints, always re-read this file and follow it strictly.
