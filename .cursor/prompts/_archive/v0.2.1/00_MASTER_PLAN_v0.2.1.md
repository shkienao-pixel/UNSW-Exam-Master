# 00_MASTER_PLAN_v0.2.1.md

## Project Identity
**App Name:** UNSW Exam Master
**Current Version:** 0.2.0
**Target Version:** 0.2.1 (default), 0.3.0 only if incompatible DB break is unavoidable
**Iteration Goal:** Phase 2.2 / Course-first workspace + Outputs history + standalone Flashcards

---

## 1. Feature Specifications (Definition of Done)

### A. Course-first study flow
- Sidebar replaces free-text `Collection` with **Course selector + Create Course**.
- Course creation requires `course_code` + `course_name`.
- Upload is blocked when no active course is selected.
- Uploaded PDFs are saved as artifacts bound to `course_id`.

### B. Course-bound generation and output persistence
- Study workspace keeps generation area for:
  - chapter summary
  - knowledge graph
  - revision syllabus
- Every generation writes to `outputs` table with:
  - `course_id`, `type`, `scope`, `created_at`, `model`, `status`, `content/path`
- Outputs tab shows history by course and supports view/download.

### C. Flashcards standalone zone
- Flashcards is a top-level navigation page.
- Support Deck/Card model with deck types:
  - `vocab`
  - `mcq`
- Support deck creation, card generation, and an MVP review interface.

### D. Migration safety invariants
- Keep existing migration guarantees:
  - migration lock
  - transaction per migration
  - rollback on failure
  - idempotent reruns
- New schema must be delivered through migration SQL files.

### E. Versioning and release notes
- `VERSION` updated to `0.2.1`.
- `CHANGELOG.md` adds `## 0.2.1 - 2026-02-18` with Added/Changed sections.

---

## 2. Sprint Roadmap (Swarm Kanban)

### Phase M (MASTER)
- [x] Produce v0.2.1 execution plan in MASTER format.
- [x] Define stage handoff contracts for Architect/Worker/QA.

### Phase A (ARCHITECT)
- [x] Define IA for sidebar nav + course workspace tabs.
- [x] Define DB model + relations + migration strategy.
- [x] Define service/repository APIs and state boundaries.

### Phase W (WORKER)
- [x] W1: Migration + repository (Course/Artifact/Output/Deck/Card)
- [x] W2: Course selector/create + upload gating + artifact binding
- [x] W3: Outputs persistence/history/download in Study workspace
- [x] W4: Standalone Flashcards page with vocab/mcq deck/card flow

### Phase Q (QA)
- [x] Functional QA against DoD A-E
- [x] Migration idempotency + cold-start validation
- [x] Compile/self-check evidence
- [x] Release summary and verification steps

---

## 3. Operational Rules
- No phase skipping.
- Every phase must emit a markdown artifact in `.cursor/prompts`.
- Worker tasks must include DoD + Evidence (commands + click paths).
- Final merge requires QA pass and version/changelog updates.
