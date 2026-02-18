# MASTER PLAN — v0.2.4 Flashcards + Mistakes Bank + Navigation Routing

## Project Identity
**App Name:** UNSW Exam Master  
**Current Version:** 0.2.1  
**Target Version:** 0.2.4  
**Iteration Goal:** Implement NotebookLM-style Flashcards (mixed MCQ + Knowledge cards) and Mistakes Bank, and split navigation into independent routed pages (no page coupling).

---

## 1. Goal (v0.2.4)
- Deliver a productized Flashcards experience with mixed card types (`mcq` + `knowledge`).
- Persist user review behavior (`known` / `unknown`) and build Mistakes Bank workflow.
- Decouple navigation into independent routes so Quiz and Flashcards states are isolated.

## 2. Non-Goals (v0.2.4)
- No SRS spaced-repetition algorithm in this version.
- No complex analytics dashboard/reporting.
- No full-site i18n architecture refactor.

## 3. UX Requirements (Key Interaction Acceptance)
- Flashcards viewer must show progress `i/N`.
- Flashcards viewer must provide `Show Answer` flip/toggle behavior.
- `✅ Known` and `❌ Unknown` actions must always be visible.
- MCQ card:
  - render stem + options
  - support option click/select
  - render answer + explanation on back.
- Knowledge card:
  - render key concept/statement on front
  - render explanation/example on back.
- `❌ Unknown` behavior:
  - immediately upsert into Mistakes Bank
  - deduplicate by `(userId, flashcardId)`
  - repeated unknown increments `wrongCount` only
  - then advance to next card.
- Deck completion must display a finished state.

## 4. Navigation Routing (Must Split Pages)
- Required routes:
  - `/dashboard`
  - `/study`
  - `/quiz`
  - `/flashcards`
  - `/mistakes`
- Hard rule:
  - Quiz and Flashcards states must not be shared.
  - Quiz and Flashcards must not be coupled in the same page component.

## 5. Data Model (MVP)
### Flashcard
- `id`, `userId`, `type` (`"mcq" | "knowledge"`)
- `scope`: `{ chapterIds: [], fileIds: [] }`
- `front`: `{ stem: string, options?: string[] }`
- `back`: `{ answer?: number | string, explanation: string }`
- `stats`: `{ seen, known, unknown, lastReviewedAt? }`
- `sourceRefs?`: `[{ fileId, page?, chunkId?, quote? }]`
- `createdAt`

### MistakeItem
- `id`, `userId`, `flashcardId`
- `status`: `"active" | "mastered" | "archived"`
- `addedAt`, `wrongCount`, `lastWrongAt`
- Dedup strategy: `unique(userId, flashcardId)` or equivalent upsert.

## 6. API Endpoints (MVP)
- `POST /api/flashcards/generate`
- `POST /api/flashcards/:id/review`
- `GET  /api/mistakes`
- `GET  /api/mistakes/review`
- `POST /api/mistakes/:id/master`
- `DELETE /api/mistakes/:id` (soft delete)

## 7. Acceptance Criteria
- 5 route pages are reachable and operationally decoupled.
- Flashcards mixed deck generation works (`mcq` + `knowledge`).
- `Known/Unknown` updates Flashcard stats correctly.
- `Unknown` writes to Mistakes Bank with dedup + `wrongCount` increment.
- Mistakes supports list/filter/review/master/soft-delete.
- Study and Quiz existing capabilities are not regressed.

## 8. Task Breakdown (3-Agent Handoff)
- **ARCHITECT**
  - routing boundaries
  - API contracts
  - storage schema + upsert strategy
  - generator schema contract.
- **WORKER**
  - route pages
  - API endpoints
  - persistence implementation
  - Flashcards + Mistakes UI flows.
- **QA**
  - end-to-end cases
  - regression matrix
  - reproducible evidence and pass/fail verdict.

---

## 9. Sprint Roadmap (Swarm Kanban)
### Phase M (MASTER)
- [x] Produce v0.2.4 execution plan in MASTER format.
- [x] Define stage handoff contracts for Architect/Worker/QA.

### Phase A (ARCHITECT)
- [ ] Define routing/page isolation spec.
- [ ] Define Flashcards/Mistakes data and API architecture.
- [ ] Define generator JSON contract and validation/retry strategy.

### Phase W (WORKER)
- [ ] W1: Routing/page split implementation (`/dashboard /study /quiz /flashcards /mistakes`)
- [ ] W2: Storage + migration + dedup upsert for mistakes
- [ ] W3: Flashcards generation/review flow
- [ ] W4: Mistakes list/review/master/archive flow

### Phase Q (QA)
- [ ] Route decoupling and refresh tests
- [ ] Flashcards + Mistakes functional validation
- [ ] Study/Quiz regression verification
- [ ] Release verification summary

---

## 10. Operational Rules
- No phase skipping.
- Every phase must emit a markdown artifact in `.cursor/prompts`.
- Worker tasks must include DoD + Evidence (commands + click paths).
- Final merge requires QA pass and version/changelog updates.
